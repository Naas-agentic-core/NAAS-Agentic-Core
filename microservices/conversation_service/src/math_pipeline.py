"""
LangGraph Math Pipeline — CogniForge BAC Tutor.

البنية (3 nodes — مُحسَّنة 2026-05-15 ISS-071):
  START → classify_node (deterministic) → solve_node (LLM) → normalize_node (deterministic) → END

دروس مُكتسَبة:
  ISS-070: 3 nodes × LLM = meta-text كارثي → الحل: node واحد للـ LLM.
  ISS-071 (2026-05-15): النموذج يستخدم \\[...\\] بدلاً من $$...$$ رغم التعليمات.
    الحل: normalize_node يُحوِّل كل صيغ LaTeX إلى $$...$$ بعد الـ LLM.
  ISS-072 (2026-05-15): temperature=0.7 يُسبب تشتتاً في الإجابات الرياضية.
    الحل: temperature=0.2 للرياضيات.
"""

from __future__ import annotations

import asyncio
import logging
import os
import re as _re
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

logger = logging.getLogger(__name__)

_NODE_TIMEOUT = 40.0
# ISS-079 (D-067 — 2026-05-17): تغيير الـ default — nvidia/nemotron-nano-30b
# يفشل مع system prompts طويلة (content=None، reasoning بالإنجليزية).
# تجريب حي حقيقي أثبت أن gpt-oss-20b هو الأنسب (عربي + LaTeX + content مضمون).
# ISS-082 (D-088 — 2026-05-27): gpt-oss-20b:free أصبح rate-limited بشكل دائم
# على OpenRouter. gpt-oss-120b من نفس العائلة، نفس quality contract،
# rate limit pool مختلف. مُرقّى لـ default للـ math pipeline.
# ISS-130 (D-167 — 2026-07-14): gpt-oss-120b:free أُزيل من OpenRouter (404) — العودة للـ 20b المُتحقَّق.
# ISS-200 (D-288 — 2026-09-09): gpt-oss-20b:free بلا endpoint الآن (`"endpoints": []`).
_DEFAULT_MODEL = "google/gemma-4-31b-it:free"
# ISS-074 (2026-05-15): fallback chain مُحدَّث بعد بنشمارك حي
# - google/gemma-4-26b-a4b-it:free → rate-limited 429 (مُزال)
# - qwen/qwen3-coder:free          → rate-limited 429 (مُزال)
# - الترتيب: الأسرع → الأقوى → الأكبر
# D-288: أُزيل منها ما يُنتج garbage بدل إجابة:
# - nemotron-3-super-120b (nvidia) → **محظور** في كل طبقة: تسرّب إنجليزي في content (ISS-107)
# - `z-ai/glm-4.5-air:free` → reasoning-only ⇒ content=None (D-067)
_FALLBACK_MODELS = [
    "google/gemma-4-26b-a4b-it:free",  # ✅ endpoint حيّ (2026-09-09) — عربي + LaTeX
    "nvidia/nemotron-3.5-lightning:free",  # ✅ endpoint حيّ — 1M ctx (فتحة D-280 المُجرَّبة في CI)
    "openai/gpt-oss-20b:free",  # 🕳 0 endpoints حالياً — فتحة تعافٍ آلي (demoted 2026-09-09)
]

