import asyncio
import os
from operator import add
from typing import Annotated, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph


def _load_search_nodes() -> tuple[type, type, type, type, type]:
    """يحمّل عقد البحث عند توفر التبعيات ويعيد بدائل آمنة عند غيابها."""
    try:
        from .search import (
            InternalRetrieverNode,
            QueryAnalyzerNode,
            RerankerNode,
            SynthesizerNode,
            WebSearchFallbackNode,
        )

        return (
            QueryAnalyzerNode,
            InternalRetrieverNode,
            RerankerNode,
            WebSearchFallbackNode,
            SynthesizerNode,
        )
    except Exception:

        class _PassthroughNode:
            def __call__(self, state: dict) -> dict:
                return state

        return (
            _PassthroughNode,
            _PassthroughNode,
            _PassthroughNode,
            _PassthroughNode,
            _PassthroughNode,
        )


class AgentState(TypedDict):
    messages: Annotated[list[object], add]
    query: str
    intent: str
    filters: object
    retrieved_docs: list[object]
    reranked_docs: list[object]
    used_web: bool
    final_response: object
    tools_executed: bool


ADMIN_METRIC_TRIGGERS = {
    # Arabic
    "كم",
    "عدد",
    "احسب",
    "حساب",
    "كمية",
    "ملفات",
    "ملف",
    "بايثون",
    "جداول",
    "جدول",
    "مستخدمين",
    "مستخدم",
    "خدمات",
    "إحصائيات",
    # English
    "count",
    "how many",
    "total",
    "files",
    "tables",
    "users",
    "stats",
    "metrics",
    "services",
    "python",
}

CHAT_INTENT_TRIGGERS = {
    "السلام عليكم",
    "مرحبا",
    "اهلا",
    "أهلا",
    "هلا",
    "hello",
    "hi",
    "hey",
    "good morning",
    "good evening",
    "كيف حالك",
    "من أنت",
    "شكرا",
    "شكراً",
}


import re

ADMIN_PATTERNS = [
    r"(كم|عدد|احسب|حساب|كمية)\s*(عدد)?\s*(ملفات|ملف|بايثون)",
    r"(كم|عدد)\s*(عدد)?\s*(جداول|جدول|قاعدة البيانات)",
    r"(كم|عدد)\s*(عدد)?\s*(مستخدمين|مستخدم|الأعضاء)",
    r"(كم|عدد)\s*(عدد)?\s*(خدمات|الخدمات|microservices)",
    r"(إحصائيات|stats|metrics|system info|معلومات النظام)",
    r"(count|how many)\s*(files|tables|users|services|python)",
]


def emergency_intent_guard(query: str) -> bool:
    """
    DETERMINISTIC check BEFORE any LLM involvement.
    If True -> FORCE admin tool path, no exceptions.
    """
    query_lower = query.lower()
    # Require at least one exact match from the patterns to avoid trapping generic words
    return any(re.search(pattern, query_lower) for pattern in ADMIN_PATTERNS)


import dspy


def _configure_dspy() -> None:
    """يضبط نموذج DSPy عالميًا في مرحلة الإقلاع باستخدام مفاتيح البيئة المتاحة."""
    if dspy.settings.lm is not None:
        return

    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not openrouter_key:
        import logging

        logging.getLogger("graph").warning(
            "CRITICAL: DSPy LM configuration skipped because OPENROUTER_API_KEY is missing."
        )
        return

    try:
        lm = dspy.LM(
            model="openai/nvidia/nemotron-3-nano-30b-a3b:free",
            api_base="https://openrouter.ai/api/v1",
            api_key=openrouter_key,
        )
        dspy.settings.configure(lm=lm)
    except Exception as exc:
        import logging

        logging.getLogger("graph").warning(
            "CRITICAL: DSPy LM configuration failed; proceeding without LM. reason=%s", exc
        )


class IntentClassifier(dspy.Signature):
    """Classify if conversation needs admin system metrics, general chat/greetings, or educational search. If the user says a greeting (السلام عليكم, hello) or general chat, output is_chat=True. Follow-up questions about previous exercises/topics are educational searches, so is_chat=False."""

    conversation: str = dspy.InputField()
    is_admin: bool = dspy.OutputField(desc="True if conversation needs real system counts/metrics")
    is_chat: bool = dspy.OutputField(
        desc="True if conversation is a greeting, small talk, or general conversational chat (e.g. السلام عليكم, شكرا, مرحبا)"
    )
    confidence: float = dspy.OutputField()
    tool_needed: str = dspy.OutputField(desc="Which admin tool is needed")


class SupervisorNode:
    def __init__(self):
        self.dspy_classifier = dspy.ChainOfThought(IntentClassifier)

    async def __call__(self, state: AgentState) -> dict:
        """يوجّه النية بشكل غير حاجب للحلقة الحدثية مع أولوية للحراس الحتمية."""
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        query = state.get("query", "")
        import json

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

        if emergency_intent_guard(query):
            intent = "admin"
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return {"intent": intent}

        query_normalized = query.strip().lower()
        if any(trigger in query_normalized for trigger in CHAT_INTENT_TRIGGERS):
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return {"intent": "chat"}

        for pattern in ADMIN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "admin"}

        try:
            result = await asyncio.to_thread(self.dspy_classifier, conversation=conversation_text)
            try:
                conf = float(result.confidence)
            except (ValueError, TypeError):
                conf = 0.0

            if (
                hasattr(result, "is_admin")
                and str(result.is_admin).lower() == "true"
                and conf > 0.75
            ):
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "admin"}
            if hasattr(result, "is_chat") and str(result.is_chat).lower() == "true" and conf > 0.70:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "chat"}
        except Exception:
            pass

        if len(query_normalized.split()) <= 3 and "?" not in query_normalized and "؟" not in query:
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            return {"intent": "chat"}

        intent = "search"
        emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
        return {"intent": intent}


