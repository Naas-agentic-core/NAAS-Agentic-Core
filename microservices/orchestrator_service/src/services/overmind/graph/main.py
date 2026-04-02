import asyncio
import json
import logging
import os
import re
from operator import add
from typing import Annotated, TypedDict

import dspy
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

ADMIN_PATTERNS = [
    r"(كم|عدد|احسب|حساب|كمية)\s*(عدد)?\s*(ملفات|ملف|بايثون)",
    r"(كم|عدد)\s*(عدد)?\s*(جداول|جدول|قاعدة البيانات)",
    r"(كم|عدد)\s*(عدد)?\s*(مستخدمين|مستخدم|الأعضاء)",
    r"(كم|عدد)\s*(عدد)?\s*(خدمات|الخدمات|microservices)",
    r"(إحصائيات|stats|metrics|system info|معلومات النظام)",
    r"(count|how many)\s*(files|tables|users|services|python)",
]


ARABIC_ANAPHORA = [
    "ها",
    "ه",
    "هم",
    "هن",
    "هذا",
    "هذه",
    "ذلك",
    "تلك",
    "فيها",
    "منها",
    "عنها",
    "لها",
    "بها",
    "عليها",
    "إليها",
    "فيه",
    "منه",
    "عنه",
    "له",
    "به",
    "عليه",
    "إليه",
    "السابق",
    "السابقة",
    "نفس",
    "أيضاً",
    "أيضا",
    "كذلك",
    "المذكور",
    "المذكورة",
    "أكثر",
    "المزيد",
    "آخر",
    "أخرى",
    "وماذا عن",
    "اشرح أكثر",
]
ENGLISH_ANAPHORA = [
    "it",
    "its",
    "they",
    "them",
    "their",
    "this",
    "that",
    "those",
    "these",
    "the same",
    "previous",
    "above",
    "more",
    "another",
    "also",
    "further",
    "what about",
    "tell me more",
    "explain further",
]
# CONTEXT_FIX: فواعل الضمائر المتصلة الأكثر شيوعًا في العربية للكشف المورفولوجي.
ARABIC_PRONOUN_SUFFIXES = ["ها", "ه", "هم", "هن", "هما", "كم", "كن", "نا"]
SHORT_QUERY_THRESHOLD = 6
ELLIPTICAL_STARTERS = {
    "ما",
    "ماذا",
    "أي",
    "اي",
    "من",
    "أين",
    "متى",
    "كم",
    "كيف",
    "لماذا",
    "هل",
    "where",
    "what",
    "how",
    "why",
    "which",
}
ELLIPTICAL_TERMS = {
    "العاصمة",
    "تمرين",
    "تمرينًا",
    "تمرينا",
    "شرح",
    "exercise",
    "capital",
    "example",
    "details",
}


def build_conversation_context(
    messages: list[object],
    max_turns: int = 6,
    include_json_extraction: bool = True,
) -> str:
    # CONTEXT_FIX: توحيد بناء سجل المحادثة لكل العقد التي تعتمد على السياق.
    """يبني تمثيلًا نصيًا متينًا للسياق الأخير دون رمي استثناءات."""
    if not messages:
        return ""

    recent_messages: list[str] = []
    last_signature: tuple[str, str] | None = None
    for msg in messages[-max_turns:]:
        content = getattr(msg, "content", None)
        if not isinstance(content, str) or not content.strip():
            continue
        role = getattr(msg, "type", getattr(msg, "role", "user"))
        prefix = "User: " if role in ("human", "user") else "Assistant: "
        text = content.strip()
        if include_json_extraction and text.startswith("{") and role in ("ai", "assistant"):
            try:
                data = json.loads(text)
                if isinstance(data, dict):
                    extracted = data.get("الإجابة") or data.get("التمرين") or text
                    text = str(extracted)
            except Exception:
                pass
        signature = (prefix, text)
        if signature == last_signature:
            continue
        recent_messages.append(f"{prefix}{text}")
        last_signature = signature

    return "\n".join(recent_messages)


def _tokenize_query(query: str) -> list[str]:
    # CONTEXT_FIX: توحيد تقسيم النص لتفادي المطابقة الجزئية الخاطئة.
    """يقسّم النص إلى كلمات/رموز دلالية منخفضة المخاطر للمطابقة القاموسية."""
    normalized = query.casefold()
    tokens = re.findall(r"[^\W_]+", normalized, flags=re.UNICODE)
    return [token for token in tokens if token]