# ISS-074: ترتيب الأنواع حسب التخصيص (أكثر تحديداً → أقل تحديداً)
# function_study و differential_eq قبل derivative لتجنب false positives
_MATH_TYPES: dict[str, list[str]] = {
    "function_study": [
        # ISS-074: bare "ادرس" was overmatching genuine sequence questions like
        # "ادرس تقاربية المتتالية". Require an explicit function/study marker.
        "ادرس الدالة",
        "ادرس دالة",
        "ادرس f",
        "ادرس g",
        "ادرس h",
        "دراسة الدالة",
        "tableau de variation",
        "تغيرات الدالة",
        "إشارة الدالة",
        "جدول التغيرات",
        "ادرس تغيرات",
    ],
    "differential_eq": [
        "معادلة تفاضلية",
        "équation différentielle",
        "y''",
        "y' +",
        "y' =",
        "ED:",
        "EDO",
    ],
    "derivative": ["مشتق", "اشتقاق", "مشتقة", "f'(", "dérivée", "dériver"],
    "integral": ["تكامل", "∫", "intégrale", "intégrer", "primitive", "احسب التكامل"],
    "limit": [
        "نهاية الدالة",
        "نهاية عند",
        "lim(",
        "lim ",
        "limite",
        "∞",
        "لانهاية",
        "lim_",
        "limit",
    ],
    "matrix": ["مصفوفة", "matrice", "déterminant", "عكسية المصفوفة", "محدد المصفوفة"],
    "sequence": ["متتالية", "suite", "تقاربية", "divergente", "حدود المتتالية"],
    "equation": ["معادلة", "حل المعادلة", "equation", "résoudre", "جذر", "حلول"],
    "probability": ["احتمال", "probabilité", "عشوائي", "حادثة", "variable aléatoire"],
    "complex": ["مركب", "complexe", "module", "argument", "conjugué", "i² = -1"],
    "geometry": ["هندسة", "géométrie", "مستقيم", "مستوى", "متجه", "vecteur"],
}

_TYPE_LABELS: dict[str, str] = {
    "derivative": "📐 مسألة اشتقاق",
    "integral": "∫ مسألة تكامل",
    "limit": "∞ مسألة نهايات",
    "equation": "⚖️ مسألة معادلات",
    "function_study": "📊 دراسة دالة",
    "probability": "🎲 مسألة احتمالات",
    "complex": "🔢 أعداد مركبة",
    "matrix": "🔲 مصفوفات",
    "geometry": "📐 هندسة تحليلية",
    "sequence": "🔢 متتاليات",
    "differential_eq": "📈 معادلة تفاضلية",
}

_MATH_HINTS: dict[str, str] = {
    "derivative": "استخدم قاعدة الضرب (uv)' = u'v + uv' وقاعدة السلسلة",
    "integral": "فكِّر في التكامل بالتجزئة أو التعويض",
    "limit": "جرِّب التحليل أو قاعدة لوبيتال أو المكافئات المقاربية",
    "equation": "عزِّل المجهول أو حلِّل إلى عوامل",
    "function_study": "ابدأ بالمجال ثم المشتق ثم جدول التغيرات",
    "probability": "حدِّد الفضاء الاحتمالي ثم طبِّق القانون المناسب",
    "complex": "حوِّل بين الشكل الجبري والمثلثي والأسي",
    "matrix": "احسب المحدد أولاً",
    "geometry": "استخدم المتجهات والمعادلات الديكارتية",
    "sequence": "حدِّد نوع المتتالية ثم طبِّق القانون",
    "differential_eq": "ابحث عن الحل المتجانس أولاً ثم الحل الخاص",
    "general_math": "",
}

# System prompt — ISS-074 (2026-05-15) — concise + positive instructions
# الدرس: قائمة طويلة من الممنوعات تجعل النموذج يُكرِّرها كنص.
# الحل: تعليمات إيجابية مختصرة + مثال مباشر للأسلوب المطلوب.
_MATH_SYSTEM = (
    "أنت أستاذ رياضيات للبكالوريا الجزائرية. اشرح بالعربية الفصحى لطالب مبتدئ.\n\n"
    "قواعد LaTeX:\n"
    "- استخدم $$...$$ للمعادلات المستقلة\n"
    "- استخدم \\(...\\) للرموز داخل النص\n"
    "- اكتب النتيجة النهائية في $$\\boxed{...}$$\n\n"
    "منهجية الشرح:\n"
    "1. اشرح لماذا نستخدم هذه الطريقة في سطر\n"
    "2. اكتب الخطوات مرقمة مع كل عملية حسابية\n"
    "3. ضع النتيجة النهائية في صندوق\n"
    "4. أضف تفسيراً قصيراً لمعنى النتيجة\n\n"
    "ابدأ مباشرة بالحل — بدون تمهيد أو تفكير صوتي."
)

