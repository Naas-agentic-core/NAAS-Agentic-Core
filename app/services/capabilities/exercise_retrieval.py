"""
قدرة استرجاع التمارين التعليمية — نظام موحد ومنظم.

يعتمد هذا النظام على فهرس مركزي (knowledge_index.py) لاستدعاء التمارين
بدقة عالية بدلاً من البحث العشوائي في الملفات.

المبدأ: كل تمرين له هوية فريدة (سنة + دورة + موضوع + رقم التمرين).
الاستدعاء يكون دائماً بمعايير محددة، لا بكلمات مفتاحية عشوائية.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import ClassVar

from pydantic import Field

from app.core.schemas import RobustBaseModel
from app.services.capabilities.arabic_normalize import (
    normalize_ar,
    primary_canonical_topic,
)
from app.services.capabilities.knowledge_index import (
    ExerciseEntry,
    find_best_match,
    search_exercises,
)
from shared.exercise_scope import (
    EXPLANATION_CANCEL_MARKERS,
    extract_target,
    resolve_scope,
)
from shared.intent import markers_for

# ─────────────────────────────────────────────────────────────────────────────
# أنماط النية السلبية — تشير إلى أن المستخدم يريد شرحاً أو مساعدة وليس جلب محتوى.
# عند وجود أي منها، يُلغى الاسترجاع حتى لو ذُكرت كلمة "تمرين".
# ─────────────────────────────────────────────────────────────────────────────
#: **الطالب يملك المحتوى** — «هذا التمرين» تعني أنه ألصقه بنفسه، فلا يُجلَب مخزَّن.
#: مفهومٌ مستقلّ عن نيّة الطالب (ملكيّةُ محتوى لا رغبة)، فيبقى محلّياً بحقّ — وليس
#: دَيناً مؤجَّلاً. تمييزُه عن النيّة هو ما جعل حذف هذا الملفّ من `_FROZEN_DEBT` ممكناً.
_USER_OWNS_CONTENT_PATTERNS: tuple[str, ...] = (
    "هذا التمرين",
    "هذه المسألة",
    "هذا السؤال",
    "هذا الجزء",
    "الجزء أ",
    "الجزء ب",
    "الجزء ج",
    "الجزء الأول",
    "الجزء الثاني",
    "الجزء الثالث",
    "part a",
    "part b",
    "part c",
)

#: **اتّساعٌ مقصود للإلغاء وحده — ليست علامات نيّة.** «ساعد» سلسلةٌ جزئية تلتقط
#: «المساعدة» و«ساعدة»، وهو اتّساعٌ آمنٌ هنا (أسوأ أثره: لا نجلب تمريناً مخزَّناً)
#: وخطِرٌ في `shared/intent` حيث تُغذّي كشفَ نيّة الطالب في المسار التعليمي الحيّ
#: (`student_state_skill`) — فتجعل «ما هي المساعدة» طلبَ تلميحٍ لا سؤالَ تعريف.
#: تُبقى هنا **بسببها المكتوب** لا كدَينٍ منسيّ: ترقيتها إلى السجلّ القانوني تتطلّب
#: قياسَ أثرها على التوجيه أوّلاً.
_RETRIEVAL_CANCEL_BREADTH: tuple[str, ...] = ("ساعد",)


def _build_explanation_intent_patterns() -> tuple[str, ...]:
    """أنماط «لا تجلب محتوى» — **مُركَّبة من المصادر القانونية** (D-206 · L6).

    كانت هنا قائمةٌ محلّية من ٢٣ نمطاً تخلط ثلاثة مفاهيم: نيّة الشرح · نيّة التعريف ·
    ملكيّة المحتوى. وكونُها نسخةً رابعة لعلامات نيّةٍ موجودة أصلاً في `shared/intent`
    هو ما أبقى هذا الملفّ في `_FROZEN_DEBT` (D7). الآن: النيّة من مصدرها، والملكيّة
    وحدها محلّية — فالدَّين يُسدَّد بالتفكيك لا بالترحيل.
    """
    from shared.intent import markers_for

    return tuple(
        dict.fromkeys(
            (
                *EXPLANATION_CANCEL_MARKERS,  # اشرح · وضح · فسر · كيف · لماذا · explain …
                *markers_for("hint_request"),  # ساعدني · دلني · help …
                *markers_for("definition"),  # ما هو · ما معنى · what is …
                *_USER_OWNS_CONTENT_PATTERNS,
                *_RETRIEVAL_CANCEL_BREADTH,
            )
        )
    )


_EXPLANATION_INTENT_PATTERNS: tuple[str, ...] = _build_explanation_intent_patterns()

# ─────────────────────────────────────────────────────────────────────────────
# أنماط النية الإيجابية — تشير إلى طلب جلب محتوى من قاعدة المعرفة.
# يجب أن تكون محددة جداً لتجنب التفعيل الخاطئ.
# ─────────────────────────────────────────────────────────────────────────────
_RETRIEVAL_INTENT_PATTERNS: tuple[str, ...] = (
    # طلب صريح لتمرين بكالوريا
    "تمرين بكالوريا",
    "تمارين بكالوريا",
    "بكالوريا",
    "bac",
    "baccalauréat",
    # طلب تمرين محدد بموضوع
    "تمرين احتمالات",
    "تمارين احتمالات",
    "exercise probability",
    "probability exercise",
    "تمرين دوال",
    "دوال عددية",
    "numerical functions",
    "تمرين أعداد مركبة",
    "أعداد مركبة",
    "complex numbers",
    # طلب موضوع امتحان
    "الموضوع الأول",
    "الموضوع الثاني",
    "الموضوع الثالث",
    "subject 1",
    "subject 2",
    "subject 3",
    # طلب تمرين مُرقَّم بالترتيب
    "التمرين الأول",
    "التمرين الثاني",
    "التمرين الثالث",
    "التمرين الرابع",
    "exercise 1",
    "exercise 2",
    "exercise 3",
    "exercise 4",
    # طلب صريح للجلب — صيغ متعددة
    "أعطني تمرين",
    "أعطني تمارين",
    "اعطني تمرين",
    "اعطني تمارين",
    "أريد تمرين",
    "أريد تمارين",
    "اريد تمرين",
    "اريد تمارين",
    "هات تمرين",
    "هاتلي تمرين",
    "أحتاج تمرين",
    "احتاج تمرين",
    "نص تمرين",
    "نص التمرين",
    "أظهر تمرين",
    "اظهر تمرين",
    "عرض تمرين",
    "give me exercise",
    "give me exercises",
    "fetch exercise",
    "get exercise",
    "show exercise",
    "display exercise",
    "ابحث عن تمرين",
    "جلب تمرين",
    # الدورة الأولى / الثانية (خاص بـ 2016)
    "الدورة الأولى",
    "الدورة الثانية",
    "دورة أولى",
    "دورة ثانية",
    "session 1",
    "session 2",
    # طلب بالسنة فقط مع موضوع رياضي
    "2016 دوال",
    "دوال 2016",
    "2016 احتمالات",
    "احتمالات 2016",
    "2024 احتمالات",
    "احتمالات 2024",
    "2024 أعداد مركبة",
    "أعداد مركبة 2024",
)

# أنماط استخراج السنة والدورة والموضوع والتمرين
_SESSION_PATTERNS: dict[str, str] = {
    "الدورة الأولى": "الأولى",
    "الدورة الثانية": "الثانية",
    "دورة أولى": "الأولى",
    "دورة ثانية": "الثانية",
    "session 1": "الأولى",
    "session 2": "الثانية",
}

_SUBJECT_PATTERNS: dict[str, int] = {
    "الموضوع الأول": 1,
    "الموضوع الثاني": 2,
    "الموضوع الثالث": 3,
    "subject 1": 1,
    "subject 2": 2,
    "subject 3": 3,
    "subject1": 1,
    "subject2": 2,
    "subject3": 3,
}

_EXERCISE_PATTERNS: dict[str, int] = {
    "التمرين الأول": 1,
    "التمرين الثاني": 2,
    "التمرين الثالث": 3,
    "التمرين الرابع": 4,
    "exercise 1": 1,
    "exercise 2": 2,
    "exercise 3": 3,
    "exercise 4": 4,
}

_TOPIC_KEYWORDS: dict[str, list[str]] = {
    "احتمالات": ["الاحتمالات", "probability"],
    "probability": ["الاحتمالات", "probability"],
    "دوال عددية": ["الدوال العددية", "numerical functions"],
    "numerical functions": ["الدوال العددية", "numerical functions"],
    "أعداد مركبة": ["الأعداد المركبة", "complex numbers"],
    "complex numbers": ["الأعداد المركبة", "complex numbers"],
    "تكامل": ["التكامل", "integration"],
    "integration": ["التكامل", "integration"],
    "مشتقة": ["المشتقة", "derivative"],
    "derivative": ["المشتقة", "derivative"],
}

# تدوين الدوال — **تدوينٌ لا نيّة استرجاع** (ISS-140). يُحتسَب فقط مع قرينة استرجاع.
_FUNCTION_NOTATION_PATTERNS: tuple[str, ...] = (
    "g(x)",
    "f(x)",
    "h(x)",
    "دالة g",
    "دالة f",
    "دالة h",
    "الدالة g",
    "الدالة f",
    "الدالة h",
)

# طلب عمل مباشر على تعبير الطالب — يُلغي الاسترجاع (ISS-140).
_DIRECT_WORK_PATTERNS: tuple[str, ...] = (
    "احسب",
    "أحسب",
    "احسبي",
    "calcule",
    "calculate",
    "compute",
    "أوجد",
    "اوجد",
    "جد ",
    "استنتج",
    "برهن",
    "أثبت",
    "اثبت",
    "بيّن أن",
    "بين أن",
    "حل المعادلة",
    "حل المتراجحة",
    "بسّط",
    "بسط ",
    "ادرس",
    "أدرس",
)

# "تمرين" أو "exercise" متبوعاً برقم مباشرة
_EXERCISE_WITH_NUMBER_RE = re.compile(r"(تمرين|تمارين|exercise)\s*\d+", re.IGNORECASE)

# سنة دراسية (2000–2039) — تشمل 2016 (الدورتان الاستثنائيتان) إضافةً للسنوات الحديثة
_YEAR_RE = re.compile(r"\b20[0-3]\d\b")


class ExerciseRetrievalRequest(RobustBaseModel):
    """طلب استرجاع تعليمي منسّق."""

    question: str = Field(..., min_length=1)


class ExerciseRetrievalDecision(RobustBaseModel):
    """قرار التعرف على نية الاسترجاع التعليمي."""

    recognized: bool
    reason: str = ""
    matched_entry: ExerciseEntry | None = None

    model_config: ClassVar[dict[str, object]] = {"arbitrary_types_allowed": True}


class ExerciseRetrievalResult(RobustBaseModel):
    """نتيجة استرجاع التمارين مع semantics واضحة."""

    success: bool
    message: str | None = None
    entry: ExerciseEntry | None = None

    model_config: ClassVar[dict[str, object]] = {"arbitrary_types_allowed": True}


def _has_explanation_intent(normalized: str) -> bool:
    """يكشف عن نية الشرح أو المساعدة — تلغي الاسترجاع عند وجودها."""
    return any(pattern in normalized for pattern in _EXPLANATION_INTENT_PATTERNS)


def _has_function_notation(normalized: str) -> bool:
    """يكشف تدوين الدوال (``f(x)`` · ``الدالة g`` …) — **تدوينٌ لا نيّة**.

    كانت هذه الرموز مُدرَجة كأنماط استرجاع مستقلّة، فصار كل سؤال تفاضل/تكامل يذكر دالةً
    مُصنَّفاً «اجلب تمريناً مخزَّناً». وهذا هو صنف ISS-038 عائداً بمِفتاحٍ آخر: علامةٌ مسطَّحة
    تتجاهل النيّة. `f(x)` تظهر في كل سؤال رياضي تقريباً، فلا تصلح دليلاً على شيء وحدها.
    """
    return any(pattern in normalized for pattern in _FUNCTION_NOTATION_PATTERNS)


def _has_direct_work_intent(normalized: str) -> bool:
    """يكشف طلب **عملٍ مباشر** على تعبير الطالب (احسب · أوجد · برهن …).

    الطالب الذي يقول «احسب تكامل f(x)=x²+3x من 0 إلى 2» يطلب عملاً على تعبيره **هو**؛
    إرجاع تمرين بكالوريا مخزَّن بدل ذلك ليس إجابةً ناقصة بل إجابةً عن سؤالٍ آخر.
    """
    return any(pattern in normalized for pattern in _DIRECT_WORK_PATTERNS)


def _wants_stored_exercise(normalized: str) -> bool:
    """يكشف طلباً صريحاً لتمرينٍ **مخزَّن** (فيتقدّم على نيّة العمل المباشر).

    «احسب تمرين البكالوريا 2024» طلبُ استرجاعٍ حقيقي حتى لو بدأ بفعل حساب.
    """
    return (
        "تمرين" in normalized
        or "تمارين" in normalized
        or "exercise" in normalized
        or "بكالوريا" in normalized
        or "bac" in normalized
        or _YEAR_RE.search(normalized) is not None
    )


def _has_retrieval_intent(normalized: str) -> bool:
    """يكشف عن نية جلب محتوى من قاعدة المعرفة بشكل صريح أو دلالي."""
    if any(pattern in normalized for pattern in _RETRIEVAL_INTENT_PATTERNS):
        return True
    # تدوين الدوال يُحتسَب **فقط** مع قرينة استرجاع حقيقية (كلمة «تمرين» أو سنة أو
    # بكالوريا أو فعل جلب) — لا وحده. «هات تمرين الدالة f» استرجاع، و«احسب f(x)» ليس كذلك.
    if _has_function_notation(normalized):
        corroborated = (
            "تمرين" in normalized
            or "تمارين" in normalized
            or "exercise" in normalized
            or _YEAR_RE.search(normalized) is not None
            or "بكالوريا" in normalized
            or "bac" in normalized
        )
        if corroborated:
            return True
    if _EXERCISE_WITH_NUMBER_RE.search(normalized):
        return True
    # "تمرين" + سنة = طلب تمرين من سنة محددة
    if ("تمرين" in normalized or "exercise" in normalized) and _YEAR_RE.search(normalized):
        return True
    # أنماط دلالية: فعل جلب + موضوع رياضي = طلب محتوى
    _MATH_TOPICS_DIRECT: tuple[str, ...] = (  # noqa: N806
        "دوال عددية",
        "الدوال العددية",
        "احتمالات",
        "الاحتمالات",
        "أعداد مركبة",
        "الأعداد المركبة",
        "تكامل",
        "التكامل",
        "مشتقة",
        "المشتقة",
        "متتاليات",
        "المتتاليات",
    )
    _FETCH_VERBS: tuple[str, ...] = (  # noqa: N806
        "اعطني",
        "أعطني",
        "هات",
        "هاتلي",
        "أريد",
        "اريد",
        "أحتاج",
        "احتاج",
        "أظهر",
        "اظهر",
        "عرض",
        "show",
        "give",
        "get",
        "fetch",
        "display",
    )
    # تطبيع عربي + موضوع مرجعي → مناعة ضد أداة التعريف «ال» وتنويع الصياغة (عربي/فرنسي/إنجليزي)
    has_math_topic = (
        any(t in normalized for t in _MATH_TOPICS_DIRECT)
        or primary_canonical_topic(normalized) is not None
    )
    has_year = _YEAR_RE.search(normalized) is not None
    # "تمرين"/"exercise" + موضوع رياضي محدد = طلب تمرين (حتى بلا سنة)
    #   مثل: «تمرين الدوال العددية»
    if ("تمرين" in normalized or "exercise" in normalized) and has_math_topic:
        return True
    # موضوع رياضي مرجعي + سنة (بلا فعل جلب صريح) = طلب تمرين تلك السنة
    #   مثل: «nombres complexes 2024» / «الأعداد المركبة 2024»
    if has_math_topic and has_year:
        return True
    has_fetch_verb = any(v in normalized for v in _FETCH_VERBS)
    return has_fetch_verb and has_math_topic


def _extract_year(normalized: str) -> int | None:
    """يستخرج السنة من النص."""
    match = _YEAR_RE.search(normalized)
    return int(match.group()) if match else None


def _extract_session(normalized: str) -> str | None:
    """يستخرج الدورة من النص."""
    for pattern, session in _SESSION_PATTERNS.items():
        if pattern in normalized:
            return session
    return None


def _extract_subject_number(normalized: str) -> int | None:
    """يستخرج رقم الموضوع من النص."""
    for pattern, number in _SUBJECT_PATTERNS.items():
        if pattern in normalized:
            return number
    return None


def _extract_exercise_number(normalized: str) -> int | None:
    """يستخرج رقم التمرين من النص."""
    for pattern, number in _EXERCISE_PATTERNS.items():
        if pattern in normalized:
            return number
    match = _EXERCISE_WITH_NUMBER_RE.search(normalized)
    if match:
        digits = re.search(r"\d+", match.group())
        if digits:
            return int(digits.group())
    return None


def _extract_topic_keywords(normalized: str) -> list[str]:
    """يستخرج الكلمات المفتاحية للموضوع الرياضي (مطابقة مطبَّعة صامدة أمام «ال»)."""
    norm_q = normalize_ar(normalized)
    found: list[str] = []
    for keyword, topics in _TOPIC_KEYWORDS.items():
        kw_norm = normalize_ar(keyword)
        if kw_norm and kw_norm in norm_q:
            found.extend(topics)
    return list(set(found))


def _find_matching_entry(
    normalized: str, *, allow_tag_fallback: bool = True
) -> ExerciseEntry | None:
    """
    يبحث في فهرس قاعدة المعرفة عن أفضل تمرين مطابق للسؤال.

    يستخرج المعايير (سنة/دورة/موضوع/رقم) + الموضوع المرجعي، ثم يستدعي search_exercises.
    الموضوع المرجعي (canonical_topic_id) هو الإشارة الأقوى التي تكسر تعادل السنة.

    ISS-111 (D-102): ``allow_tag_fallback=False`` يقصر المطابقة على الإشارات
    البنيوية (سنة/دورة/موضوع/رقم/موضوع مرجعي). الـ tag-fallback يطابق أي كلمة
    عامة (مثل "math" من system prompt) — آمن لسؤال الطالب المباشر، كارثي
    لفحص history المحادثة.
    """
    year = _extract_year(normalized)
    session = _extract_session(normalized)
    subject_number = _extract_subject_number(normalized)
    exercise_number = _extract_exercise_number(normalized)
    topic_keywords = _extract_topic_keywords(normalized)
    canonical = primary_canonical_topic(normalized)

    results = search_exercises(
        year=year,
        session=session,
        subject_number=subject_number,
        exercise_number=exercise_number,
        topic_keywords=topic_keywords if topic_keywords else None,
        canonical_topic_id=canonical.canonical_id if canonical else None,
    )

    if results:
        return results[0]

    if not allow_tag_fallback:
        return None

    # بحث بالوسوم إذا لم تُوجد نتائج بالمعايير
    tag_keywords = [w for w in normalized.split() if len(w) > 2]
    return find_best_match(tag_keywords)


def detect_exercise_retrieval(
    request: ExerciseRetrievalRequest,
    history_messages: list[dict[str, str]] | None = None,
) -> ExerciseRetrievalDecision:
    """
    يتعرف على أسئلة الاسترجاع التعليمي بدقة عالية لتجنب التفعيل الخاطئ.

    المنطق رباعي المراحل:
    1. نية الشرح/المساعدة → لا استرجاع (حتى لو ذُكر "تمرين" أو "احتمالات")
    2. نية الجلب الصريحة → استرجاع مع تحديد التمرين من الفهرس
    3. (ISS-CONV-C — LangGraph Amnesia Fix) سؤال متابعة + سياق محادثة عن تمرين
       بكالوريا → استرجاع بالتمرين المذكور في السياق
    4. حالة الشك → لا استرجاع (LangGraph يعالج الحالات الغامضة أفضل)

    يحل ISS-038: كلمة "تمرين" في سياق الشرح كانت تُطلق استرجاع تمرين
    الاحتمالات بشكل ثابت بغض النظر عن السياق.

    يحل ISS-CONV-C (LangGraph Amnesia): أسئلة المتابعة مثل "اسئلة الاحتمالات فقط"
    كانت تُعيد تشغيل SupervisorNode من الصفر وتتجاهل سياق المحادثة. الآن تُحلَّل
    بالرجوع إلى history_messages لتحديد التمرين الصحيح.
    """
    normalized = request.question.strip().lower()

    # الأولوية الأولى: نية الشرح تلغي الاسترجاع دائماً
    if _has_explanation_intent(normalized):
        return ExerciseRetrievalDecision(
            recognized=False,
            reason="explanation_intent_detected",
        )

    # الأولوية الأولى-ب (ISS-140): طلب عمل مباشر على تعبير الطالب يُلغي الاسترجاع، إلّا
    # إذا طلب صراحةً تمريناً مخزَّناً («احسب تمرين البكالوريا 2024»). الطالب الذي يقول
    # «احسب تكامل f(x)=x²+3x من 0 إلى 2» كان يتلقّى تمرين «الدوال العددية» المخزَّن —
    # أي إجابةً عن سؤالٍ لم يطرحه.
    if _has_direct_work_intent(normalized) and not _wants_stored_exercise(normalized):
        return ExerciseRetrievalDecision(
            recognized=False,
            reason="direct_work_intent_detected",
        )

    # الأولوية الثانية: نية الجلب الصريحة
    if _has_retrieval_intent(normalized):
        matched_entry = _find_matching_entry(normalized)
        return ExerciseRetrievalDecision(
            recognized=True,
            reason="retrieval_intent_detected",
            matched_entry=matched_entry,
        )

    # الأولوية الثالثة (ISS-CONV-C): سؤال متابعة + سياق محادثة
    # أنماط تُشير إلى طلب تصفية/تحديد داخل تمرين سبق ذكره في المحادثة
    _FOLLOWUP_FILTER_PATTERNS: tuple[str, ...] = (  # noqa: N806
        "فقط",
        "only",
        "seulement",
        "اسئلة",
        "أسئلة",
        "الأسئلة",
        "questions",
        "الجزء",
        "part",
        "partie",
        "أعد",
        "اعد",
        "مرة أخرى",
        "again",
        "encore",
        "هذا التمرين",
        "نفس التمرين",
        "same exercise",
    )
    is_followup = any(p in normalized for p in _FOLLOWUP_FILTER_PATTERNS)
    if is_followup and history_messages:
        context_entry = _detect_entry_from_history(history_messages)
        if context_entry is not None:
            return ExerciseRetrievalDecision(
                recognized=True,
                reason="followup_with_conversation_context",
                matched_entry=context_entry,
            )

    # الحالة الافتراضية: لا استرجاع — اللجوء إلى LangGraph
    return ExerciseRetrievalDecision(
        recognized=False,
        reason="no_clear_retrieval_intent",
    )


def load_exercise_content(entry: ExerciseEntry) -> str | None:
    """
    يحمِّل محتوى ملف التمرين من قاعدة المعرفة.

    يُرجع المحتوى كنص أو None إذا لم يُوجد الملف.
    """
    project_root = Path(__file__).resolve().parents[3]
    file_path = project_root / entry.file_path

    if not file_path.exists():
        return None

    return file_path.read_text(encoding="utf-8")


def load_exercise_questions_only(entry: ExerciseEntry) -> str | None:
    """ISS-120 (D-153): يحمِّل نص التمرين **بلا الحل النموذجي** (أسئلة-فقط).

    القاعدة الدستورية: أي نص يُغذَّى لاستخراج الكيانات/التركيبة (المحرك الرمزي)
    يجب أن يكون خالياً من نثر الحل — نثر الحل («…تحمل الرقم 0 … وعددها 3 كرات»)
    يولِّد كياناً وهمياً («بطاقة رقم 0») يُفسد فضاء العينة (n=14 بدل 11).
    الحل النموذجي الكامل يبقى متاحاً عبر ``load_exercise_content`` لمسارات
    RAG-Grounded LLM (D-145) حصراً.
    """
    raw = load_exercise_content(entry)
    if not raw:
        return raw
    return _trim_at_solution(raw)


# ─────────────────────────────────────────────────────────────────────────────
# عرض التمرين بشكل نظيف للطالب (D-048)
#
# قبل ISS-051: الاسترجاع كان يُرجع كامل محتوى الملف (YAML + نص التمرين +
# عناصر الإجابة النموذجية) مما يُسبب فوضى بصرية وكشف الحلول قبل الأوان.
#
# بعد ISS-051: نُخرج فقط بطاقة الامتحان + نص التمرين، ونحذف:
#   1. YAML frontmatter
#   2. كل ما يلي "عناصر الإجابة" أو "الحل" أو "Solution"
#   3. وسوم البحث في نهاية الملف
# ─────────────────────────────────────────────────────────────────────────────

_FRONTMATTER_RE = re.compile(r"^---\s*\n.*?\n---\s*\n", re.DOTALL)

# قواطع نهاية نص التمرين — أي قسم يبدأ بأحد هذه العناوين يُحذف وما بعده
_SOLUTION_SECTION_MARKERS: tuple[str, ...] = (
    "## عناصر الإجابة",
    "## الإجابة النموذجية",
    "## الحل",
    "## الإجابة",
    "## شرح الحل",
    "## Solution",
    "## Model Answer",
    "## Answer",
    "## وسوم البحث",
    "## وسوم بحث",  # صيغة بديلة (مثل "## وسوم بحث مقترحة")
    "## Tags",
    "### الجزء I",  # بداية الشرح المفصَّل
    "### الجزء II",
    "### الجزء III",
)


def _strip_frontmatter(content: str) -> str:
    """يحذف YAML frontmatter من بداية ملف markdown."""
    return _FRONTMATTER_RE.sub("", content, count=1).lstrip()


def _trim_at_solution(content: str) -> str:
    """يقطع المحتوى عند أول قسم يحوي عناصر الإجابة/الحل/الوسوم."""
    cut_index: int | None = None
    for marker in _SOLUTION_SECTION_MARKERS:
        idx = content.find(marker)
        if idx == -1:
            continue
        if cut_index is None or idx < cut_index:
            cut_index = idx
    if cut_index is None:
        return content.rstrip()
    return content[:cut_index].rstrip()


# ─────────────────────────────────────────────────────────────────────────────
# حدود التمارين الدلالية (ISS-RAG-B — Semantic Boundary Slicing)
#
# المشكلة: ملف bac2024_math_experimental_subject1_ex1_ex2.md يحوي تمرينين
# (الاحتمالات + الأعداد المركبة) في ملف واحد. عند طلب "تمرين الاحتمالات 2024"
# كان format_exercise_for_display يُرجع كلا التمرينين لأنه لا يعرف رقم التمرين.
#
# الحل: _slice_exercise_by_number() يقطع المحتوى بين عناوين "## التمرين N"
# ليُرجع فقط التمرين المطلوب بحسب entry.exercise_number.
# ─────────────────────────────────────────────────────────────────────────────

# أنماط عناوين التمارين في ملفات knowledge_base (عربي + إنجليزي)
_EXERCISE_HEADING_PATTERNS: tuple[str, ...] = (
    "## التمرين الأول",
    "## التمرين الثاني",
    "## التمرين الثالث",
    "## التمرين الرابع",
    "## Exercise 1",
    "## Exercise 2",
    "## Exercise 3",
    "## Exercise 4",
    "## تمرين 1",
    "## تمرين 2",
    "## تمرين 3",
    "## تمرين 4",
)

# ترتيب العناوين حسب رقم التمرين (1-indexed)
_EXERCISE_HEADING_BY_NUMBER: dict[int, tuple[str, ...]] = {
    1: ("## التمرين الأول", "## Exercise 1", "## تمرين 1"),
    2: ("## التمرين الثاني", "## Exercise 2", "## تمرين 2"),
    3: ("## التمرين الثالث", "## Exercise 3", "## تمرين 3"),
    4: ("## التمرين الرابع", "## Exercise 4", "## تمرين 4"),
}


def _slice_exercise_by_number(content: str, exercise_number: int) -> str:
    """
    يقطع المحتوى ليُرجع فقط قسم التمرين المطلوب بحسب رقمه.

    يحل ISS-RAG-B (Semantic Boundary Slicing):
    عندما يحوي الملف أكثر من تمرين (مثل bac2024_ex1_ex2.md)، يُرجع
    هذا التابع فقط التمرين ذا الرقم المطلوب بدلاً من كامل الملف.

    الخوارزمية:
      1. يبحث عن عنوان التمرين المطلوب (## التمرين الأول / ## Exercise 1 / ...)
      2. يبحث عن عنوان التمرين التالي (حد نهاية القسم)
      3. يُرجع المحتوى بين الحدين فقط

    إذا لم يجد عنوان التمرين المطلوب → يُرجع المحتوى كاملاً (سلوك آمن).
    """
    if exercise_number not in _EXERCISE_HEADING_BY_NUMBER:
        return content

    # إيجاد موضع بداية التمرين المطلوب
    start_idx: int | None = None
    for heading in _EXERCISE_HEADING_BY_NUMBER[exercise_number]:
        idx = content.find(heading)
        if idx != -1:
            start_idx = idx
            break

    if start_idx is None:
        # لا يوجد عنوان صريح للتمرين → الملف يحوي تمريناً واحداً فقط
        return content

    # إيجاد موضع بداية التمرين التالي (حد النهاية)
    end_idx: int | None = None
    next_exercise_number = exercise_number + 1
    if next_exercise_number in _EXERCISE_HEADING_BY_NUMBER:
        for heading in _EXERCISE_HEADING_BY_NUMBER[next_exercise_number]:
            idx = content.find(heading, start_idx + 1)
            if idx != -1 and (end_idx is None or idx < end_idx):
                end_idx = idx

    if end_idx is not None:
        return content[start_idx:end_idx].rstrip()
    return content[start_idx:].rstrip()


def format_exercise_for_display(entry: ExerciseEntry, raw_content: str) -> str:
    """
    يُهيِّئ محتوى التمرين لعرض نظيف للطالب — فقط نص التمرين المطلوب، بدون YAML أو حل.

    يحل ISS-051:
      - YAML frontmatter يظهر للطالب
      - عناصر الإجابة النموذجية تُكشف قبل أن يحل الطالب
      - وسوم البحث في الأسفل

    يحل ISS-RAG-B (Semantic Boundary Slicing):
      - ملفات تحوي أكثر من تمرين (مثل bac2024_ex1_ex2.md) كانت تُرجع كلا
        التمرينين. الآن يُرجع فقط التمرين ذا الرقم المطابق لـ entry.exercise_number.

    Args:
        entry: السجل المطابق من knowledge_index (يحوي exercise_number).
        raw_content: محتوى الملف الخام (مع YAML + الحل).

    Returns:
        محتوى نظيف يحوي: عنوان + بطاقة الامتحان + نص التمرين المطلوب فقط.
    """
    if not raw_content:
        return ""
    no_frontmatter = _strip_frontmatter(raw_content)
    questions_only = _trim_at_solution(no_frontmatter)
    # ISS-RAG-B: قطع المحتوى على حدود التمرين المطلوب
    sliced = _slice_exercise_by_number(questions_only, entry.exercise_number)
    return sliced.strip()


def make_result(
    raw_result: str | None, entry: ExerciseEntry | None = None
) -> ExerciseRetrievalResult:
    """يحوّل النتيجة الخام إلى عقد موحد دون كسر السلوك التاريخي."""
    if raw_result is None or not raw_result.strip():
        return ExerciseRetrievalResult(success=False)
    return ExerciseRetrievalResult(success=True, message=raw_result, entry=entry)


# ─────────────────────────────────────────────────────────────────────────────
# مسار الشرح مع السياق (ISS-053)
#
# المشكلة: عند "اشرح تمرين الدوال العددية 2016"، كانت explanation_intent تُلغي
# الاسترجاع فيذهب الطلب إلى LangGraph بدون محتوى التمرين → هلوسة.
#
# الحل: مسار ثالث — "شرح مع سياق" — يكشف عن طلبات الشرح التي تُحدِّد تمريناً
# بكالوريا معروفاً، يجلب محتواه الكامل (نص + إجابة نموذجية)، ويُمرِّره للـ LLM.
# ─────────────────────────────────────────────────────────────────────────────

# أنماط تُشير إلى طلب شرح تمرين بكالوريا محدد (وليس شرح مفهوم عام)
# ISS-075 (D-063): أُضيفت أنماط طلب الشرح بصياغة "أريد"، "ممكن"، و prefix "ل" (للسؤال/للجزء)
_BAC_EXERCISE_EXPLANATION_PATTERNS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            # شرح + تمرين + سنة
            "اشرح تمرين",
            "شرح تمرين",
            "وضح تمرين",
            "فسر تمرين",
            "explain exercise",
            "explain the exercise",
            # شرح + إجابة نموذجية
            "اشرح الإجابة النموذجية",
            "شرح الإجابة النموذجية",
            "اشرح الحل",
            "شرح الحل",
            "اشرح الجواب",
            "شرح الجواب",
            "explain the solution",
            "explain the answer",
            # شرح + دالة رياضية محددة من التمرين
            "اشرح g(x)",
            "اشرح f(x)",
            "اشرح h(x)",
            "شرح g(x)",
            "شرح f(x)",
            "شرح h(x)",
            "وضح g(x)",
            "وضح f(x)",
            "وضح h(x)",
            "فسر g(x)",
            "فسر f(x)",
            "فسر h(x)",
            "بيّن g(x)",
            "بيّن f(x)",
            "بيّن h(x)",
            "بين g(x)",
            "بين f(x)",
            "بين h(x)",
            # شرح + جزء من التمرين مع ذكر السنة (يُكشف لاحقاً بالسنة)
            "اشرح الجزء",
            "شرح الجزء",
            "اشرح للجزء",
            "شرح للجزء",
            "اشرح السؤال",
            "شرح السؤال",
            "اشرح للسؤال",
            "شرح للسؤال",
            "اشرح الفقرة",
            "شرح الفقرة",
            # ISS-075: صياغات طبيعية بـ "أريد" / "ممكن" / "هل يمكن"
            "أريد شرح",
            "أريد شرحاً",
            "اريد شرح",
            "ابغى شرح",
            "ابغي شرح",
            "ممكن شرح",
            "ممكن تشرح",
            "هل يمكن أن تشرح",
            "هل يمكنك شرح",
            "ابي شرح",
            "ودي شرح",
            "أحتاج شرح",
            "احتاج شرح",
            "I want explanation",
            "give me explanation",
            "can you explain",
            # ISS-075: صيغ "مفصل" / "مفصلاً" / "بالتفصيل"
            "شرح مفصل",
            "شرحاً مفصلاً",
            "اشرح بالتفصيل",
            "شرح بالتفصيل",
            "اشرح بالتفصيلَ",
            "explain in detail",
            "detailed explanation",
            # طلب الشرح بالدارجة
            "شرحلي",
            "شرح لي",
            "فهمني",
            "علمني",
            "وضحلي",
            # ── D-206 (L6): العبارات المفاهيمية العارية مصدرها السجلّ القانوني ────────
            # كانت هنا ٣٠ عبارة (ماذا نقصد · ما معنى · كيف نحسب · لماذا …) منسوخةً حرفياً
            # من نيّاتٍ مُعرَّفة أصلاً في `shared/intent`. أمّا العبارات المركّبة أعلاه
            # («اشرح تمرين» · «اشرح g(x)») فهي مفهومٌ آخر — «اشرح **هذا** الشيء» — فتبقى.
            *markers_for("definition"),
            *markers_for("procedure"),
            *EXPLANATION_CANCEL_MARKERS,
            # عبارات تبرير خاصّة بالتمرين لا تُغطّيها النيّات العامّة.
            "what is meant",
            "كيف نُثبت",
            "كيف نثبت",
            "كيف نُبيِّن",
            "كيف نبين",
            "كيف نستنتج",
            "كيف نُوجد",
            "كيف يصبح",
            "كيف نصل",
            "كيف وصلنا",
            "how to prove",
            "how to compute",
            "how to derive",
            "علِّل",
            "علل",
            "برِّر",
            "برر",
            "why is",
            "justify",
        )
    )
)

# أنماط تُحدِّد تمريناً بكالوريا بالسنة أو الموضوع أو الدالة
_BAC_SPECIFICITY_PATTERNS: tuple[str, ...] = (
    "2016",
    "2024",
    "2023",
    "2022",
    "2021",
    "2020",
    "بكالوريا",
    "باكالوريا",
    "bac",
    "الموضوع الثاني",
    "الموضوع الأول",
    "التمرين الرابع",
    "التمرين الأول",
    "التمرين الثاني",
    "التمرين الثالث",
    "الدورة الأولى",
    "الدورة الثانية",
    "دوال عددية",
    "الدوال العددية",
    "g(x)",
    "f(x)",
    "h(x)",
    "احتمالات",
    "أعداد مركبة",
)


class ExplanationWithContextDecision(RobustBaseModel):
    """
    قرار مسار الشرح مع السياق.

    recognized=True يعني: المستخدم يريد شرح تمرين بكالوريا محدد موجود في قاعدة المعرفة.
    full_content يحوي نص التمرين + الإجابة النموذجية الكاملة للـ LLM.
    display_content يحوي نص التمرين فقط (بدون حل) للعرض المبدئي.
    requested_part: الجزء المطلوب (I / II / III) إن حُدِّد — يُمكِّن التقطيع الذكي.
    """

    recognized: bool
    reason: str = ""
    matched_entry: ExerciseEntry | None = None
    full_content: str | None = None  # نص + إجابة نموذجية → للـ LLM كـ context
    display_content: str | None = None  # نص فقط → للعرض المبدئي للطالب
    requested_part: str | None = None  # ISS-055: hint للتقطيع الذكي (I/II/III)

    model_config: ClassVar[dict[str, object]] = {"arbitrary_types_allowed": True}


def _detect_entry_from_history(
    history_messages: list[dict[str, str]] | None,
) -> ExerciseEntry | None:
    """يكشف عن تمرين بكالوريا مذكور حديثاً في سياق المحادثة.

    ISS-058: عندما يسأل الطالب «ماذا نقصد بدالة أصلية للدالة f» بعد أن طُلب
    منه تمرين 2016 الدوال العددية، نريد ربط السؤال بذلك التمرين تلقائياً —
    لا الذهاب لـ wide-net retrieval الذي يُرجع تمارين أخرى غير ذات صلة.

    نفحص آخر 10 رسائل بحثاً عن إشارات تمرين بكالوريا (عنوان الملف، السنة،
    الموضوع، رقم التمرين) ونستخدمها للبحث في الفهرس.
    """
    if not history_messages:
        return None
    # ISS-111 (D-102): رسائل system ليست دليلاً من المحادثة — برومبت Overmind
    # الإنجليزي ("...math, physics...") كان يمر عبر tag-fallback ويربط **كل**
    # سؤال يحوي «اشرح» بتمرين 2024 حتى في محادثة جديدة فارغة (مؤكَّد حياً).
    conversational = [
        m
        for m in history_messages[-10:]
        if isinstance(m, dict) and m.get("role") in ("user", "assistant")
    ]
    recent_text = " ".join(str(m.get("content", ""))[:1500] for m in conversational).lower()
    if not recent_text.strip():
        return None
    # ISS-111 (D-102): الربط بالتاريخ يتطلب تطابقاً بنيوياً (سنة/موضوع/رقم) —
    # الـ tag-fallback على كلمات عامة من الـ history يُنتج ربطاً زائفاً.
    return _find_matching_entry(recent_text, allow_tag_fallback=False)


# ISS-107: علامات متابعة قصيرة/حيرة تُبقي السؤال مربوطاً بتمرين السياق.
# «لم افهم التكامل» و«اشرح بالعربية» لا يطابقان _BAC_EXERCISE_EXPLANATION_PATTERNS
# (لا «اشرح» مجرّدة، ولا علامات الحيرة) → كانا يسقطان للـ LLM العام → هلوسة كيمياء.
# هذه المجموعة تُفعِّل Phase-2 (المعتمد على التاريخ) فقط — تأثيرها صفر بلا تمرين
# في السياق (`_detect_entry_from_history` يُرجع None فيسقط للمسار العام).
_FOLLOWUP_EXPLANATION_MARKERS: tuple[str, ...] = tuple(
    dict.fromkeys(
        (
            # D-206 (L6): الحيرة وطلب الشرح مصدرهما السجلّ القانوني — كانت ١١ صيغة
            # منسوخة هنا (لم افهم · مفهمتش · اشرح · وضح …) تتفرّق عن أصلها بمرور الوقت.
            *markers_for("confusion"),
            *markers_for("explanation_request"),
            *EXPLANATION_CANCEL_MARKERS,
            # صيغٌ إملائية بالشدّة لا يحملها السجلّ (الطالب يكتبها هكذا فعلاً).
            "وضّح",
            "فسّر",
            "إشرح",
            "اشرحلي",
            # **الإكمال/المتابعة مفهومٌ مستقلّ** — «أكمل الشرح» ليست حيرةً ولا طلبَ
            # شرحٍ جديد بل متابعةً لما بدأ (ISS-108 · D-097: غيابها أسقط الدور إلى
            # المسار العام بلا سياق التمرين ⇒ هلوسة عن «سمك الغشاء» لسؤال احتمالات).
            "أكمل",
            "اكمل",
            "كمل",
            "كمّل",
            "تابع",
            "واصل",
            "المزيد",
            "زدني",
            "أكثر",
            "continue",
            "go on",
            # تفضيلُ أسلوبٍ لا نيّة: «بالعربية» · «بسّط».
            "بسّط",
            "بسط",
            "بالعربية",
            "in arabic",
            "i don't understand",
            "didn't understand",
        )
    )
)


def _is_followup_explanation_request(normalized: str) -> bool:
    """يكشف متابعة شرح/حيرة قصيرة تستحق ربطها بتمرين السياق (ISS-107)."""
    return any(m in normalized for m in _FOLLOWUP_EXPLANATION_MARKERS)


def detect_explanation_with_context(
    request: ExerciseRetrievalRequest,
    history_messages: list[dict[str, str]] | None = None,
) -> ExplanationWithContextDecision:
    """
    يكشف عن طلبات شرح تمرين بكالوريا محدد ويجلب محتواه الكامل كـ context للـ LLM.

    المنطق ثلاثي المرحلة:
    1. هل يوجد نمط شرح + تحديد تمرين بكالوريا في السؤال نفسه؟ → جلب التمرين
    2. (ISS-058) هل يوجد نمط شرح/استفسار + تمرين سابق في سياق المحادثة؟ → استخدم تمرين السياق
    3. خلاف ذلك → لا شرح مع سياق (يذهب لـ LangGraph العام)

    يحل ISS-053: طلبات "اشرح تمرين الدوال العددية 2016" كانت تذهب إلى LangGraph
    بدون محتوى التمرين → هلوسة. الآن يحصل LLM على النص الكامل + الإجابة النموذجية.
    يحل ISS-058: «ماذا نقصد بدالة أصلية للدالة f» (بدون ذكر صريح للسنة/الموضوع)
    كان يُسبب dump لكل ملفات knowledge_base/. الآن نربطه بتمرين السياق.
    """
    normalized = request.question.strip().lower()

    # المرحلة 1: هل يوجد نمط شرح تمرين بكالوريا؟
    has_explanation_pattern = any(p in normalized for p in _BAC_EXERCISE_EXPLANATION_PATTERNS)
    has_specificity = any(p in normalized for p in _BAC_SPECIFICITY_PATTERNS)

    matched_entry: ExerciseEntry | None = None
    reason_used: str = ""

    if has_explanation_pattern and has_specificity:
        matched_entry = _find_matching_entry(normalized)
        reason_used = "bac_explanation_with_context"

    # المرحلة 2 (ISS-058 + ISS-107): استفسار مفاهيمي/حيرة/متابعة قصيرة + سياق محادثة
    # عن تمرين بكالوريا. وُسِّعت البوّابة لتشمل علامات المتابعة («لم افهم»، «اشرح
    # بالعربية»، «وضّح») لأن «اشرح بالعربية» لا يطابق الأنماط الصارمة → كان يهلوس.
    is_followup = has_explanation_pattern or _is_followup_explanation_request(normalized)
    if matched_entry is None and is_followup:
        context_entry = _detect_entry_from_history(history_messages)
        if context_entry is not None:
            matched_entry = context_entry
            reason_used = "bac_explanation_with_conversation_context"

    if matched_entry is None:
        return ExplanationWithContextDecision(
            recognized=False,
            reason="no_bac_explanation_pattern"
            if not is_followup
            else "no_matching_entry_or_context",
        )

    # المرحلة 3: جلب المحتوى الكامل (نص + إجابة نموذجية)
    raw_content = load_exercise_content(matched_entry)
    if not raw_content:
        return ExplanationWithContextDecision(
            recognized=False,
            reason="content_file_not_found",
        )

    # full_content = المحتوى الكامل بعد حذف YAML فقط (يشمل الإجابة النموذجية)
    full_content = _strip_frontmatter(raw_content).strip()

    # display_content = نص التمرين فقط (بدون إجابة نموذجية)
    display_content = format_exercise_for_display(matched_entry, raw_content)

    # ISS-055: كشف الجزء المطلوب لتمرير hint للـ local_graph
    # يُمكِّن التقطيع الذكي في run_local_graph_with_exercise_context
    requested_part = _detect_requested_part_from_question(request.question)

    return ExplanationWithContextDecision(
        recognized=True,
        reason=reason_used or "bac_explanation_with_context",
        matched_entry=matched_entry,
        full_content=full_content,
        display_content=display_content,
        requested_part=requested_part,
    )


def _detect_requested_part_from_question(question: str) -> str | None:
    """
    يكشف عن الجزء المطلوب من التمرين (I / II / III) من سؤال الطالب.

    يُستخدم لتمرير hint للـ local_graph لتقطيع السياق ذكياً.
    """
    normalized = question.strip().lower()
    _PART_HINTS: dict[str, tuple[str, ...]] = {  # noqa: N806
        "I": (
            "الجزء الأول",
            "الجزء i",
            "part i",
            "part 1",
            "الجزء 1",
            "g(x)",
            "الدالة g",
            "دالة g",
            "السؤال الأول",
            "g\\(x\\)",
        ),
        "II": (
            "الجزء الثاني",
            "الجزء ii",
            "part ii",
            "part 2",
            "الجزء 2",
            "f(x)",
            "الدالة f",
            "دالة f",
            "السؤال الثاني",
            "f\\(x\\)",
        ),
        "III": (
            "الجزء الثالث",
            "الجزء iii",
            "part iii",
            "part 3",
            "الجزء 3",
            "h(x)",
            "الدالة h",
            "دالة h",
            "التكامل",
            "الدالة الأصلية",
            "السؤال الثالث",
            "h\\(x\\)",
        ),
    }
    for part, patterns in _PART_HINTS.items():
        if any(p in normalized for p in patterns):
            return part
    return None


# ═══════════════════════════════════════════════════════════════════════════
# ISS-112 — «أعطني السؤال رقم N فقط» (question-only retrieval)
#
# الفضيحة المُشخَّصة حياً (2026-06-11): «اعطني السؤال رقم 2 ... فقط السؤال»
# كان يُرجع التمرين كاملاً، أو أسوأ — حلاً كاملاً مُهلوَساً من LLM بنص مشوه.
# الحل الحتمي: كشف نية «السؤال فقط» + اقتطاع السؤال المرقَّم من نص التمرين
# الرسمي (بدون حل أصلاً — display_content) — صفر LLM، صفر هلوسة.
# ═══════════════════════════════════════════════════════════════════════════

_ARABIC_INDIC_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

_QUESTION_ONLY_MARKERS: tuple[str, ...] = (
    "فقط",
    "بدون حل",
    "بدون الحل",
    "بدون اجابة",
    "بدون إجابة",
    "بدون الاجابة",
    "بدون الإجابة",
    "نص السؤال",
    "question only",
    "without solution",
)

_QUESTION_REQUEST_VERBS: tuple[str, ...] = (
    "اعطني",
    "أعطني",
    "اعطيني",
    "أعطيني",
    "اريد",
    "أريد",
    "هات",
    "اكتب لي",
    "ابغى",
    "ابغي",
)

_ORDINAL_QUESTION_NUMBERS: tuple[tuple[str, int], ...] = (
    ("الأول", 1),
    ("الاول", 1),
    ("الثاني", 2),
    ("الثالث", 3),
    ("الرابع", 4),
    ("الخامس", 5),
)

_QUESTION_NUMBER_RE = re.compile(r"(?:السؤال|سؤال)\s*(?:رقم\s*)?(\d{1,2})")


class QuestionOnlyDecision(RobustBaseModel):
    """قرار «أعطني السؤال N فقط» — اقتطاع حتمي من النص الرسمي."""

    recognized: bool = False
    reason: str = ""
    matched_entry: ExerciseEntry | None = None
    question_number: int | None = None
    sliced_content: str = ""


def _extract_question_number(normalized: str) -> int | None:
    """يستخرج رقم السؤال المطلوب — **يُفوِّض للمصدر القانوني** (D-206 · L6).

    كانت هنا قائمةُ ترتيبيّاتٍ محلّية بستّ صيغ **مُعرَّفة فقط** (`"الأول"` · `"الاول"` …)
    تُطابَق على `text.strip().lower()` — و`lower()` لا تفعل شيئاً بالعربية. فالطالب الذي
    كتب «**اول** سؤال» نكرةً لم يكن مُمثَّلاً، ومعه الدارجة («لول») والفرنسية. وهذا هو
    ISS-144 حرفياً: قدرةٌ سليمة عمياء عن صيغةِ طالبٍ حقيقي.

    السلطة الآن `shared/exercise_scope` (تُطبّع + تحذف أداة التعريف + تُطابق على حدود
    الكلمات)، فتُغطّي الصيغ الأربع بصورةٍ واحدة بدل قائمةٍ تُرقَّع بعد كل كارثة.

    نستعمل `extract_target` (استخراجٌ محض) لا `resolve_scope` (التي تشترط نيّةً صريحة):
    هذه الدالّة تُستدعى أيضاً على رسائل التاريخ حيث النيّة محسومة سلفاً، فاشتراطُها هنا
    كان سيُسقِط «السؤال الثاني» المجرّدة — انحدارٌ صامت.
    """
    number, _part = extract_target(normalized)
    return number


def _resolve_question_number_from_history(
    history_messages: list[dict[str, str]] | None,
) -> int | None:
    """متابعة «اريد السؤال فقط» بلا رقم: آخر رقم سؤال ذكره الطالب في الحوار."""
    if not history_messages:
        return None
    for msg in reversed(history_messages[-8:]):
        if not isinstance(msg, dict) or msg.get("role") != "user":
            continue
        n = _extract_question_number(str(msg.get("content", "")).strip().lower())
        if n is not None:
            return n
    return None


def _extract_numbered_question(display_content: str, question_number: int) -> str | None:
    """يقتطع السؤال المرقَّم N من نص التمرين (مع عنوان جزئه للسياق).

    التمرين قد يحوي البند N في أكثر من جزء (مثل «2.» في (1) و (2) بتمرين
    الاحتمالات) — نُرجِع كل المطابقات كلٌّ مع عنوان جزئها: صدقٌ أوضح من تخمين.
    """
    numbered_re = re.compile(r"^\s*(?:\*\*)?(\d{1,2})[.)ـ-]\s*")
    part_header_re = re.compile(r"^\s*(?:\*\*\(|##+\s|\*\*[IV1-9])")

    lines = display_content.splitlines()
    current_part: str = ""
    matches: list[str] = []
    collecting: list[str] | None = None

    def _flush() -> None:
        nonlocal collecting
        if collecting:
            block = "\n".join(collecting).strip()
            if block:
                header = f"{current_part}\n\n" if current_part else ""
                matches.append(header + block)
        collecting = None

    for raw_line in lines:
        line = raw_line.translate(_ARABIC_INDIC_DIGITS)
        m = numbered_re.match(line)
        if m:
            _flush()
            if int(m.group(1)) == question_number:
                collecting = [raw_line.rstrip()]
            continue
        if part_header_re.match(line):
            _flush()
            stripped = raw_line.strip()
            if not stripped.startswith("## التمرين") and not stripped.startswith("# "):
                current_part = stripped
            continue
        if collecting is not None:
            collecting.append(raw_line.rstrip())
    _flush()

    if not matches:
        return None
    if len(matches) == 1:
        return matches[0]
    # ── L1 (D-206): البند الواحد لا يُسلَّم مرّتين ────────────────────────────
    # كان يُرجِع **كلّ** المطابقات مجموعةً: «البند 1» في الجزء (1) و«البند 1» في
    # الجزء (2) معاً. فردُّ «أعطني السؤال الأول فقط» كان جزأين — أوسع من الطلب.
    # نُسلِّم الأوّل ونُخبر بوجود غيره (L11: الاقتضاب لا يعني الإخفاء).
    return f"{matches[0]}\n\n_(البند {question_number} يتكرّر في جزء آخر — قل لي إن أردته.)_"


def _available_question_numbers(display_content: str) -> list[int]:
    """أرقام البنود الموجودة فعلاً في نصّ التمرين — لسؤال التوضيح (L1/L11).

    نعرض للطالب ما نملكه بصدق بدل تخمين ما يقصد. مرتّبة وبلا تكرار.
    """
    found: set[int] = set()
    numbered_re = re.compile(r"^\s*(?:\*\*)?(\d{1,2})[.)ـ-]\s*")
    for raw_line in display_content.splitlines():
        match = numbered_re.match(raw_line.translate(_ARABIC_INDIC_DIGITS))
        if match:
            found.add(int(match.group(1)))
    return sorted(found)


def detect_question_only_request(
    request: ExerciseRetrievalRequest,
    history_messages: list[dict[str, str]] | None = None,
) -> QuestionOnlyDecision:
    """يكشف طلب «السؤال رقم N فقط / بدون حل» ويُجهِّز الاقتطاع الحتمي.

    قواعد (ISS-112، مُحدَّثة بـD-206):
    1. نية الشرح تُلغي — «اشرح السؤال 2» طلبُ شرحٍ لا استرجاع.
    2. **نيّة النطاق سلطتُها `shared/exercise_scope`** — لا قوائم علامات محلّية (L6).
    3. الكيان: من السؤال (detect_exercise_retrieval) ثم من history
       (الربط البنيوي D-102 — رسائل user/assistant فقط).
    4. الرقم الغائب يُستكمل من آخر طلب مرقَّم في الحوار (داخل `resolve_scope`).
    5. صفر LLM — المحتوى من النص الرسمي فقط (display = بدون حل أصلاً).
    6. **الفشل يُقصِّر ولا يُوسِّع (L1)** — تعذُّر الاقتطاع مع «فقط» يُنتج سؤالاً
       توضيحياً واحداً، **لا** التمرين كاملاً. انظر أسفل الدالّة.
    """
    normalized = request.question.strip().lower()
    if not normalized:
        return QuestionOnlyDecision(reason="empty_question")

    if _has_explanation_intent(normalized):
        return QuestionOnlyDecision(reason="explanation_intent_wins")

    scope = resolve_scope(request.question, history_messages)
    if not scope.explicit:
        return QuestionOnlyDecision(reason="no_question_only_intent")

    question_number = scope.question_number

    retrieval = detect_exercise_retrieval(request)
    matched_entry = retrieval.matched_entry
    if matched_entry is None:
        matched_entry = _detect_entry_from_history(history_messages)
    if matched_entry is None:
        return QuestionOnlyDecision(reason="no_exercise_context", question_number=question_number)

    raw_content = load_exercise_content(matched_entry)
    if not raw_content:
        return QuestionOnlyDecision(reason="content_file_not_found")

    display_content = format_exercise_for_display(matched_entry, raw_content)

    sliced: str | None = None
    if question_number is not None:
        sliced = _extract_numbered_question(display_content, question_number)
    if sliced:
        title_line = next(
            (
                ln.strip()
                for ln in display_content.splitlines()
                if ln.strip().startswith("## التمرين")
            ),
            "",
        )
        if title_line:
            sliced = f"{title_line}\n\n{sliced}"
        reason = "question_only_sliced"
    elif scope.only:
        # ── L1 (D-206 · ISS-144): الفشل يُقصِّر ولا يُوسِّع ────────────────────
        # كان هنا `sliced = display_content` — أي أنّ الردّ على «أعطني السؤال الأول
        # **فقط**» هو التمرين **كاملاً**. مُثبَتٌ في الإنتاج (customer_messages 4590):
        # الطالب طلب بنداً واحداً فتلقّى الجدار كلّه، فأعاد طلبه فتلقّى شيئاً ثالثاً.
        # الردّ الأوسع من الطلب ليس «تساهلاً» بل نقضٌ صريح لِما قاله الطالب.
        # البديل: سؤالٌ توضيحيّ واحد قصير (L10: الصمت انضباط لا فراغ).
        numbers = _available_question_numbers(display_content)
        choices = "، ".join(str(n) for n in numbers[:6]) if numbers else ""
        sliced = (
            f"أيّ سؤال بالضبط؟ البنود المتاحة: {choices}."
            if choices
            else "أيّ سؤال من التمرين تريد؟ اذكر رقمه."
        )
        reason = "question_only_clarify"
    else:
        # بلا حصرٍ صريح («أعطني أسئلة التمرين») ⇒ النصّ الرسمي بلا حلّ مشروع.
        sliced = display_content
        reason = "question_only_full_display"

    return QuestionOnlyDecision(
        recognized=True,
        reason=reason,
        matched_entry=matched_entry,
        question_number=question_number,
        sliced_content=sliced,
    )
