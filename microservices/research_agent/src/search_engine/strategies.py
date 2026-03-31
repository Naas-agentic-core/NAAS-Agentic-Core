import os
from abc import ABC, abstractmethod

from microservices.research_agent.src.content.service import content_service
from microservices.research_agent.src.logging import get_logger
from microservices.research_agent.src.search_engine.models import (
    SearchRequest,
    SearchResult,
)
from microservices.research_agent.src.search_engine.reranker import get_reranker
from microservices.research_agent.src.search_engine.retriever import get_retriever

logger = get_logger("search-strategies")


class SearchStrategy(ABC):
    """
    Abstract base class for search strategies.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        pass

    @abstractmethod
    async def execute(self, request: SearchRequest) -> list[SearchResult]:
        pass


class BaseVectorStrategy(SearchStrategy):
    """
    Base class for vector-based strategies (Strict & Relaxed).
    """

    def __init__(self):
        self.db_url = os.environ.get("DATABASE_URL")
        self.similarity_threshold = float(os.environ.get("SEMANTIC_SIMILARITY_THRESHOLD", "0.72"))

    async def _search_vectors(self, query: str, filters: dict, limit: int) -> list[str]:
        """
        Helper to execute vector search and return Content IDs.
        Includes Reranking.
        """
        if not self.db_url:
            logger.warning("DATABASE_URL not set, skipping vector search.")
            return []

        try:
            retriever = get_retriever(self.db_url)
            # Fetch more candidates to allow for reranking
            retrieval_limit = max(limit * 3, limit + 20)

            nodes = retriever.search(
                query,
                limit=retrieval_limit,
                filters=filters,
                similarity_threshold=self.similarity_threshold,
            )
            nodes = [
                node
                for node in nodes
                if isinstance(getattr(node, "score", None), (int, float))
                and float(getattr(node, "score", 0.0)) >= self.similarity_threshold
            ]

            if nodes:
                # Rerank
                try:
                    reranker = get_reranker()
                    nodes = reranker.rerank(query, nodes, top_n=limit)
                except Exception as rerank_err:
                    logger.warning(f"Reranking failed: {rerank_err}")

            content_ids = []
            for node in nodes:
                metadata = getattr(node, "node", node)
                meta = getattr(metadata, "metadata", {})
                if isinstance(meta, dict):
                    cid = meta.get("content_id")
                    if cid:
                        content_ids.append(cid)
            return content_ids
        except Exception as e:
            logger.error(f"Vector search failed in {self.name}: {e}")
            return []

    async def _fetch_from_db(
        self, content_ids: list[str], request: SearchRequest, apply_filters: bool
    ) -> list[SearchResult]:
        """
        Fetch full records from SQL based on Vector IDs.
        """
        if not content_ids:
            return []

        # Prepare kwargs for content_service
        search_kwargs = {
            "q": None,  # We use IDs, not text search here
            "content_ids": content_ids,
            "limit": request.limit,
            "lang": request.filters.lang,
            "type": request.filters.type,
            "preserve_content_id_order": True,
        }

        if apply_filters:
            # Strict mode: Pass all filters to SQL
            search_kwargs.update(
                {
                    "level": request.filters.level,
                    "subject": request.filters.subject,
                    "branch": request.filters.branch,
                    "set_name": request.filters.set_name,
                    "year": request.filters.year,
                }
            )
        else:
            # Relaxed mode: Clear filters that might conflict with vector results
            # We assume the vector match is semantically correct even if metadata is missing/wrong.
            pass

        results_dicts = await content_service.search_content(**search_kwargs)

        # Convert to Pydantic
        return [SearchResult(**r, strategy=self.name) for r in results_dicts]


class StrictVectorStrategy(BaseVectorStrategy):
    """
    Strict Semantic Search: Uses vectors AND metadata filters.
    """

    name = "Strict Semantic"

    async def execute(self, request: SearchRequest) -> list[SearchResult]:
        if not request.q:
            return []

        # Convert Pydantic filters to dict, removing None
        filters_dict = request.filters.model_dump(exclude_none=True)

        # 1. Get IDs from Vector Store (with filters)
        content_ids = await self._search_vectors(request.q, filters_dict, request.limit)

        if not content_ids:
            return []

        # 2. Fetch from DB (enforcing filters)
        return await self._fetch_from_db(content_ids, request, apply_filters=True)


class RelaxedVectorStrategy(BaseVectorStrategy):
    """
    Relaxed Semantic Search: Uses vectors only (ignoring strict metadata).
    """

    name = "Relaxed Semantic"

    async def execute(self, request: SearchRequest) -> list[SearchResult]:
        if not request.q:
            return []

        # 1. Get IDs from Vector Store (NO filters)
        # We purposely pass empty filters to find any relevant content
        content_ids = await self._search_vectors(request.q, {}, request.limit)

        if not content_ids:
            return []

        # 2. Fetch from DB (ignoring strict filters like year/subject/branch)
        return await self._fetch_from_db(content_ids, request, apply_filters=False)


class KeywordStrategy(SearchStrategy):
    """
    Keyword Fallback: Uses SQL LIKE search via ContentService.
    """

    name = "Keyword Fallback"

    async def execute(self, request: SearchRequest) -> list[SearchResult]:
        # For keyword search, we pass the query text and all filters
        search_kwargs = {
            "q": request.q,
            "limit": request.limit,
            **request.filters.model_dump(exclude_none=True),
        }

        # Remove content_ids if present
        search_kwargs.pop("content_ids", None)

        results_dicts = await content_service.search_content(**search_kwargs)
        return [SearchResult(**r, strategy=self.name) for r in results_dicts]