class ChatFallbackSignature(dspy.Signature):
    """صياغة رد محادثي طبيعي ومدروس للمحادثات العامة خارج مسارات البحث."""

    conversation: str = dspy.InputField()
    response: str = dspy.OutputField(desc="رد عربي طبيعي ومفيد للمستخدم")


class ChatFallbackNode:
    def __init__(self) -> None:
        self.generator = dspy.Predict(ChatFallbackSignature)

    async def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        import json

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

        conversation = "\n".join(recent_messages) if recent_messages else query
        fallback_response = (
            "وعليكم السلام! أنا هنا للمساعدة. أخبرني بما تحتاجه وسأتابع معك خطوة بخطوة."
        )
        try:
            prediction = await asyncio.to_thread(self.generator, conversation=conversation)
            model_response = getattr(prediction, "response", "")
            if isinstance(model_response, str) and model_response.strip():
                fallback_response = model_response.strip()
        except Exception as error:
            emit_telemetry(
                node_name="ChatFallbackNode",
                start_time=start_time,
                state=state,
                error=error,
            )

        emit_telemetry(node_name="ChatFallbackNode", start_time=start_time, state=state)
        return {
            "final_response": {
                "الإجابة": fallback_response,
                "المصدر": "chat_fallback",
            }
        }


class ToolExecutorNode:
    async def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        messages = state.get("messages", [])
        if not messages:
            emit_telemetry(node_name="ToolExecutorNode", start_time=start_time, state=state)
            return {"tools_executed": False}

        last_msg = messages[-1]
        results = []
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                from microservices.orchestrator_service.src.contracts.admin_tools import ADMIN_TOOLS

                for t in ADMIN_TOOLS:
                    if t.name == tc["name"]:
                        try:
                            if asyncio.iscoroutinefunction(t.invoke):
                                res = await t.ainvoke(tc["args"])
                            else:
                                res = t.invoke(tc["args"])
                            results.append(str(res))
                        except Exception as e:
                            results.append(f"Error: {e!s}")
                            emit_telemetry(
                                node_name="ToolExecutorNode",
                                start_time=start_time,
                                state=state,
                                error=e,
                            )

        emit_telemetry(
            node_name="ToolExecutorNode", start_time=start_time, state=state, tool_invoked=True
        )
        return {"final_response": "\n".join(results), "tools_executed": True}


class ValidatorNode:
    def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        emit_telemetry(node_name="ValidatorNode", start_time=start_time, state=state)
        return {}


def route_intent(state: AgentState) -> str:
    import logging

    logger = logging.getLogger("graph")
    intent = state.get("intent", "search")
    node = {
        "search": "query_analyzer",
        "admin": "admin_agent",
        "tool": "tool_executor",
        "chat": "chat_fallback",
    }.get(intent, "query_analyzer")
    logger.info(f"SUPERVISOR_NODE → routing to → {node}")
    return intent


def check_results(state: AgentState) -> str:
    docs = state.get("reranked_docs", [])
    return "found" if len(docs) > 0 else "not_found"


def check_quality(state: AgentState) -> str:
    return "pass"


def create_unified_graph(admin_app=None):
    _configure_dspy()
    graph = StateGraph(AgentState)

    (
        query_analyzer_node,
        internal_retriever_node,
        reranker_node,
        web_search_fallback_node,
        synthesizer_node,
    ) = _load_search_nodes()

    from .admin import AdminAgentNode

    graph.add_node("supervisor", SupervisorNode())
    graph.add_node("query_analyzer", query_analyzer_node())
    graph.add_node("retriever", internal_retriever_node())
    graph.add_node("reranker", reranker_node())
    graph.add_node("web_fallback", web_search_fallback_node())
    graph.add_node("admin_agent", AdminAgentNode(admin_app=admin_app))
    graph.add_node("tool_executor", ToolExecutorNode())
    graph.add_node("chat_fallback", ChatFallbackNode())
    graph.add_node("synthesizer", synthesizer_node())
    graph.add_node("validator", ValidatorNode())

    graph.add_conditional_edges(
        "supervisor",
        route_intent,
        {
            "search": "query_analyzer",
            "admin": "admin_agent",
            "tool": "tool_executor",
            "chat": "chat_fallback",
        },
    )

    graph.add_edge("query_analyzer", "retriever")
    graph.add_edge("retriever", "reranker")
    graph.add_conditional_edges(
        "reranker", check_results, {"found": "synthesizer", "not_found": "web_fallback"}
    )

    graph.add_edge("web_fallback", "synthesizer")
    graph.add_edge("admin_agent", "validator")
    graph.add_edge(
        "tool_executor", "validator"
    )  # tool_executor -> validator directly, bypassing synthesizer to not break admin outputs
    graph.add_edge("chat_fallback", "validator")
    graph.add_edge("synthesizer", "validator")

    graph.add_conditional_edges("validator", check_quality, {"pass": END, "fail": "supervisor"})

    graph.set_entry_point("supervisor")
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)
