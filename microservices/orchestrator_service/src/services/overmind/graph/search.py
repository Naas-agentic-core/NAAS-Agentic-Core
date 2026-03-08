import time

import dspy
from llama_index.core.schema import Document as LlamaDocument
from pydantic import BaseModel

from microservices.orchestrator_service.src.core.logging import get_logger

# Assuming research_client is used for actual db access
from microservices.orchestrator_service.src.infrastructure.clients.research_client import (
    research_client,
)

logger = get_logger("search-graph")


# --- NODE 1: QueryAnalyzerNode ---
class AnalyzeQuery(dspy.Signature):
    """Extract structured filters from Arabic query"""

    raw_query: str = dspy.InputField()
    year: int = dspy.OutputField()
    subject: str = dspy.OutputField()
    branch: str = dspy.OutputField()
    exercise_num: int = dspy.OutputField()
    language: str = dspy.OutputField()
    needs_web: bool = dspy.OutputField()


class QueryFilters(BaseModel):
    raw_query: str
    year: int = 0
    subject: str = ""
    branch: str = ""
    exercise_num: int = 0
    language: str = "ar"
    needs_web: bool = False


class QueryAnalyzerNode:
    def __init__(self):
        # Initializing the actual DSPy module
        self.analyzer = dspy.Predict(AnalyzeQuery)

    def __call__(self, state: dict) -> dict:
        from .telemetry import emit_telemetry

        start_time = time.time()
        query = state.get("query", "")
        error = None

        try:
            prediction = self.analyzer(raw_query=query)
            filters = QueryFilters(
                raw_query=query,
                year=int(prediction.year) if str(prediction.year).isdigit() else 2024,
                subject=str(prediction.subject),
                branch=str(prediction.branch),
                exercise_num=int(prediction.exercise_num)
                if str(prediction.exercise_num).isdigit()
                else 1,
            )
        except Exception as e:
            logger.warning(f"DSPy parsing failed, falling back to heuristics: {e}")
            error = e
            import re

            year_match = re.search(r"20\d\d", query)
            year = int(year_match.group(0)) if year_match else 2024
            branch = "علوم تجريبية" if "تجريبية" in query else ""
            subject = "احتمالات" if "احتمالات" in query else ""
            filters = QueryFilters(
                raw_query=query, year=year, subject=subject, branch=branch, exercise_num=1
            )

        emit_telemetry(
            node_name="QueryAnalyzerNode", start_time=start_time, state=state, error=error
        )
        return {"filters": filters}


# --- NODE 2: InternalRetrieverNode ---
class InternalRetrieverNode:
    async def __call__(self, state: dict) -> dict:
        from .telemetry import emit_telemetry

        start_time = time.time()
        filters: QueryFilters = state.get("filters")

        exact_filters = {
            "year": filters.year,
            "branch": filters.branch,
            "subject": filters.subject,
            "exercise_num": filters.exercise_num,
        }
        try:
            exact_results = await research_client.semantic_search(
                query=filters.raw_query, top_k=5, filters=exact_filters
            )

            if exact_results:
                docs = [
                    LlamaDocument(
                        text=res.get("content", ""),
                        metadata={
                            "source": "قاعدة البيانات الداخلية",
                            "score": res.get("score", 1.0),
                        },
                    )
                    for res in exact_results
                ]
                emit_telemetry(
                    node_name="InternalRetrieverNode",
                    start_time=start_time,
                    state=state,
                    retrieval_source="internal_exact",
                )
                return {"retrieved_docs": docs}

            semantic_results = await research_client.semantic_search(
                query=filters.raw_query, top_k=15, filters={}
            )
            docs = [
                LlamaDocument(
                    text=res.get("content", ""),
                    metadata={"source": "قاعدة البيانات الداخلية", "score": res.get("score", 0.5)},
                )
                for res in semantic_results
            ]
            emit_telemetry(
                node_name="InternalRetrieverNode",
                start_time=start_time,
                state=state,
                retrieval_source="internal_hybrid",
            )
            return {"retrieved_docs": docs}
        except Exception as e:
            emit_telemetry(
                node_name="InternalRetrieverNode", start_time=start_time, state=state, error=e
            )
            return {"retrieved_docs": []}