# ISS-074 (2026-05-15): _META_MARKERS مُحدَّث — قائمة أكثر دقة.
# - فقط عبارات meta-narration حقيقية (تفكير صوتي قبل البدء)
# - لا تطابق طبيعي مع "Let me work" داخل شرح علمي
# - نقحص فقط أول 150 char من الإجابة (حيث meta-text حقيقي يظهر)
_META_MARKERS = [
    "We need to",
    "Must output",
    "produce analysis",
    "I need to provide",
    "Let me think",
    "Let me start by",
    "I'll think",
    "I'll work through",
    "I should think",
    "I must analyze",
    "First, let me",
    "Okay, so",
    "Alright, let",
]

# ISS-074: علامات echo للـ system prompt (يحدث في نماذج صغيرة على أسئلة معقدة)
_SYSTEM_PROMPT_ECHO_MARKERS = [
    "$$...$$ for equations",
    "$$ for equations",
    "$$ for independent equations",
    "$$ for display equations",
    "$$ for display",
    "$$ for inline",
    "$$ for final",
    "$$...$$ for inline",
    "$$...$$ for display",
    "Provide methodology",
    "Must use $$",
    "Must not use",
    "Must follow methodology",
    "for inline? Actually",
    "for inline symbols",
    "for inline display",
    "for equations, ",
    "methodology: explain",
    "steps numbered, final",
    "for boxed",
    "in boxed",
]
_META_CHECK_PREFIX_LEN = 200  # نتحقق فقط من بداية الإجابة

# ── دالة تطبيع LaTeX (ISS-071) ────────────────────────────────────────────────
# `_re` is imported at the top of the file (E402 compliance).


def _normalize_latex(text: str) -> str:
    """
    يُحوِّل جميع صيغ LaTeX إلى $$...$$ الموحَّدة.

    المشكلة (ISS-071): النموذج يستخدم \\[...\\] و \\begin{equation}...\\end{equation}
    بدلاً من $$...$$ رغم التعليمات الصريحة في system prompt.
    الحل: post-processing deterministic بعد كل استجابة LLM.

    التحويلات:
      \\[ ... \\]                    → $$ ... $$
      \\begin{equation} ... \\end{equation} → $$ ... $$
      \\begin{align} ... \\end{align}       → $$ ... $$
      \\begin{aligned} ... \\end{aligned}   → $$ ... $$
    """
    if not text:
        return text

    # \\[ ... \\] → $$ ... $$  (multiline)
    text = _re.sub(
        r"\\\[\s*(.*?)\s*\\\]",
        lambda m: f"$$\n{m.group(1).strip()}\n$$",
        text,
        flags=_re.DOTALL,
    )

    # \\begin{equation} ... \\end{equation} → $$ ... $$
    text = _re.sub(
        r"\\begin\{equation\*?\}\s*(.*?)\s*\\end\{equation\*?\}",
        lambda m: f"$$\n{m.group(1).strip()}\n$$",
        text,
        flags=_re.DOTALL,
    )

    # \\begin{align} ... \\end{align} → $$ ... $$
    text = _re.sub(
        r"\\begin\{align\*?\}\s*(.*?)\s*\\end\{align\*?\}",
        lambda m: f"$$\n{m.group(1).strip()}\n$$",
        text,
        flags=_re.DOTALL,
    )

    # \\begin{aligned} ... \\end{aligned} → $$ ... $$
    text = _re.sub(
        r"\\begin\{aligned\*?\}\s*(.*?)\s*\\end\{aligned\*?\}",
        lambda m: f"$$\n{m.group(1).strip()}\n$$",
        text,
        flags=_re.DOTALL,
    )

    # تنظيف: $$ $$ متعددة متتالية → $$ واحدة
    return _re.sub(r"\$\$\s*\$\$", "", text)


