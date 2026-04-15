import asyncio
import os
import time
from types import SimpleNamespace

import anyio
from llama_index.core.schema import Document as LlamaDocument
from pydantic import BaseModel

try:
    import dspy
except ModuleNotFoundError:

    def _dspy_input_field(*_: object, **__: object) -> str:
        return ""

    def _dspy_output_field(*_: object, **__: object) -> str:
        return ""

    def _dspy_predict(*_: object, **__: object):
        def _runner(**_: object) -> SimpleNamespace:
            return SimpleNamespace(
                year=None,
                subject="",
                branch="",
                exercise_num=None,
                language="ar",
                needs_web=False,
            )

        return _runner

    class _DSPySignature:
        pass

    class _DSPyModule:
        Signature = _DSPySignature
        InputField = staticmethod(_dspy_input_field)
        OutputField = staticmethod(_dspy_output_field)
        Predict = staticmethod(_dspy_predict)

    dspy = _DSPyModule()  # type: ignore[assignment]

from microservices.orchestrator_service.src.core.logging import get_logger

# Assuming research_client is used for actual db access
from microservices.orchestrator_service.src.infrastructure.clients.research_client import (
    research_client,
)

logger = get_logger("search-graph")


# --- NODE 1: QueryAnalyzerNode ---
class AnalyzeQuery(dspy.Signature):
    """Extract structured filters from Arabic query.

    Do NOT guess or infer the year or exercise number.
    If it is not explicitly stated in the prompt, you MUST output None.
    """

    history: str = dspy.InputField(
        desc="Previous conversation context to resolve pronouns and context"
    )
    question: str = dspy.InputField()
    year: int | None = dspy.OutputField()
    subject: str = dspy.OutputField()
    branch: str = dspy.OutputField()
    exercise_num: int | None = dspy.OutputField()
    language: str = dspy.OutputField()
    needs_web: bool = dspy.OutputField()


class QueryFilters(BaseModel):
    question: str
    year: int | None = None
    subject: str = ""
    branch: str = ""
    exercise_num: int | None = None
    language: str = "ar"
    needs_web: bool = False