# --- NODE 3: RerankerNode ---
class RerankerNode:
    def __init__(self):
        try:
            from llama_index.postprocessor.flag_embedding_reranker import FlagEmbeddingReranker

            self.reranker = FlagEmbeddingReranker(
                model="cross-encoder/ms-marco-MiniLM-L-6-v2", top_n=5
            )
        except ImportError:
            self.reranker = None
            logger.warning("FlagEmbeddingReranker not installed, falling back to simple sort.")

    def __call__(self, state: dict) -> dict:
        from .telemetry import emit_telemetry

        start_time = time.time()
        docs = state.get("retrieved_docs", [])
        filters: QueryFilters = state.get("filters")
        error = None

        if not docs:
            emit_telemetry(node_name="RerankerNode", start_time=start_time, state=state)
            return {"reranked_docs": []}

        if self.reranker:
            try:
                from llama_index.core.schema import NodeWithScore, TextNode

                nodes = [
                    NodeWithScore(node=TextNode(text=d.text), score=d.metadata.get("score", 1.0))
                    for d in docs
                ]
                from llama_index.core.indices.query.schema import QueryBundle

                reranked_nodes = self.reranker.postprocess_nodes(
                    nodes=nodes, query_bundle=QueryBundle(filters.raw_query)
                )
                reranked = [
                    LlamaDocument(
                        text=n.node.text,
                        metadata={"source": "قاعدة البيانات الداخلية", "score": n.score},
                    )
                    for n in reranked_nodes
                ]
            except Exception as e:
                logger.error(f"Reranking failed: {e}")
                error = e
                reranked = docs[:5]
        else:
            docs.sort(key=lambda x: x.metadata.get("score", 0), reverse=True)
            reranked = docs[:5]

        emit_telemetry(node_name="RerankerNode", start_time=start_time, state=state, error=error)
        return {"reranked_docs": reranked}


# --- NODE 4: WebSearchFallbackNode ---
class WebSearchFallbackNode:
    async def __call__(self, state: dict) -> dict:
        from .telemetry import emit_telemetry

        start_time = time.time()
        reranked = state.get("reranked_docs", [])
        filters: QueryFilters = state.get("filters")
        error = None

        if len(reranked) == 0:
            query_str = f"بكالوريا {filters.subject} {filters.branch} {filters.year} تمرين {filters.exercise_num}"
            try:
                report = await research_client.deep_research(query_str)
                docs = [LlamaDocument(text=report, metadata={"source": "الإنترنت", "score": 0.85})]
            except Exception as e:
                error = e
                docs = []

            emit_telemetry(
                node_name="WebSearchFallbackNode",
                start_time=start_time,
                state=state,
                error=error,
                retrieval_source="web",
            )
            return {"reranked_docs": docs, "used_web": True}

        emit_telemetry(node_name="WebSearchFallbackNode", start_time=start_time, state=state)
        return {"used_web": False}


# --- NODE 5: SynthesizerNode ---
class SynthesizerNode:
    def __call__(self, state: dict) -> dict:
        from .telemetry import emit_telemetry

        start_time = time.time()
        reranked = state.get("reranked_docs", [])
        filters: QueryFilters = state.get("filters")

        if not reranked:
            text_val = "لا توجد تفاصيل متاحة."
            source = "لا يوجد"
            confidence = "0.00"
        else:
            text_val = reranked[0].text
            source = reranked[0].metadata.get("source", "الإنترنت")
            confidence = str(reranked[0].metadata.get("score", 0.85))

        response_json = {
            "المصدر": source,
            "مستوى_الثقة": confidence,
            "التمرين": text_val,
            "السنة": str(filters.year) if filters else "N/A",
            "الشعبة": filters.branch if filters else "غير محدد",
            "المادة": filters.subject if filters else "غير محدد",
            "رقم_التمرين": filters.exercise_num if filters else 1,
        }

        emit_telemetry(
            node_name="SynthesizerNode",
            start_time=start_time,
            state=state,
            confidence=float(confidence),
        )
        return {"final_response": response_json}