def _clean_foreign_scripts(text: str) -> str:
    """
    ISS-074 (D-062): ينظف خلط لغات شاذ في المخرَج.

    الـ Whitelist:
    - عربي + لاتيني (للأسماء التقنية sin/cos/lim/dx) → مسموح
    - علامات LaTeX → مسموح

    الـ Blacklist (يُحذَف):
    - Cyrillic (روسي): `линейный`, `функция`, …
    - Chinese/Japanese: 向心, 函数, …
    - Spanish فقط: `aparece`, …
    """
    if not text:
        return text
    # 1) استبدالات Russian شائعة بمقابلها العربي
    replacements = {
        "линейный": "خطي",
        "линейная": "خطية",
        "линейное": "خطية",
        "функция": "دالة",
        "уравнение": "معادلة",
        "aparece": "يظهر",
        "aparecen": "تظهر",
        "Force向心": "قوة جذب مركزية",
        "قوة向心": "قوة جذب مركزية",
        "向心": "جذب مركزي",
        "向力": "قوة الجذب",
    }
    for foreign, arabic in replacements.items():
        text = text.replace(foreign, arabic)
    # 2) أي Cyrillic متبقٍ → احذف
    text = _re.sub(r"[Ѐ-ӿ]+", "", text)
    # 3) Chinese/CJK Han → احذف (أبجدية كاملة منفصلة، ليست تقنية)
    text = _re.sub(r"[一-鿿]+", "", text)
    # 4) Hiragana / Katakana → احذف
    return _re.sub(r"[぀-ゟ゠-ヿ]+", "", text)


def _strip_meta_prefix(text: str) -> str:
    """
    ISS-074: يحذف meta-narration من بداية الإجابة، يحتفظ بالمحتوى الجوهري.

    استراتيجية:
    1. ابحث عن أول معادلة LaTeX ($$ أو \\() أو ##/**عنوان قسم
    2. إذا وُجد قبله meta-marker → اقطع من بداية المحتوى الفعلي
    3. وإلا → أعد النص كما هو
    """
    if not text:
        return text
    # ابحث عن أول علامة على بدء المحتوى الفعلي
    candidates = []
    for marker in (
        "$$",
        "\\(",
        "##",
        "**الخطوة",
        "**المعادلة",
        "**الحل",
        "**1.",
        "1.",
        "**القاعدة",
        "**لماذا",
    ):
        i = text.find(marker)
        if i >= 0:
            candidates.append(i)
    if not candidates:
        return text
    start = min(candidates)
    # إذا كان start في أول 30 char، لا meta — أعد كما هو
    if start <= 30:
        return text
    # تأكد أن ما قبل start فيه meta-text (وليس بداية شرعية)
    prefix = text[:start]
    if not any(m in prefix for m in _META_MARKERS):
        return text
    # احذف meta-prefix
    return text[start:].strip()


def _classify_math_type(question: str) -> str:
    q_lower = question.lower()
    for math_type, patterns in _MATH_TYPES.items():
        if any(p in q_lower for p in patterns):
            return math_type
    return "general_math"


def _get_math_context(math_type: str) -> str:
    return _MATH_HINTS.get(math_type, "")


class MathPipelineState(TypedDict):
    question: str
    math_type: str
    math_hint: str
    solution: str
    final_response: str
    history: list[dict[str, str]]
    thread_id: str
    error: str | None
    # payload الواجهة التوليدية — يُملأ في enrich_node
    ui_component: dict | None


