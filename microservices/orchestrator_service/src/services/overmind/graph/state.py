"""AgentState + intent constants + history helpers — sliced verbatim from graph/main.py (D-173 Stage 2c).

نمط D-164/D-168: كل شريحة تُضاف لـ GRAPH_SOURCE_FILES؛ main.py يعيد التصدير
(noqa F401) فيبقى monkeypatch على `graph.main.<name>` والاستيراد الخارجي فعّالاً.
"""

import json
import re
from operator import add
from typing import Annotated, TypedDict


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
    # D-103: محتوى تمرين محقون من الـ monolith (شرح-بسياق عبر الرسم).
    # عند وجوده: supervisor يفرض educational، retriever يتجاوز البحث الدلالي
    # ويستخدم هذا المحتوى كمصدر وحيد — لا vector DB ولا خلط تمارين.
    exercise_content: str
    # D-115: درجة سُلّم الدعم (1..5، افتراض 5/محجوب) — تحكم عمق التلميح السقراطي
    # في SynthesizerNode (لا كشف، لا مثال موازٍ). يَعكِس D-114 (worked_example_directive مُزال).
    support_level: int
    # D-171 (ISS-132): هوية الإدمن المشتقة من JWT الموقَّع عبر `_coerce_admin_state`
    # (least-privilege + fail-closed — تُحقن فقط حين `_is_admin_payload`). LangGraph
    # يُسقط المفاتيح غير المُصرَّحة، فبدون تصريحها هنا كانت تسقط قبل وصول
    # `AdminAgentNode` → `ValidateAccessNode` ⇒ الأداة تُنفَّذ ثم تُرفض ADMIN_ACCESS_DENIED.
    is_admin: bool
    user_role: str
    scope: str
    # ISS-200 (D-288): الدور لم يُجب لأن سلسلة النماذج سقطت كلها — لا لأن المعلومة
    # غير موجودة. مُصرَّح هنا كي لا يُسقطه LangGraph، فتراه المراقبة والاختبارات
    # الحيّة (و`/health`) بدل أن يضيع خلف نصٍّ جاهز يبدو كإجابة.
    provider_error: bool


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


def get_message_content(message: object) -> str:
    """Safely extracts content from dict or object messages."""
    if isinstance(message, dict):
        return str(message.get("content", "") or "")
    return str(getattr(message, "content", "") or "")


def get_message_role(message: object) -> str:
    """Safely extracts and normalizes role from dict or object messages."""
    if isinstance(message, dict):
        role = message.get("role") or message.get("type") or "user"
    else:
        role = getattr(message, "type", getattr(message, "role", "user"))

    role = str(role).lower().strip()
    if role in {"human", "user"}:
        return "user"
    if role in {"ai", "assistant"}:
        return "assistant"
    if role == "system":
        return "system"
    return "user"


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
        content = get_message_content(msg)
        role = get_message_role(msg)

        if not content.strip():
            continue

        if role == "assistant":
            prefix = "Assistant: "
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
    for message in reversed(messages):
        role = get_message_role(message)
        if role != "user":
            continue
        content = get_message_content(message).strip(" ؟?.,!؛:")
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