class QueryAnalyzerNode:
    def __init__(self):
        # Initializing the actual DSPy module
        self.analyzer = dspy.Predict(AnalyzeQuery)

    async def __call__(self, state: dict) -> dict:
        from .telemetry import emit_telemetry

        start_time = time.time()

        query = state.get("query", "")
        messages = state.get("messages", [])
        error = None

        from .main import format_conversation_history

        formatted_history = format_conversation_history(messages[:-1])

        try:

            def _coerce_nullable_int(value: object) -> int | None:
                text_value = str(value).strip().lower()
                if text_value in {"", "none", "null"}:
                    return None
                return int(text_value) if text_value.isdigit() else None

            prediction = await asyncio.wait_for(
                anyio.to_thread.run_sync(
                    lambda: self.analyzer(history=formatted_history, question=query)
                ),
                timeout=10.0,
            )
            filters = QueryFilters(
                question=query,
                year=_coerce_nullable_int(getattr(prediction, "year", None)),
                subject=str(prediction.subject),
                branch=str(prediction.branch),
                exercise_num=_coerce_nullable_int(getattr(prediction, "exercise_num", None)),
            )
        except Exception as e:
            logger.warning(f"DSPy parsing failed, returning empty filters: {e}")
            error = e
            filters = QueryFilters(
                question=query,
                year=None,
                subject="",
                branch="",
                exercise_num=None,
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

        exact_filters: dict[str, int | str] = {}
        if filters.year is not None:
            exact_filters["year"] = filters.year
        if filters.branch:
            exact_filters["branch"] = filters.branch
        if filters.subject:
            exact_filters["subject"] = filters.subject
        if filters.exercise_num is not None:
            exact_filters["exercise_num"] = filters.exercise_num
        try:
            exact_results = await asyncio.wait_for(
                research_client.semantic_search(
                    query=filters.question, top_k=5, filters=exact_filters
                ),
                timeout=10.0,
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

            # To prevent 'Ghost Exam' injection, do not default to empty filters for generic queries
            # if we have no exact match. We should still apply whatever partial filters were extracted.
            # If the user says "تمرين احتمالات", exact_filters has {'subject': 'احتمالات'}.
            # We broaden top_k but keep exact_filters to prevent returning a random 2024 exam.
            semantic_results = await asyncio.wait_for(
                research_client.semantic_search(
                    query=filters.question, top_k=15, filters=exact_filters
                ),
                timeout=10.0,
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

    async def __call__(self, state: dict) -> dict:
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

                reranked_nodes = await anyio.to_thread.run_sync(
                    self.reranker.postprocess_nodes,
                    nodes,
                    QueryBundle(filters.question),
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
            reranked = sorted(
                docs,
                key=lambda doc: doc.metadata.get("score", 0),
                reverse=True,
            )[:5]

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
            tavily_key = os.environ.get("TAVILY_API_KEY", "").strip()
            if not tavily_key:
                emit_telemetry(
                    node_name="WebSearchFallbackNode",
                    start_time=start_time,
                    state=state,
                    retrieval_source="web_skipped_missing_tavily",
                )
                return {"reranked_docs": [], "used_web": False}
            try:
                report = await asyncio.wait_for(
                    research_client.deep_research(query_str), timeout=10.0
                )
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
class EducationalSynthesizer(dspy.Signature):
    """Synthesize an educational response from retrieved documents.
    You MUST obey any constraints specified in the conversation (e.g., 'question 1 only', 'no solution').
    Write your output clearly in Arabic."""

    context: str = dspy.InputField(desc="The raw retrieved exercise or document text.")
    conversation: str = dspy.InputField(
        desc="The recent conversation history including the user's active constraints."
    )
    query: str = dspy.InputField(desc="The user's original query.")
    response: str = dspy.OutputField(
        desc="The final synthesized response in Arabic obeying all constraints."
    )


class SynthesizerNode:
    def __init__(self):
        self.generator = dspy.Predict(EducationalSynthesizer)

    async def __call__(self, state: dict) -> dict:
        import json

        from .telemetry import emit_telemetry

        start_time = time.time()
        reranked = state.get("reranked_docs", [])
        filters: QueryFilters = state.get("filters")
        query = state.get("query", "")
        messages = state.get("messages", [])

        recent_messages: list[str] = []
        for msg in messages[-6:]:
            content = getattr(msg, "content", None)
            if not isinstance(content, str) or not content.strip():
                continue
            role = getattr(msg, "type", getattr(msg, "role", "user"))
            prefix = "User: " if role in ("human", "user") else "Assistant: "
            text = content.strip()
            if text.startswith("{") and role in ("ai", "assistant"):
                try:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        extracted = data.get("الإجابة") or data.get("التمرين") or text
                        text = str(extracted)
                except Exception:
                    pass
            recent_messages.append(f"{prefix}{text}")

        conversation_text = "\n".join(recent_messages) if recent_messages else query

        if not reranked:
            text_val = "لا توجد تفاصيل متاحة."
            source = "لا يوجد"
            confidence = "0.00"
        else:
            raw_doc_text = reranked[0].text
            source = reranked[0].metadata.get("source", "الإنترنت")
            confidence = str(reranked[0].metadata.get("score", 0.85))

            try:
                prediction = await anyio.to_thread.run_sync(
                    lambda: self.generator(
                        context=raw_doc_text, conversation=conversation_text, query=query
                    )
                )
                text_val = getattr(prediction, "response", raw_doc_text).strip()
            except Exception as e:
                logger.error(f"Synthesizer LLM generation failed: {e}")
                text_val = raw_doc_text

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
        import json

        from langchain_core.messages import AIMessage

        return {
            "final_response": response_json,
            "messages": [AIMessage(content=json.dumps(response_json, ensure_ascii=False))],
        }
