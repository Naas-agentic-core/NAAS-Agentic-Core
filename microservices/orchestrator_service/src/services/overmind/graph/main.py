import asyncio
import json
import logging
import os
import re
from operator import add
from types import SimpleNamespace
from typing import Annotated, TypedDict

from langgraph.graph import END, StateGraph

try:
    import dspy
except ModuleNotFoundError:

    def _dspy_input_field(*_: object, **__: object) -> str:
        return ""

    def _dspy_output_field(*_: object, **__: object) -> str:
        return ""

    def _dspy_chain_of_thought(*_: object, **__: object):
        def _runner(**_: object) -> SimpleNamespace:
            return SimpleNamespace(
                is_admin=False,
                is_chat=False,
                confidence=0.0,
                tool_needed="",
                rewritten_query="",
            )

        return _runner

    def _dspy_predict(*_: object, **__: object):
        def _runner(**_: object) -> SimpleNamespace:
            return SimpleNamespace(response="")

        return _runner

    class _DSPySettings:
        def __init__(self) -> None:
            self.lm: object | None = None

        def configure(self, *, lm: object | None = None) -> None:
            self.lm = lm

    class _DSPySignature:
        pass

    class _DSPyModule:
        class LM:
            def __init__(self, **_: object) -> None:
                pass

        Signature = _DSPySignature
        settings = _DSPySettings()
        InputField = staticmethod(_dspy_input_field)
        OutputField = staticmethod(_dspy_output_field)
        ChainOfThought = staticmethod(_dspy_chain_of_thought)
        Predict = staticmethod(_dspy_predict)

    dspy = _DSPyModule()  # type: ignore[assignment]

logger = logging.getLogger(__name__)


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
    retry_count: int


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


def format_conversation_history(messages: list[object]) -> str:
    """Formats the entire messages list into a readable string dialogue."""
    return build_conversation_context(messages, max_turns=24)


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
        if isinstance(msg, dict):
            content = msg.get("content")
            role = msg.get("role") or msg.get("type") or "user"
        else:
            content = getattr(msg, "content", None)
            role = getattr(msg, "type", getattr(msg, "role", "user"))

        if not isinstance(content, str) or not content.strip():
            continue

        role = str(role).lower().strip()

        if role in {"assistant", "ai"}:
            prefix = "Assistant: "
        elif role in {"human", "user"}:
            prefix = "User: "
        elif role == "system":
            prefix = "System: "
        else:
            prefix = "User: "

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


def _extract_recent_entity_anchor(messages: list[object]) -> str | None:
    """يستخرج مرساة كيان حديثة من رسائل المستخدم لتوسيع الأسئلة الإحالية."""
    stop_words = {
        "ما",
        "ماذا",
        "من",
        "هي",
        "هو",
        "في",
        "على",
        "عن",
        "هل",
        "كم",
        "أين",
        "متى",
        "كيف",
        "لماذا",
        "تقع",
        "عاصمة",
        "عاصمتها",
        "عاصمته",
    }
    for message in reversed(messages[:-1]):
        role = getattr(message, "type", getattr(message, "role", "user"))
        if role not in {"human", "user"}:
            continue
        content = str(getattr(message, "content", "")).strip(" ؟?.,!؛:")
        if not content:
            continue
        tokens = _tokenize_query(content)
        candidates = [
            token
            for token in tokens
            if len(token) > 2 and token not in stop_words and not token.endswith(("ها", "هم", "هن"))
        ]
        if candidates:
            return candidates[-1]
    return None


def _rewrite_with_entity_anchor(query: str, anchor: str) -> str:
    """يعيد كتابة السؤال الإحالي بصيغة صريحة تحافظ على نية المستخدم."""
    normalized = query.strip()
    if not normalized:
        return normalized

    replacements = {
        "عاصمتها": f"عاصمة {anchor}",
        "عاصمته": f"عاصمة {anchor}",
        "عاصمتهم": f"عاصمة {anchor}",
        "عاصمتها؟": f"عاصمة {anchor}؟",
    }
    rewritten = normalized
    for source, target in replacements.items():
        rewritten = rewritten.replace(source, target)

    if rewritten != normalized:
        return rewritten
    return f"{normalized} (المقصود: {anchor})"