def _contains_compound_indicator(query: str, indicators: list[str]) -> bool:
    # CONTEXT_FIX: كشف العبارات متعددة الكلمات مع حدود كلمة صريحة.
    """يتحقق من وجود عبارات كاملة مع حدود كلمة لتجنّب الإيجابيات الكاذبة."""
    normalized = query.casefold()
    for indicator in indicators:
        if " " not in indicator and "\t" not in indicator:
            continue
        escaped_indicator = re.escape(indicator.casefold())
        if re.search(rf"(?<!\w){escaped_indicator}(?!\w)", normalized):
            return True
    return False


def _contains_anaphora_indicator(query: str) -> bool:
    # CONTEXT_FIX: كشف الضمائر والإشارات دون الاعتماد على احتواء جزئي خطِر.
    """يكشف مؤشرات الإحالة المرجعية العربية والإنجليزية بشكل حذر ودقيق."""
    tokens = _tokenize_query(query)
    if not tokens:
        return False

    token_set = set(tokens)
    arabic_token_indicators = {item for item in ARABIC_ANAPHORA if " " not in item}
    english_token_indicators = {item for item in ENGLISH_ANAPHORA if " " not in item}

    if token_set.intersection(arabic_token_indicators):
        return True
    if token_set.intersection(english_token_indicators):
        return True
    if _contains_compound_indicator(query=query, indicators=ARABIC_ANAPHORA):
        return True
    return _contains_compound_indicator(query=query, indicators=ENGLISH_ANAPHORA)


def _looks_elliptical_followup(query: str, history: str) -> bool:
    # CONTEXT_FIX: تقليل إعادة الصياغة العدوانية للاستعلامات القصيرة غير الغامضة.
    """يكتشف الأسئلة القصيرة المرجّح اعتمادها على سياق سابق دون إفراط في التحفيز."""
    if not history.strip():
        return False
    tokens = _tokenize_query(query)
    if not tokens or len(tokens) > SHORT_QUERY_THRESHOLD:
        return False

    first_token = tokens[0]
    contains_elliptical_term = bool(set(tokens).intersection(ELLIPTICAL_TERMS))
    return (first_token in ELLIPTICAL_STARTERS) or contains_elliptical_term


def emergency_intent_guard(query: str) -> bool:
    """
    DETERMINISTIC check BEFORE any LLM involvement.
    If True -> FORCE admin tool path, no exceptions.
    """
    query_lower = query.lower()
    # Require at least one exact match from the patterns to avoid trapping generic words
    return any(re.search(pattern, query_lower) for pattern in ADMIN_PATTERNS)


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
        messages = state.get("messages", [])
        conversation_text = build_conversation_context(messages=messages) or query

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

        if (
            len(query_normalized.split()) <= 3
            and "?" not in query_normalized
            and "؟" not in query
            and not _looks_elliptical_followup(query, conversation_text)
        ):
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
        query = state.get("query", "")
        messages = state.get("messages", [])
        conversation = build_conversation_context(messages=messages) or query
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


class QueryRewriterSignature(dspy.Signature):
    # CONTEXT_FIX: توقيع مقيد بقواعد صارمة لضمان إعادة كتابة آمنة ومختصرة.
    """Rewrite the current query into a self-contained standalone query.

    Rules:
    1) Resolve pronouns and implicit references using conversation history only.
    2) Preserve user intent exactly; do not answer or expand semantics.
    3) Keep the same user language (Arabic/English/mixed).
    4) If the query is already self-contained, return it unchanged.
    5) Keep rewrite concise and free of transcript labels.
    """

    conversation_history: str = dspy.InputField(
        desc="Recent turns formatted as User/Assistant transcript"
    )
    current_query: str = dspy.InputField(desc="Current possibly ambiguous user query")
    rewritten_query: str = dspy.OutputField(
        desc="Self-contained rewritten query or unchanged original query"
    )


