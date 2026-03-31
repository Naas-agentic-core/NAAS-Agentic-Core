import asyncio
import os

from microservices.research_agent.src.logging import get_logger
from microservices.research_agent.src.search_engine.fallback_expander import FallbackQueryExpander
from microservices.research_agent.src.search_engine.models import SearchRequest, SearchResult
from microservices.research_agent.src.search_engine.query_refiner import get_refined_query
from microservices.research_agent.src.search_engine.strategies import (
    KeywordStrategy,
    RelaxedVectorStrategy,
    SearchStrategy,
    StrictVectorStrategy,
)

logger = get_logger("search-orchestrator")


class SearchOrchestrator:
    """
    Orchestrates the search process:
    1. Query Refinement (DSPy)
    2. Query Expansion (Fallback)
    3. Strategy Execution (Strict -> Relaxed -> Keyword)
    """

    def __init__(self):
        self.strategies: list[SearchStrategy] = [
            StrictVectorStrategy(),
            RelaxedVectorStrategy(),
            KeywordStrategy(),
        ]

    @staticmethod
    def _is_generic_query(request: SearchRequest) -> bool:
        """يتحقق من كون الاستعلام عامًا جدًا بدون قيود دلالية واضحة."""
        if not request.q:
            return False
        tokens = [token for token in request.q.split() if token.strip()]
        has_structured_filters = any(
            value is not None and value != ""
            for value in request.filters.model_dump(exclude_none=True).values()
        )
        return len(tokens) <= 2 and not has_structured_filters

    async def search(self, request: SearchRequest) -> list[SearchResult]:
        original_q = request.q
        refined_q = original_q

        # 1. DSPy Refinement
        api_key = os.environ.get("OPENROUTER_API_KEY")
        if original_q and api_key:
            try:
                logger.info(f"🔍 DSPy Active: Refining query '{original_q}'...")
                dspy_result = await asyncio.to_thread(get_refined_query, original_q, api_key)

                if isinstance(dspy_result, dict):
                    refined_q = dspy_result.get("refined_query", original_q)
                    # Update filters if found
                    if dspy_result.get("year"):
                        request.filters.year = dspy_result["year"]
                    if dspy_result.get("subject"):
                        request.filters.subject = dspy_result["subject"]
                    if dspy_result.get("branch"):
                        request.filters.branch = dspy_result["branch"]

                    logger.info(
                        f"✅ DSPy Result: '{refined_q}' | Filters: {request.filters.model_dump(exclude_none=True)}"
                    )
                else:
                    logger.warning("⚠️ DSPy returned unexpected format.")

            except Exception as e:
                logger.warning(f"⚠️ DSPy refinement failed: {e}")

        # Update request with refined query for Vector Search
        # We prefer the refined query for semantic search as it likely contains English translation/normalization
        request.q = refined_q
        generic_query_mode = self._is_generic_query(request)

        if generic_query_mode:
            logger.info("🧭 Generic query mode active: aggregating relaxed + keyword strategies.")
            aggregated_results: list[SearchResult] = []
            seen_ids: set[str] = set()
            for strategy in self.strategies:
                if isinstance(strategy, StrictVectorStrategy):
                    continue
                req_copy = request.model_copy(deep=True)
                if isinstance(strategy, KeywordStrategy):
                    variations = FallbackQueryExpander.generate_variations(original_q)
                    req_copy.q = variations[-1] if variations else original_q
                try:
                    strategy_results = await strategy.execute(req_copy)
                except Exception as error:
                    logger.warning(f"Generic mode strategy {strategy.name} failed: {error}")
                    continue
                for result in strategy_results:
                    if result.id in seen_ids:
                        continue
                    seen_ids.add(result.id)
                    aggregated_results.append(result)
                    if len(aggregated_results) >= request.limit:
                        break
                if len(aggregated_results) >= request.limit:
                    break
            if aggregated_results:
                return aggregated_results

        # 2. Execute Strategies
        for strategy in self.strategies:
            logger.info(f"🔄 Strategy: {strategy.name}")

            # Special handling for Keyword Strategy: Use the "cleanest" variation
            if isinstance(strategy, KeywordStrategy):
                variations = FallbackQueryExpander.generate_variations(original_q)
                if variations:
                    # The last variation is usually the most stripped/clean (stop words removed)
                    clean_q = variations[-1]
                    logger.info(f"🔑 Using Optimized Keyword Query: '{clean_q}'")
                    request.q = clean_q
                else:
                    request.q = original_q  # Fallback to original if no variations

            # Execute
            try:
                results = await strategy.execute(request)
                if results:
                    logger.info(f"🎉 Success! Found {len(results)} results using {strategy.name}.")
                    return results
                logger.info("❌ No results found in this strategy. Retrying...")
            except Exception as e:
                logger.error(f"Strategy {strategy.name} failed: {e}")
                continue

        return []


# Singleton
search_orchestrator = SearchOrchestrator()