async def _call_openrouter(
    system_prompt: str,
    user_prompt: str,
    max_tokens: int = 1500,
    model: str | None = None,
) -> str:
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return ""

    chosen = model or os.environ.get("MATH_PIPELINE_MODEL", _DEFAULT_MODEL)
    models_to_try = [chosen, *_FALLBACK_MODELS]

    try:
        import httpx

        for m in models_to_try:
            try:
                async with httpx.AsyncClient(timeout=35.0) as client:
                    resp = await client.post(
                        "https://openrouter.ai/api/v1/chat/completions",
                        headers={
                            "Authorization": f"Bearer {api_key}",
                            "Content-Type": "application/json",
                            "HTTP-Referer": "https://cogniforge.dz",
                            "X-Title": "CogniForge Math Pipeline",
                        },
                        json={
                            "model": m,
                            "messages": [
                                {"role": "system", "content": system_prompt},
                                {"role": "user", "content": user_prompt},
                            ],
                            "max_tokens": max_tokens,
                            "temperature": 0.2,  # ISS-072: 0.2 للرياضيات — أقل تشتتاً
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    choices = data.get("choices", [])
                    if choices:
                        msg = choices[0].get("message", {})
                        # ISS-069: reasoning models put answer in "reasoning" not "content"
                        content = msg.get("content") or msg.get("reasoning") or ""
                        if content and content.strip():
                            return content.strip()
                    logger.warning("math_pipeline: empty content from %s", m)
            except Exception as e:
                logger.warning("math_pipeline: model %s failed: %s", m, e)
                continue
    except ImportError:
        logger.error("math_pipeline: httpx not available")
    return ""


async def classify_node(state: MathPipelineState) -> MathPipelineState:
    """Node 1 — Deterministic. لا LLM → لا meta-text ممكن."""
    math_type = _classify_math_type(state["question"])
    math_hint = _get_math_context(math_type)
    return {**state, "math_type": math_type, "math_hint": math_hint}


async def solve_node(state: MathPipelineState) -> MathPipelineState:
    """Node 2 — LLM واحد، prompt مباشر، الحل الكامل."""
    t0 = time.perf_counter()
    question = state["question"]
    math_type = state["math_type"]
    math_hint = state["math_hint"]
    label = _TYPE_LABELS.get(math_type, "📚 رياضيات")

    # سياق المحادثة السابقة
    history_ctx = ""
    if state.get("history"):
        recent = [h for h in state["history"][-4:] if h.get("content")]
        if recent:
            lines = "\n".join(f"{h['role']}: {h['content']}" for h in recent)
            history_ctx = f"\n\nسياق المحادثة:\n{lines}"

    hint_line = f"\nتلميح: {math_hint}" if math_hint else ""
    user_prompt = f"{question}{hint_line}{history_ctx}"

    try:
        solution = await asyncio.wait_for(
            _call_openrouter(_MATH_SYSTEM, user_prompt, max_tokens=1500),
            timeout=_NODE_TIMEOUT,
        )

        if not solution or len(solution.strip()) < 20:
            solution = _build_fallback_solution(question, math_type)
        else:
            # ISS-074: meta-text + system-prompt-echo detection — فحص prefix
            prefix = solution[:_META_CHECK_PREFIX_LEN]
            meta_hit = next((m for m in _META_MARKERS if m in prefix), None)
            echo_hit = next((m for m in _SYSTEM_PROMPT_ECHO_MARKERS if m in prefix), None)
            if echo_hit and not meta_hit:
                meta_hit = echo_hit  # treat echo as meta-text for the retry path
            if meta_hit:
                # حاول strip-and-keep أولاً (احتفظ بالمحتوى الجيد)
                stripped = _strip_meta_prefix(solution)
                if stripped and len(stripped.strip()) > 100:
                    logger.info(
                        "math_pipeline: stripped meta-prefix (%r) — kept %d chars",
                        meta_hit,
                        len(stripped),
                    )
                    solution = stripped
                else:
                    # ISS-074: retry على نموذج آخر عند echo/meta — كان nemotron-super-120B،
                    # وهو **محظور** منذ ISS-107 لأنه يسرّب التفكير الإنجليزي داخل `content`
                    # (أي أن محاولة «الإصلاح» كانت تُنتج النص الخاطئ الذي تراه الطالب).
                    # D-288: النموذج البديل هو أول سلسلة احتياط حيّة (gemma-4-26b) —
                    # مختلفٌ عمّا فشل، ومُتحقَّق منه عربياً+LaTeX وبنقطة خدمةٍ حيّة.
                    logger.warning(
                        "math_pipeline: meta-text/echo detected (%r), retrying on %s",
                        meta_hit,
                        _FALLBACK_MODELS[0],
                    )
                    retry = await asyncio.wait_for(
                        _call_openrouter(
                            (
                                "أستاذ رياضيات. اشرح بالعربية الفصحى فقط.\n"
                                "LaTeX: $$...$$ للمعادلات، \\(...\\) للرموز. النتيجة في $$\\boxed{...}$$.\n"
                                "ابدأ مباشرة بـ: 'لحساب ...' أو 'نطبق قاعدة ...' بدون تمهيد."
                            ),
                            question,
                            max_tokens=1500,
                            model=_FALLBACK_MODELS[0],
                        ),
                        timeout=_NODE_TIMEOUT,
                    )
                    if retry and len(retry.strip()) > 100:
                        retry_prefix = retry[:_META_CHECK_PREFIX_LEN]
                        if not any(m in retry_prefix for m in _META_MARKERS):
                            solution = retry
                        else:
                            # حتى الـ retry فيه meta — احتفظ بالمحتوى الأطول والأنظف
                            solution = _strip_meta_prefix(retry) or retry

        elapsed = time.perf_counter() - t0
        logger.info(
            "math_pipeline.solve: type=%s chars=%d time=%.2fs", math_type, len(solution), elapsed
        )
        final = f"## {label}\n\n{solution}"
        return {**state, "solution": solution, "final_response": final}

    except TimeoutError:
        logger.warning("math_pipeline.solve: timeout")
        fb = _build_fallback_solution(question, math_type)
        return {
            **state,
            "solution": fb,
            "final_response": f"## {label}\n\n{fb}",
            "error": "timeout",
        }
    except Exception as exc:
        logger.error("math_pipeline.solve error: %s", exc)
        fb = _build_fallback_solution(question, math_type)
        return {**state, "solution": fb, "final_response": f"## {label}\n\n{fb}", "error": str(exc)}


def _build_ui_component(
    math_type: str,
    solution: str,
    question: str,
) -> dict:
    """
    يبني payload الواجهة التوليدية من الحل النصي.

    الفصل المعماري (القانون الأعلى):
      - هذه الدالة هي الخلفية (العقل المنطقي)
      - تُحلِّل النص وتُنظِّم البيانات في هيكل واضح
      - الواجهة (MathExplanationCard) تُحوِّل هذا الهيكل إلى قصة بصرية
      - لا خلط بين الطبقتين أبداً

    الخوارزمية:
      1. استخرج الخطوات من النص (كل سطر يبدأ بـ رقم أو ** هو خطوة)
      2. استخرج الحدس (أول فقرة قبل أي معادلة)
      3. أضف الاستعارة البصرية حسب نوع المسألة
      4. أضف التلميح من _MATH_HINTS
    """
    label = _TYPE_LABELS.get(math_type, "📚 رياضيات")
    hint = _MATH_HINTS.get(math_type, "")

    # ── استخراج الحدس: أول فقرة نصية قبل أي معادلة LaTeX ──────────────────
    intuition = ""
    lines = solution.split("\n")
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        # توقف عند أول معادلة أو عنوان أو خطوة مرقمة
        if stripped.startswith("$$") or stripped.startswith("##") or stripped.startswith("**"):
            break
        if _re.match(r"^\d+[\.\)]\s", stripped):
            break
        if len(stripped) > 20:
            intuition = stripped
            break

    # ── استخراج الخطوات: أسطر مرقمة أو عناوين ** ──────────────────────────
    steps: list[dict] = []
    current_step: dict | None = None
    content_buffer: list[str] = []

    def _flush_step() -> None:
        nonlocal current_step
        if current_step is not None:
            current_step["content"] = "\n".join(content_buffer).strip()
            steps.append(current_step)
            current_step = None
            content_buffer.clear()

    for line in lines:
        stripped = line.strip()
        # عنوان خطوة: **نص** أو رقم. نص
        numbered = _re.match(r"^(\d+)[\.\)]\s+(.+)", stripped)
        bold_title = _re.match(r"^\*\*([^*]+)\*\*\s*(.*)$", stripped)

        if numbered:
            _flush_step()
            current_step = {"id": f"step-{len(steps)}", "title": numbered.group(2)[:80]}
            content_buffer.clear()
        elif bold_title and len(bold_title.group(1)) < 60:
            _flush_step()
            title = bold_title.group(1).strip()
            rest = bold_title.group(2).strip()
            current_step = {"id": f"step-{len(steps)}", "title": title}
            content_buffer.clear()
            if rest:
                content_buffer.append(rest)
        elif current_step is not None:
            content_buffer.append(stripped)

    _flush_step()

    # ISS-108 (D-097): حارس ضد الخطوات الوهمية — نرفض الشظايا (عنوان بلا محتوى،
    # أو جملة ختامية/تحية مثل «أتمنى أن تكون الفكرة واضحة»، أو «بالعربي»). بطاقة
    # الخطوات صالحة فقط لخطوات حقيقية لها محتوى. كان النثر الحر يُقطَّع لـ «خطوات»
    # عشوائية (مؤكَّد حياً msg 3411). كما أُزيل fallback تقسيم الفقرات «الجزء {i}».
    non_step_phrases = (
        "أتمنى",
        "بالعربي",
        "موفق",
        "إذا بقي",
        "إذا احتجت",
        "أخبرني",
        "بالتوفيق",
        "خلاصة",
    )

    def _is_real_step(s: dict) -> bool:
        title = str(s.get("title", "")).strip()
        content = str(s.get("content", "")).strip()
        if not title or len(title) < 4:
            return False
        if not content or len(content) < 20:
            return False
        return not any(ph in title for ph in non_step_phrases)

    steps = [s for s in steps if _is_real_step(s)]

    # ── الاستعارات البصرية حسب نوع المسألة ────────────────────────────────
    visual_metaphors: dict[str, str] = {
        "derivative": (
            "تخيّل أنك تقود سيارة — المشتق هو عدّاد السرعة اللحظية، "
            "لا المسافة الكلية. كلما كانت الدالة تصعد بسرعة، كان المشتق أكبر."
        ),
        "integral": (
            "التكامل هو مساحة الشكل تحت المنحنى — كأنك تملأ حوضاً بالماء "
            "شريحة رفيعة بعد شريحة، وتجمع كل الشرائح معاً."
        ),
        "limit": (
            "النهاية هي الوجهة التي تقترب منها دون أن تصلها بالضرورة — "
            "كأنك تمشي نحو جدار وتقترب منه خطوة نصف خطوة، إلى ما لا نهاية."
        ),
        "probability": (
            "الاحتمال هو عالم موازٍ — نحتفظ فيه فقط بالحالات التي حقّقت الشرط، ونحسب نسبتها من الكل."
        ),
        "function_study": (
            "دراسة الدالة كأنك ترسم خريطة طريق — تبدأ بالمجال (أين الطريق موجود؟)، "
            "ثم المشتق (أين يصعد وأين ينزل؟)، ثم جدول التغيرات (الخريطة الكاملة)."
        ),
        "equation": (
            "المعادلة ميزان — ما تفعله في الطرف الأيسر يجب أن تفعله في الأيمن. "
            "هدفك: عزل المجهول وحده على أحد الطرفين."
        ),
        "matrix": (
            "المصفوفة جدول بيانات ذكي — كل عملية عليها تُحوِّل الفضاء الهندسي "
            "بطريقة محددة: تمديد، تدوير، أو انعكاس."
        ),
        "complex": (
            "العدد المركب نقطة في مستوى ثنائي الأبعاد — المحور الأفقي للجزء الحقيقي، "
            "والمحور الرأسي للجزء التخيلي. الضرب = دوران وتمديد."
        ),
        "sequence": (
            "المتتالية قائمة أرقام لها قانون خفي — اكتشف القانون وستتنبأ بأي حد مهما كان بعيداً."
        ),
        "differential_eq": (
            "المعادلة التفاضلية تصف كيف يتغير شيء ما بمرور الوقت — "
            "كنمو السكان أو تبريد كوب القهوة. الحل هو الدالة التي تصف هذا التغير."
        ),
    }

    metaphor = visual_metaphors.get(math_type, "")

    return {
        "component": "math_explanation_card",
        "props": {
            "math_type": math_type,
            "label": label,
            "intuition": intuition,
            "steps": steps[:8],  # حد أقصى 8 خطوات لتجنب الازدحام
            "hint": hint,
            "visual_metaphor": metaphor,
        },
        "fallbackText": f"شرح {label}",
    }


def _build_fallback_solution(question: str, math_type: str) -> str:
    hint = _get_math_context(math_type)
    hint_line = f"\n\n**تلميح:** {hint}" if hint else ""
    return (
        f"**المسألة:** {question}"
        f"{hint_line}\n\n"
        "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً. يُرجى المحاولة مرة أخرى."
    )


async def normalize_node(state: MathPipelineState) -> MathPipelineState:
    """
    Node 3 — Deterministic post-processing. لا LLM → ضمان أمان.

    يُصحِّح:
    - ISS-071: \\[...\\] → $$...$$ و \\begin{equation}...\\end{equation} → $$...$$
    - ISS-074: كلمات Cyrillic/Greek في نص عربي
    """
    solution = state.get("solution", "")
    if solution:
        normalized = _normalize_latex(solution)
        normalized = _clean_foreign_scripts(normalized)
        label = _TYPE_LABELS.get(state["math_type"], "📚 رياضيات")
        final = f"## {label}\n\n{normalized}"
        return {**state, "solution": normalized, "final_response": final}
    return state


async def enrich_node(state: MathPipelineState) -> MathPipelineState:
    """
    Node 4 — Deterministic. يبني payload الواجهة التوليدية.

    الفصل المعماري (القانون الأعلى):
      - هذا الـ node هو الخلفية (العقل المنطقي)
      - يُحلِّل الحل النصي ويُنظِّم البيانات في هيكل ui_component
      - الواجهة (MathExplanationCard) تُحوِّل هذا الهيكل إلى قصة بصرية
      - لا LLM هنا → لا meta-text ممكن → أمان تام

    يُنتج ui_component فقط عند وجود حل حقيقي (> 50 حرف).
    """
    solution = state.get("solution", "")
    math_type = state.get("math_type", "general_math")
    question = state.get("question", "")

    if solution and len(solution.strip()) > 50:
        try:
            ui_component = _build_ui_component(math_type, solution, question)
            return {**state, "ui_component": ui_component}
        except Exception as exc:
            logger.warning("enrich_node: failed to build ui_component: %s", exc)

    return {**state, "ui_component": None}


def build_math_pipeline() -> object:
    """
    يبني LangGraph Math Pipeline.
    Topology: START → classify → solve → normalize → enrich → END

    Node 4 (enrich): يبني ui_component payload للواجهة التوليدية.
    """
    builder = StateGraph(MathPipelineState)
    builder.add_node("classify", classify_node)
    builder.add_node("solve", solve_node)
    builder.add_node("normalize", normalize_node)
    builder.add_node("enrich", enrich_node)
    builder.add_edge(START, "classify")
    builder.add_edge("classify", "solve")
    builder.add_edge("solve", "normalize")
    builder.add_edge("normalize", "enrich")
    builder.add_edge("enrich", END)
    return builder.compile()


# Singleton: initialised once at startup, reused across requests
_math_pipeline: object | None = None


def get_math_pipeline() -> object:
    global _math_pipeline
    if _math_pipeline is None:
        _math_pipeline = build_math_pipeline()
    return _math_pipeline


async def invoke_math_pipeline(
    question: str,
    thread_id: str,
    history: list[dict[str, str]] | None = None,
) -> dict:
    """
    يستدعي Math Pipeline ويُعيد:
      final_response, math_type, solution, error, ui_component

    ui_component: payload الواجهة التوليدية (MathExplanationCard) أو None.
    """
    pipeline = get_math_pipeline()
    initial_state: MathPipelineState = {
        "question": question,
        "math_type": "general_math",
        "math_hint": "",
        "solution": "",
        "final_response": "",
        "history": history or [],
        "thread_id": thread_id,
        "error": None,
        "ui_component": None,
    }
    config = {"configurable": {"thread_id": thread_id}}
    result = await pipeline.ainvoke(initial_state, config=config)
    return {
        "final_response": result.get("final_response", ""),
        "math_type": result.get("math_type", "general_math"),
        "solution": result.get("solution", ""),
        "error": result.get("error"),
        "ui_component": result.get("ui_component"),
    }