def _resolve_query_from_history(query: str, messages: list[object]) -> str:
    """يفك الإحالة الضميرية باستخدام سياق المحادثة قبل المرور لمسار الإجابة النهائي."""
    normalized = query.strip()
    if not normalized:
        return normalized
    query_tokens = _tokenize_query(normalized)
    has_pronoun_suffix = any(
        token.endswith(suffix) and len(token) > len(suffix) + 1
        for token in query_tokens
        for suffix in ARABIC_PRONOUN_SUFFIXES
    )
    if not _contains_anaphora_indicator(normalized) and not has_pronoun_suffix:
        return normalized

    anchor = _extract_recent_entity_anchor(messages)
    if not anchor:
        return normalized
    return _rewrite_with_entity_anchor(normalized, anchor)


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
        dspy_model = os.getenv(
            "OPENROUTER_DSPY_MODEL", "nvidia/nemotron-3-super-120b-a12b:free"
        ).strip()
        if not dspy_model.startswith("openai/"):
            dspy_model = f"openai/{dspy_model}"
        lm = dspy.LM(
            model=dspy_model,
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
    """Classify if conversation needs admin system metrics, general chat/greetings, general knowledge, or educational search.
    educational: ONLY BAC exercises, school curriculum, exams.
    general_knowledge: Includes ALL factual questions including follow-ups that depend on history (e.g., pronouns like 'عاصمتها').
    admin: system metrics, service counts, operational information.
    chat: Only greetings and small talk. NEVER factual questions.
    Classify by DOMAIN, not by whether it is a follow-up.
    """

    history: str = dspy.InputField(
        desc="Previous conversation context to resolve pronouns and context"
    )
    question: str = dspy.InputField(
        desc="If the question contains pronouns or implicit entities, you MUST resolve them using history BEFORE classification."
    )
    resolved_question: str = dspy.OutputField(
        desc="The question rewritten with pronouns resolved using history"
    )
    intent: str = dspy.OutputField(desc="One of: educational, general_knowledge, admin, chat")
    confidence: float = dspy.OutputField()


class SupervisorNode:
    def __init__(self):
        self.dspy_classifier = dspy.ChainOfThought(IntentClassifier)

    async def __call__(self, state: AgentState) -> dict:
        """يوجّه النية بشكل غير حاجب للحلقة الحدثية مع أولوية للحراس الحتمية."""
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()

        # State Safety: Prevent query overwrite without backup
        if "original_query" not in state:
            # But wait, we can only update the state by returning a dict.
            # Mutating `state` directly doesn't persist the change unless it is returned.
            pass

        query = str(state.get("query", "")).strip()
        print("NODE:", "SupervisorNode")
        print("QUERY:", query)
        messages = state.get("messages", [])
        formatted_history = format_conversation_history(messages[:-1])
        resolved_q = _resolve_query_from_history(query=query, messages=messages)
        if resolved_q != query:
            print("RESOLVED QUERY:", resolved_q)
        query = resolved_q

        if emergency_intent_guard(query):
            intent = "admin"
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            updates = {"intent": intent, "query": query}
            if "original_query" not in state:
                updates["original_query"] = state.get("query", "")
            return updates

        query_normalized = query.strip().lower()
        if any(trigger in query_normalized for trigger in CHAT_INTENT_TRIGGERS):
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            updates = {"intent": "chat", "query": query}
            if "original_query" not in state:
                updates["original_query"] = state.get("query", "")
            return updates

        for pattern in ADMIN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "admin", "query": query}

        try:
            result = await asyncio.to_thread(
                self.dspy_classifier, history=formatted_history, question=query
            )
            try:
                conf = float(result.confidence)
            except (ValueError, TypeError):
                conf = 0.0

            if hasattr(result, "resolved_question") and result.resolved_question:
                resolved_q = result.resolved_question

            pred_intent = getattr(result, "intent", "").lower().strip()

            if pred_intent == "admin" and conf > 0.75:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                updates = {"intent": "admin", "query": resolved_q}
                if "original_query" not in state:
                    updates["original_query"] = state.get("query", "")
                return updates
            if pred_intent == "general_knowledge" and conf > 0.60:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                updates = {"intent": "general_knowledge", "query": resolved_q}
                if "original_query" not in state:
                    updates["original_query"] = state.get("query", "")
                return updates
            if pred_intent == "chat" and conf > 0.65:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                updates = {"intent": "chat", "query": resolved_q}
                if "original_query" not in state:
                    updates["original_query"] = state.get("query", "")
                return updates
            if pred_intent == "educational" and conf > 0.55:
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                updates = {"intent": "educational", "query": resolved_q}
                if "original_query" not in state:
                    updates["original_query"] = state.get("query", "")
                return updates

        except Exception:
            pass

        if (
            len(query_normalized.split()) <= 3
            and "?" not in query_normalized
            and "؟" not in query
            and not _looks_elliptical_followup(query, formatted_history)
        ):
            emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
            updates = {"intent": "chat", "query": query}
            if "original_query" not in state:
                updates["original_query"] = state.get("query", "")
            return updates

        intent = "general_knowledge"
        emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
        updates = {"intent": intent, "query": query}
        if "original_query" not in state:
            updates["original_query"] = state.get("query", "")
        return updates