class QueryRewriterNode:
    # CONTEXT_FIX: عقدة حل إحالات ضميرية مع بوابة سريعة + fallback آمن.
    def __init__(self) -> None:
        self.rewriter = dspy.ChainOfThought(QueryRewriterSignature)
        self.logger = logging.getLogger("graph")

    def _needs_rewrite(self, query: str, messages: list[object]) -> bool:
        # CONTEXT_FIX: بوابة حتمية سريعة تمنع استدعاء LLM عند عدم الحاجة.
        """يحدد إذا كان السؤال يحتاج إعادة صياغة مرجعية قبل البحث."""
        if not query.strip() or not messages:
            return False

        query_words = _tokenize_query(query)
        for word in query_words:
            for suffix in ARABIC_PRONOUN_SUFFIXES:
                if word.endswith(suffix) and len(word) > len(suffix) + 1:
                    return True

        if _contains_anaphora_indicator(query=query):
            return True

        history = build_conversation_context(messages=messages)
        if _looks_elliptical_followup(query=query, history=history):
            return True

        return len(query_words) <= 5 and bool(history.strip())

    def _is_valid_rewrite(
        self,
        original_query: str,
        rewritten_query: str,
        conversation_history: str,
    ) -> bool:
        # CONTEXT_FIX: تحقق صارم لمنع تسريب صيغة السجل أو التضخم غير المبرر.
        """يتحقق من صلاحية إعادة الصياغة قبل تمريرها لعقد التحليل."""
        candidate = rewritten_query.strip()
        original = original_query.strip()
        if not candidate:
            return False
        if candidate in conversation_history:
            return False
        if len(candidate) > max(24, len(original) * 3):
            return False
        return "User:" not in candidate and "Assistant:" not in candidate

    def _extract_latest_reference_snippet(self, messages: list[object]) -> str:
        """يستخرج آخر رسالة مرجعية غير فارغة لتثبيت الإحالة الضميرية عند الفشل."""
        if not messages:
            return ""

        for message in reversed(messages):
            role = getattr(message, "type", getattr(message, "role", ""))
            content = getattr(message, "content", "")
            if role not in {"human", "user", "ai", "assistant"}:
                continue
            if not isinstance(content, str):
                continue
            text = content.strip()
            if not text:
                continue
            if len(text) > 220:
                return text[:220].strip()
            return text
        return ""

    def _build_contextual_fallback_rewrite(self, query: str, messages: list[object]) -> str:
        """يبني إعادة صياغة حتمية عند تعذر إعادة الصياغة الذكية لمنع عمى السياق."""
        reference = self._extract_latest_reference_snippet(messages=messages)
        if not reference:
            return query

        lowered = query.casefold()
        if any(token in lowered for token in ["capital", "عاصمة"]):
            return f"اعتمادًا على هذا السياق: {reference}\nالسؤال الحالي: {query}"

        if _contains_anaphora_indicator(query=query) or _looks_elliptical_followup(
            query=query,
            history=build_conversation_context(messages=messages),
        ):
            return f"بالرجوع إلى آخر سياق في نفس المحادثة: {reference}\nالسؤال: {query}"
        return query

    async def __call__(self, state: AgentState) -> dict:
        # CONTEXT_FIX: تنفيذ غير حاجب مع fallback آمن إلى السؤال الأصلي.
        """يعيد كتابة السؤال الغامض إلى صيغة مستقلة قبل دخوله مسار البحث."""
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        query = str(state.get("query", "")).strip()
        messages = state.get("messages", [])
        if not query or len(messages) <= 1:
            emit_telemetry(node_name="QueryRewriterNode", start_time=start_time, state=state)
            return {"query": query}

        if not self._needs_rewrite(query=query, messages=messages):
            emit_telemetry(node_name="QueryRewriterNode", start_time=start_time, state=state)
            return {"query": query}

        history = build_conversation_context(messages=messages)
        if not history.strip():
            emit_telemetry(node_name="QueryRewriterNode", start_time=start_time, state=state)
            return {"query": query}

        rewritten_query = query
        try:
            result = await asyncio.to_thread(
                self.rewriter,
                conversation_history=history,
                current_query=query,
            )
            candidate = getattr(result, "rewritten_query", "")
            if isinstance(candidate, str) and self._is_valid_rewrite(query, candidate, history):
                rewritten_query = candidate.strip()
        except Exception as error:
            self.logger.debug("QueryRewriterNode fallback to original query: %s", error)
            emit_telemetry(
                node_name="QueryRewriterNode",
                start_time=start_time,
                state=state,
                error=error,
            )
            return {
                "query": self._build_contextual_fallback_rewrite(query=query, messages=messages)
            }

        if rewritten_query == query:
            rewritten_query = self._build_contextual_fallback_rewrite(
                query=query, messages=messages
            )

        emit_telemetry(node_name="QueryRewriterNode", start_time=start_time, state=state)
        return {"query": rewritten_query}


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
        "search": "query_rewriter",
        "admin": "admin_agent",
        "tool": "tool_executor",
        "chat": "chat_fallback",
    }.get(intent, "query_rewriter")
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
    graph.add_node("query_rewriter", QueryRewriterNode())
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
            "search": "query_rewriter",
            "admin": "admin_agent",
            "tool": "tool_executor",
            "chat": "chat_fallback",
        },
    )

    graph.add_edge("query_rewriter", "query_analyzer")
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
    return graph.compile()