class ChatFallbackSignature(dspy.Signature):
    """صياغة رد محادثي طبيعي ومدروس للمحادثات العامة خارج مسارات البحث."""

    history: str = dspy.InputField(
        desc="Previous conversation context to resolve pronouns and context"
    )
    question: str = dspy.InputField()
    response: str = dspy.OutputField(desc="رد عربي طبيعي ومفيد للمستخدم")


class ChatFallbackNode:
    def __init__(self) -> None:
        self.generator = dspy.Predict(ChatFallbackSignature)

    async def __call__(self, state: AgentState) -> dict:
        import time

        from microservices.orchestrator_service.src.core.ai_gateway import get_ai_client

        from .telemetry import emit_telemetry

        start_time = time.time()
        messages = state.get("messages", [])

        query = state.get("query")
        if not query and messages:
            query = messages[-1].content
        query = str(query or "").strip()

        history = format_conversation_history(messages[:-1] if messages else [])

        if not history.strip():
            print("🚨 FAILURE: EMPTY HISTORY")

        if "ها" in query and "فرنسا" not in query:
            print("🚨 PRONOUN LEAK DETECTED")

        if "فرنسا" not in history:
            print("🚨 ENTITY LOST IN HISTORY")

        print("=== FINAL LLM INPUT ===")
        print("HISTORY:", history)
        print("QUERY:", query)

        ai_client = get_ai_client()

        system_content = "أجب بدقة اعتماداً على سياق المحادثة. لا تتجاهل السياق أبداً."
        user_content = f"السياق:\n{history}\n\nالسؤال:\n{query}"

        fallback_response = (
            "وعليكم السلام! أنا هنا للمساعدة. أخبرني بما تحتاجه وسأتابع معك خطوة بخطوة."
        )

        try:
            response_content = await ai_client.send_message(
                system_prompt=system_content, user_message=user_content, temperature=0.7
            )
            if response_content and isinstance(response_content, str) and response_content.strip():
                fallback_response = response_content.strip()
        except Exception as error:
            emit_telemetry(
                node_name="ChatFallbackNode",
                start_time=start_time,
                state=state,
                error=error,
            )

        emit_telemetry(node_name="ChatFallbackNode", start_time=start_time, state=state)

        from langchain_core.messages import AIMessage

        return {
            "final_response": fallback_response,
            "messages": [AIMessage(content=fallback_response)],
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

        for message in reversed(
            messages[:-1]
        ):  # exclude the last message which is the current query
            role = getattr(message, "type", getattr(message, "role", ""))
            content = getattr(message, "content", "")
            if role not in {"human", "user", "ai", "assistant"}:
                continue

            # Try extracting from structured kwargs first
            additional = getattr(message, "additional_kwargs", {})
            if isinstance(additional, dict) and "structured" in additional:
                structured = additional["structured"]
                if isinstance(structured, dict):
                    text = structured.get("الإجابة") or str(structured)
                    if text and len(text) <= 220:
                        return text[:220].strip()

            if not isinstance(content, str):
                continue
            text = content.strip()
            # Context blindness fix: try extracting the core text if the response was JSON-encoded by LangGraph
            if text.startswith("{") and role in {"ai", "assistant"}:
                try:
                    data = json.loads(text)
                    if isinstance(data, dict):
                        extracted = data.get("الإجابة") or data.get("التمرين") or text
                        text = str(extracted).strip()
                except Exception:
                    pass
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
        print("NODE:", "QueryRewriterNode")
        print("QUERY:", query)
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
        print("NODE:", "ToolExecutorNode")
        print("QUERY:", str(state.get("query", "")).strip())
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
        from langchain_core.messages import AIMessage

        return {
            "final_response": "\n".join(results),
            "tools_executed": True,
            "messages": [AIMessage(content="\n".join(results))],
        }


class ValidatorNode:
    def __call__(self, state: AgentState) -> dict:
        """يتحقق من اكتمال الحالة ويعيد تحديثًا غير فارغ لتلبية عقدة LangGraph."""
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        print("NODE:", "ValidatorNode")
        print("QUERY:", str(state.get("query", "")).strip())

        updates: dict[str, object] = {"tools_executed": bool(state.get("tools_executed", False))}

        final_response = state.get("final_response")
        is_failure = False
        if not final_response:
            is_failure = True
        elif isinstance(final_response, str):
            response_lower = final_response.lower()
            failure_phrases = ["لم أفهم", "يرجى التوضيح", "لا أستطيع"]
            if (
                any(phrase in response_lower for phrase in failure_phrases)
                or not response_lower.strip()
            ):
                is_failure = True

        retry_count = state.get("retry_count", 0)
        if is_failure:
            if retry_count >= 1:
                updates["final_response"] = "عذراً، لم أتمكن من معالجة السياق."
                updates["retry_count"] = retry_count
            else:
                updates["retry_count"] = retry_count + 1

        emit_telemetry(node_name="ValidatorNode", start_time=start_time, state=state)
        return updates


def route_intent(state: AgentState) -> str:
    import logging

    logger = logging.getLogger("graph")
    intent = state.get("intent", "educational")

    if intent == "search":
        intent = "educational"

    node = {
        "educational": "query_rewriter",
        "admin": "admin_agent",
        "tool": "tool_executor",
        "chat": "chat_fallback",
        "general_knowledge": "general_knowledge",
    }.get(intent, "query_rewriter")
    logger.info(f"SUPERVISOR_NODE → routing to → {node}")
    return intent


def check_results(state: AgentState) -> str:
    docs = state.get("reranked_docs", [])
    if len(docs) > 0:
        return "found"
    intent = state.get("intent", "")
    if intent == "educational":
        return "web_fallback"
    return "general_knowledge"


def check_quality(state: AgentState) -> str:
    final_response = state.get("final_response")
    if not final_response:
        return "fail"

    if isinstance(final_response, str):
        response_lower = final_response.lower()
        failure_phrases = ["لم أفهم", "يرجى التوضيح", "لا أستطيع"]
        if (
            any(phrase in response_lower for phrase in failure_phrases)
            or not response_lower.strip()
        ):
            return "fail"

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
    from .general_knowledge import GeneralKnowledgeNode

    graph.add_node("supervisor", SupervisorNode())
    graph.add_node("query_rewriter", QueryRewriterNode())
    graph.add_node("query_analyzer", query_analyzer_node())
    graph.add_node("retriever", internal_retriever_node())
    graph.add_node("reranker", reranker_node())
    graph.add_node("web_fallback", web_search_fallback_node())
    graph.add_node("admin_agent", AdminAgentNode(admin_app=admin_app))
    graph.add_node("tool_executor", ToolExecutorNode())
    graph.add_node("chat_fallback", ChatFallbackNode())
    graph.add_node("general_knowledge", GeneralKnowledgeNode())
    graph.add_node("synthesizer", synthesizer_node())
    graph.add_node("validator", ValidatorNode())

    graph.add_conditional_edges(
        "supervisor",
        route_intent,
        {
            "educational": "query_rewriter",
            "admin": "admin_agent",
            "tool": "tool_executor",
            "chat": "chat_fallback",
            "general_knowledge": "general_knowledge",
        },
    )

    graph.add_edge("query_rewriter", "query_analyzer")
    graph.add_edge("query_analyzer", "retriever")
    graph.add_edge("retriever", "reranker")
    graph.add_conditional_edges(
        "reranker",
        check_results,
        {
            "found": "synthesizer",
            "web_fallback": "web_fallback",
            "general_knowledge": "general_knowledge",
        },
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

    # Use global postgres checkpointer if available, otherwise compile without it
    from microservices.orchestrator_service.src.core.database import get_checkpointer

    checkpointer = get_checkpointer()
    if checkpointer:
        logger.info("[CHECKPOINTER] LangGraph compiled with Postgres checkpointer.")
        return graph.compile(checkpointer=checkpointer)

    logger.warning(
        "[CHECKPOINTER] LangGraph compiled without checkpointer; state continuity relies on injected history."
    )
    return graph.compile()
