"""
LangGraph StateGraph لـ conversation-service — الخطوة 12.

البنية:
  START → intent_node → context_node → response_node → END

الحالة (ConversationState):
  - question: سؤال الطالب
  - intent: educational | general | chat
  - context: سياق إضافي (مادة، مستوى، إلخ)
  - history: سجل المحادثة
  - response: الإجابة النهائية
  - thread_id: معرف الجلسة (للـ checkpointing)
  - correlation_id: للتتبع الموزع

قانون الـ Skill:
  - هذا الـ graph مستقل تماماً — لا يستورد من microservice آخر
  - كل node يُسجِّل مقاييسه في Prometheus
  - Fallback mode إلزامي عند غياب LLM
  - Timeout guard على كل ainvoke()
  - System prompt متخصص لكل نية (educational/general/chat)
"""

from __future__ import annotations

import asyncio
import logging
import os
import re as _re
import time
from typing import TypedDict

from langgraph.graph import END, START, StateGraph

from microservices.conversation_service.prom_metrics import (
    record_graph_error,
    record_graph_invocation,
)

_CYRILLIC_REPLACEMENTS = {
    "линейный": "خطي",
    "линейная": "خطية",
    "линейное": "خطية",
    "функция": "دالة",
    "уравнение": "معادلة",
    "aparece": "يظهر",
    "aparecen": "تظهر",
    "Force向心": "قوة جذب مركزية",
    "向心": "جذب مركزي",
}

# ISS-074 (D-062): علامات تفكير صوتي إنجليزي يجب حذفها من بداية ردود chat
_CHAT_ECHO_PATTERNS = [
    _re.compile(r"^Okay,\s+the user[^.\n]*\.\s*", _re.IGNORECASE),
    _re.compile(r"^First,?\s+I\s+(should|must|need|will)[^.\n]*\.\s*", _re.IGNORECASE),
    _re.compile(r"^The user greeted me[^.\n]*\.\s*", _re.IGNORECASE),
    _re.compile(r"^I need to (respond|answer|reply)[^.\n]*\.\s*", _re.IGNORECASE),
    _re.compile(r"^Let me (think|respond|answer|consider)[^.\n]*\.\s*", _re.IGNORECASE),
    _re.compile(r"^Alright,\s+the (user|question)[^.\n]*\.\s*", _re.IGNORECASE),
]


def _strip_chat_meta_narration(text: str) -> str:
    """يحذف meta-narration إنجليزي من بداية ردود chat (ISS-074)."""
    if not text:
        return text
    cleaned = text
    # كرر حتى لا يبقى pattern (في حال عدة جمل meta متتالية)
    for _ in range(5):
        prev = cleaned
        for rx in _CHAT_ECHO_PATTERNS:
            cleaned = rx.sub("", cleaned, count=1)
        cleaned = cleaned.lstrip()
        if cleaned == prev:
            break
    return cleaned


def _normalize_latex_response(text: str) -> str:
    """
    يُحوِّل \\[...\\] و \\begin{equation}...\\end{equation} إلى $$...$$ (ISS-071).
    ينظف كلمات Cyrillic/Spanish الشاذة (ISS-074 D-062).
    يُطبَّق على كل إجابة LLM قبل إرسالها للمستخدم.
    """
    if not text:
        return text
    text = _re.sub(
        r"\\\[\s*(.*?)\s*\\\]",
        lambda m: f"$$\n{m.group(1).strip()}\n$$",
        text,
        flags=_re.DOTALL,
    )
    text = _re.sub(
        r"\\begin\{equation\*?\}\s*(.*?)\s*\\end\{equation\*?\}",
        lambda m: f"$$\n{m.group(1).strip()}\n$$",
        text,
        flags=_re.DOTALL,
    )
    text = _re.sub(
        r"\\begin\{align\*?\}\s*(.*?)\s*\\end\{align\*?\}",
        lambda m: f"$$\n{m.group(1).strip()}\n$$",
        text,
        flags=_re.DOTALL,
    )
    text = _re.sub(r"\$\$\s*\$\$", "", text)
    # ISS-074 D-062: نظف الكلمات الأجنبية الشاذة
    for foreign, arabic in _CYRILLIC_REPLACEMENTS.items():
        text = text.replace(foreign, arabic)
    text = _re.sub(r"[Ѐ-ӿ]+", "", text)  # أي Cyrillic متبقٍ
    text = _re.sub(r"[一-鿿]+", "", text)  # Chinese CJK Han
    return _re.sub(r"[぀-ゟ゠-ヿ]+", "", text)  # Japanese Hiragana/Katakana


logger = logging.getLogger(__name__)

# ── ثوابت ─────────────────────────────────────────────────────────────────────
_NODE_TIMEOUT_SECONDS = 45.0
# ISS-079 (D-067 — 2026-05-17): تغيير الـ default — التجريب الحي أثبت أن
# nvidia/nemotron-nano-30b يفشل مع system prompts طويلة.
# ISS-082 (D-088 — 2026-05-27): gpt-oss-20b:free أصبح rate-limited بشكل دائم
# على OpenRouter ("Provider returned error 429"). gpt-oss-120b من نفس العائلة،
# نفس quality contract، rate limit pool مختلف. مُرقّى لـ default.
# ISS-130 (D-167 — 2026-07-14): gpt-oss-120b:free أُزيل من OpenRouter (404) — العودة للـ 20b المُتحقَّق.
# ISS-200 (D-288 — 2026-09-09): مسبار الكتالوج الحيّ (`/api/v1/models/<id>/endpoints`)
# يُظهر `"endpoints": []` لـ gpt-oss-20b:free — الحرفية الميتة نفسها كانت هنا أيضاً.
# الحُرّاس: لا يُصلَّب النموذج في `shared/ai_models/model_chain.py` وحده؛ هذه الصورة
# تُحدَّث معه (sister copy — لا استيراد: صورة هذا الخدمة لا تحمل `shared/`).
_DEFAULT_MODEL = "google/gemma-4-31b-it:free"

# سلسلة fallback — تُجرَّب بالترتيب عند 404/429 أو فشل النموذج الأساسي (D-067).
# أُزيل منها ما يضرّ ولا يفي: nemotron-3-super-120b (nvidia — محظور
# تسرّب إنجليزي في content، ISS-107)، وglm-4.5-air (reasoning-only ⇒
# content=None، D-067)، و`mistralai/mistral-7b-instruct:free` (بلا endpoint حيّ).
_FALLBACK_CHAIN: list[str] = [
    "google/gemma-4-26b-a4b-it:free",  # ✅ endpoint حيّ (2026-09-09)
    "nvidia/nemotron-3.5-lightning:free",  # ✅ endpoint حيّ — 1M ctx (D-280)
    "openai/gpt-oss-20b:free",  # 🕳 0 endpoints حالياً — فتحة تعافٍ آلي (demoted 2026-09-09)
    "meta-llama/llama-3.3-70b-instruct:free",
    "google/gemma-3-27b-it:free",
]

_INTENT_PATTERNS: dict[str, list[str]] = {
    "educational": [
        "اشرح",
        "حل",
        "تمرين",
        "مسألة",
        "قانون",
        "نظرية",
        "درس",
        "رياضيات",
        "فيزياء",
        "كيمياء",
        "بكالوريا",
        "باك",
        "احسب",
        "أوجد",
        "برهن",
        "ادرس",
        "تكامل",
        "مشتق",
        "معادلة",
        "دالة",
        "متجه",
        "مصفوفة",
        "احتمال",
        "إحصاء",
        "هندسة",
        "جبر",
        "expliquer",
        "exercice",
        "problème",
        "loi",
        "théorème",
        "calculer",
        "trouver",
        "démontrer",
        "étudier",
        "dériver",
        "intégrer",
        "équation",
        "fonction",
        "vecteur",
        "matrice",
    ],
    "chat": [
        "مرحبا",
        "أهلا",
        "كيف حالك",
        "شكرا",
        "وداعا",
        "bonjour",
        "merci",
        "salut",
        "hello",
        "hi",
        "صباح",
        "مساء",
        "ليلة",
        "سلام",
    ],
}

# ── System Prompts المتخصصة ────────────────────────────────────────────────────
_SYSTEM_PROMPTS: dict[str, str] = {
    "educational": (
        "أنت أستاذ رياضيات وعلوم عبقري متخصص في البكالوريا الجزائرية.\n"
        "مهمتك: أن يفهم الطالب فهماً عميقاً حقيقياً — إدراكاً لا حفظاً.\n\n"
        "## قواعد اللغة — صارمة لا تُخرق\n"
        "- اكتب بالعربية الفصحى الواضحة فقط\n"
        "- لا تخلط مع الروسية أو الإنجليزية أو الفرنسية إلا للمصطلحات التقنية\n"
        "- المصطلحات التقنية: اكتبها بالعربية أولاً ثم الأجنبية بين قوسين\n\n"
        "## قواعد LaTeX — صارمة لا تُخرق أبداً\n"
        "- المعادلات المستقلة: $$...$$ فقط — لا تستخدم \\[...\\] أبداً\n"
        "- الرموز المضمّنة في النص: \\(...\\)\n"
        "- النتائج النهائية: $$\\boxed{...}$$\n"
        "- مثال صحيح: $$f'(x) = 2x \\cdot e^{3x} + 3x^2 \\cdot e^{3x}$$\n"
        "- مثال خاطئ: \\[f'(x) = 2x\\] — هذا ممنوع تماماً\n"
        "- مثال صحيح: الدالة \\(f(x) = x^2 e^{-x}\\) معرَّفة على \\(\\mathbb{R}\\)\n"
        "- مثال صحيح: $$\\lim_{x\\to+\\infty} \\frac{x^2+1}{e^x} = 0$$\n\n"
        "## منهجية الشرح العبقري (6 مراحل)\n"
        "1. **لماذا؟** — ابدأ بالسؤال: لماذا نحتاج هذه الطريقة؟ ما المشكلة التي تحلها؟\n"
        "2. **الفكرة الجوهرية** — اشرح المبدأ الرياضي بكلمات بسيطة قبل الرموز\n"
        "3. **الخطوات المرقمة** — كل خطوة في سطر منفصل مع تبرير رياضي واضح\n"
        "4. **الحسابات التفصيلية** — لا تتخطى خطوة واحدة — الطالب يحتاج كل التفاصيل\n"
        "5. **النتيجة في صندوق** — $$\\boxed{\\text{النتيجة النهائية}}$$\n"
        "6. **التفسير الواقعي** — ماذا تعني النتيجة في الفيزياء أو الهندسة أو الحياة؟\n\n"
        "## مواد البكالوريا الجزائرية\n"
        "**رياضيات:** التحليل (الدوال، التكامل، المعادلات التفاضلية)، الجبر "
        "(الأعداد المركبة، المصفوفات)، الإحصاء والاحتمالات، الهندسة التحليلية\n"
        "**فيزياء:** الميكانيك (قوانين نيوتن، الطاقة)، الكهرباء، الموجات، الفيزياء الحديثة\n"
        "**كيمياء:** الكيمياء العضوية وغير العضوية، التوازنات الكيميائية\n\n"
        "## قاعدة 2016\n"
        "سنة 2016 هي السنة الوحيدة في تاريخ بكالوريا الجزائر بدورتين. "
        "تحقق دائماً من الدورة المقصودة.\n\n"
        "## أسلوب الشرح\n"
        "- ابدأ بـ «لماذا نستخدم هذه الطريقة؟» قبل الحساب\n"
        "- اربط المفاهيم بالحياة الواقعية والفيزياء والهندسة\n"
        "- استخدم التشبيهات والأمثلة الملموسة لتثبيت المفهوم\n"
        "- إذا كان السؤال غامضاً، اطرح توضيحاً قبل الإجابة\n"
        "- لا تختصر — الطالب يحتاج الفهم الكامل\n"
        "- شجّع الطالب وأكد له أن الرياضيات ممتعة وليست صعبة"
    ),
    "general": (
        "أنت مساعد ذكي متخصص في خدمة الطلاب الجزائريين.\n"
        "أجب بالعربية الفصحى الواضحة فقط — لا تخلط اللغات.\n"
        "أجب بدقة علمية مع الاستناد إلى سياق المحادثة السابقة.\n"
        "استخدم LaTeX للرموز الرياضية: $$...$$ للمعادلات و \\(...\\) للرموز المضمّنة.\n"
        "قدّم إجابات منظمة بعناوين وخطوات واضحة.\n"
        "لا تُشر إلى تفاصيل داخلية أو بنية النظام."
    ),
    "chat": (
        "أنت مساعد ودود وذكي للطلاب الجزائريين.\n"
        "رد مباشرة بالعربية الفصحى — لا تكتب تفكيراً صوتياً بالإنجليزية.\n"
        "اكتب ردك فقط، لا تشرح ماذا ستفعل أو ماذا فهمت من السؤال.\n"
        "كن مختصراً (سطر أو سطرين)، إيجابياً، ومحفزاً.\n"
        "إذا كان السؤال تعليمياً، شجّع الطالب على طرحه كاملاً."
    ),
}


# ── State TypedDict ────────────────────────────────────────────────────────────


class ConversationState(TypedDict):
    """حالة المحادثة — تمر عبر جميع nodes."""

    question: str
    intent: str  # educational | general | chat
    subject: str  # math | physics | chemistry | general — يُكتشف في context_node
    enriched_question: str  # السؤال المُعزَّز بسياق المادة
    history: list[dict[str, str]]  # [{role, content}, ...]
    response: str
    thread_id: str
    correlation_id: str
    error: str | None
    # payload الواجهة التوليدية — يُملأ من Math Pipeline عند subject==math
    ui_component: dict | None


# ── دوال مساعدة ───────────────────────────────────────────────────────────────


def _classify_intent(question: str) -> str:
    """يُصنِّف نية السؤال بدون LLM — deterministic."""
    q_lower = question.lower()
    for intent, patterns in _INTENT_PATTERNS.items():
        if any(p in q_lower for p in patterns):
            return intent
    return "general"


def _build_fallback_response(question: str, intent: str) -> str:
    """يبني إجابة fallback عند غياب LLM أو انتهاء المهلة."""
    if intent == "educational":
        return (
            f"سؤالك التعليمي: «{question}»\n\n"
            "⚠️ خدمة الذكاء الاصطناعي غير متاحة حالياً. "
            "يُرجى المحاولة مرة أخرى بعد لحظات."
        )
    if intent == "chat":
        return "مرحباً! كيف يمكنني مساعدتك اليوم؟"
    return f"تم استلام سؤالك: «{question}» — يُرجى المحاولة مرة أخرى."


def _get_system_prompt(intent: str) -> str:
    """يُعيد system prompt المناسب للنية — مع دعم override من البيئة."""
    custom = os.environ.get("CONVERSATION_SYSTEM_PROMPT", "").strip()
    if custom:
        return custom
    return _SYSTEM_PROMPTS.get(intent, _SYSTEM_PROMPTS["general"])


def _get_max_tokens(intent: str) -> int:
    """يُحدد الحد الأقصى للـ tokens حسب النية."""
    if intent == "educational":
        return int(os.environ.get("CONVERSATION_MAX_TOKENS_EDU", "1500"))
    if intent == "chat":
        return int(os.environ.get("CONVERSATION_MAX_TOKENS_CHAT", "200"))
    return int(os.environ.get("CONVERSATION_MAX_TOKENS_GENERAL", "800"))


async def _call_llm_if_available(
    question: str,
    intent: str,
    history: list[dict[str, str]],
) -> str:
    """
    يستدعي LLM عبر OpenRouter مع system prompt متخصص.

    - يختار system prompt حسب النية (educational/general/chat)
    - يُرسل آخر 8 رسائل من السياق
    - يُعيد fallback عند غياب المفتاح أو الفشل
    - ISS-069: يتحقق من content != None قبل الإعادة
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        return _build_fallback_response(question, intent)

    # بناء قائمة النماذج: النموذج المُحدَّد أولاً ثم سلسلة الـ fallback
    primary = os.environ.get("CONVERSATION_LLM_MODEL", _DEFAULT_MODEL)
    model_chain = [primary] + [m for m in _FALLBACK_CHAIN if m != primary]

    system_prompt = _get_system_prompt(intent)
    max_tokens = _get_max_tokens(intent)

    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    # آخر 8 رسائل من السياق لتجنب تجاوز حد الـ context
    for h in history[-8:]:
        if isinstance(h, dict) and h.get("role") and h.get("content"):
            messages.append({"role": h["role"], "content": h["content"]})
    messages.append({"role": "user", "content": question})

    import httpx

    last_exc: Exception | None = None
    for model in model_chain:
        try:
            async with httpx.AsyncClient(timeout=40.0) as client:
                resp = await client.post(
                    "https://openrouter.ai/api/v1/chat/completions",
                    headers={
                        "Authorization": f"Bearer {api_key}",
                        "Content-Type": "application/json",
                        "HTTP-Referer": "https://cogniforge.dz",
                        "X-Title": "CogniForge BAC Tutor",
                    },
                    json={
                        "model": model,
                        "messages": messages,
                        "max_tokens": max_tokens,
                        "temperature": 0.3,  # ISS-072: 0.3 للتعليم — أقل تشتتاً من 0.7
                    },
                )
                # 429 → جرّب النموذج التالي في السلسلة
                if resp.status_code == 429:
                    logger.warning("model=%s returned 429 — trying next in chain", model)
                    continue
                resp.raise_for_status()
                data = resp.json()
                choices = data.get("choices", [])
                if not choices:
                    logger.warning(
                        "LLM returned no choices model=%s: %s", model, data.get("error", {})
                    )
                    continue

                msg = choices[0].get("message", {})
                # ISS-069: بعض نماذج reasoning تضع الإجابة في reasoning لا content
                # D-067: لا نُمرِّر reasoning كـ content — إذا content=None نجرّب النموذج التالي
                content = msg.get("content") or ""
                if not content or not content.strip():
                    logger.warning("LLM returned empty content model=%s — trying next", model)
                    continue

                # ISS-071 + ISS-074: تطبيع LaTeX + تنظيف foreign scripts + chat meta-narration
                cleaned = _normalize_latex_response(content.strip())
                if intent == "chat":
                    cleaned = _strip_chat_meta_narration(cleaned)
                logger.info("LLM success model=%s intent=%s", model, intent)
                return cleaned

        except Exception as exc:
            last_exc = exc
            logger.warning("LLM call failed model=%s: %s — trying next", model, exc)
            continue

    logger.error("All models in chain failed. Last error: %s", last_exc)
    return _build_fallback_response(question, intent)


# ── دوال تحليل المادة ─────────────────────────────────────────────────────────

_SUBJECT_PATTERNS: dict[str, list[str]] = {
    "math": [
        "رياضيات",
        "تكامل",
        "مشتق",
        "دالة",
        "معادلة",
        "جبر",
        "مصفوفة",
        "احتمال",
        "إحصاء",
        "هندسة",
        "متجه",
        "مركب",
        "حد",
        "تسلسل",
        "sin",
        "cos",
        "tan",
        "log",
        "ln",
        "∫",
        "∑",
        "∏",
        "lim",
        "math",
        "intégrale",
        "dérivée",
        "fonction",
        "équation",
    ],
    "physics": [
        "فيزياء",
        "قوة",
        "طاقة",
        "سرعة",
        "تسارع",
        "كهرباء",
        "موجة",
        "ضوء",
        "حرارة",
        "ضغط",
        "كتلة",
        "نيوتن",
        "كولوم",
        "أوم",
        "physique",
        "force",
        "énergie",
        "vitesse",
        "accélération",
    ],
    "chemistry": [
        "كيمياء",
        "تفاعل",
        "عنصر",
        "مركب",
        "أيون",
        "حمض",
        "قاعدة",
        "أكسدة",
        "اختزال",
        "مول",
        "تركيز",
        "chimie",
        "réaction",
    ],
}


def _detect_subject(question: str) -> str:
    """يكتشف المادة الدراسية من السؤال."""
    q_lower = question.lower()
    for subject, patterns in _SUBJECT_PATTERNS.items():
        if any(p in q_lower for p in patterns):
            return subject
    return "general"


def _enrich_question(question: str, subject: str, intent: str) -> str:
    """يُعزِّز السؤال بسياق المادة لتحسين جودة الإجابة."""
    if intent != "educational":
        return question
    subject_context = {
        "math": "في مادة الرياضيات (بكالوريا جزائرية):",
        "physics": "في مادة الفيزياء (بكالوريا جزائرية):",
        "chemistry": "في مادة الكيمياء (بكالوريا جزائرية):",
        "general": "",
    }
    prefix = subject_context.get(subject, "")
    if prefix and not question.startswith(prefix):
        return f"{prefix}\n{question}"
    return question


# ── Graph Nodes ────────────────────────────────────────────────────────────────


async def intent_node(state: ConversationState) -> ConversationState:
    """
    يُصنِّف نية السؤال.

    Input:  state.question
    Output: state.intent
    Metrics: cogniforge_conversation_graph_invocations_total{node="intent"}
    """
    t0 = time.perf_counter()
    try:
        intent = _classify_intent(state["question"])
        duration = time.perf_counter() - t0
        record_graph_invocation("intent", "success", duration)
        return {**state, "intent": intent}
    except Exception as exc:
        duration = time.perf_counter() - t0
        record_graph_invocation("intent", "error", duration)
        record_graph_error("state_error")
        logger.error("intent_node error: %s", exc)
        return {**state, "intent": "general", "error": str(exc)}


async def context_node(state: ConversationState) -> ConversationState:
    """
    يُحلِّل سياق السؤال ويُعزِّزه بمعلومات المادة الدراسية.

    Input:  state.question, state.intent
    Output: state.subject, state.enriched_question
    Metrics: cogniforge_conversation_graph_invocations_total{node="context"}
    """
    t0 = time.perf_counter()
    try:
        subject = _detect_subject(state["question"])
        enriched = _enrich_question(state["question"], subject, state.get("intent", "general"))
        duration = time.perf_counter() - t0
        record_graph_invocation("context", "success", duration)
        return {**state, "subject": subject, "enriched_question": enriched}
    except Exception as exc:
        duration = time.perf_counter() - t0
        record_graph_invocation("context", "error", duration)
        record_graph_error("context_error")
        logger.error("context_node error: %s", exc)
        return {
            **state,
            "subject": "general",
            "enriched_question": state["question"],
            "error": str(exc),
        }


async def response_node(state: ConversationState) -> ConversationState:
    """
    يُولِّد الإجابة — يُوجِّه الأسئلة الرياضية للـ Math Pipeline المتخصص.

    التوجيه:
    - subject == "math" AND intent == "educational" → Math Pipeline (4 nodes)
    - غير ذلك → LLM مباشر مع system prompt متخصص

    Input:  state.enriched_question, state.intent, state.subject, state.history
    Output: state.response
    Metrics: cogniforge_conversation_graph_invocations_total{node="response"}
    """
    t0 = time.perf_counter()
    question_to_use = state.get("enriched_question") or state["question"]
    intent = state.get("intent", "general")
    subject = state.get("subject", "general")

    try:
        # توجيه الأسئلة الرياضية للـ Math Pipeline المتخصص
        if subject == "math" and intent == "educational":
            try:
                from microservices.conversation_service.src.math_pipeline import (
                    invoke_math_pipeline,
                )

                pipeline_result = await asyncio.wait_for(
                    invoke_math_pipeline(
                        question=state["question"],
                        thread_id=state.get("thread_id", "default"),
                        history=state.get("history", []),
                    ),
                    timeout=_NODE_TIMEOUT_SECONDS,
                )
                response = pipeline_result.get("final_response", "")
                if response and len(response) > 50:
                    duration = time.perf_counter() - t0
                    record_graph_invocation("response", "success", duration)
                    # تمرير ui_component من Math Pipeline للحالة
                    return {
                        **state,
                        "response": response,
                        "ui_component": pipeline_result.get("ui_component"),
                    }
                # fallback للـ LLM المباشر إذا كان الـ pipeline فارغاً
            except Exception as pipe_exc:
                logger.warning("math_pipeline failed, falling back to direct LLM: %s", pipe_exc)

        # LLM مباشر للأسئلة غير الرياضية أو عند فشل الـ pipeline
        response = await asyncio.wait_for(
            _call_llm_if_available(
                question_to_use,
                intent,
                state.get("history", []),
            ),
            timeout=_NODE_TIMEOUT_SECONDS,
        )
        duration = time.perf_counter() - t0
        record_graph_invocation("response", "success", duration)
        return {**state, "response": response}

    except TimeoutError:
        duration = time.perf_counter() - t0
        record_graph_invocation("response", "timeout", duration)
        record_graph_error("timeout")
        fallback = _build_fallback_response(state["question"], intent)
        return {**state, "response": fallback, "error": "timeout"}
    except Exception as exc:
        duration = time.perf_counter() - t0
        record_graph_invocation("response", "error", duration)
        record_graph_error("llm_error")
        logger.error("response_node error: %s", exc)
        fallback = _build_fallback_response(state["question"], intent)
        return {**state, "response": fallback, "error": str(exc)}


# ── Graph Builder ──────────────────────────────────────────────────────────────


def build_conversation_graph() -> StateGraph:
    """
    يبني StateGraph للمحادثة.

    Topology: START → intent_node → context_node → response_node → END

    - intent_node: يُصنِّف النية (educational/general/chat)
    - context_node: يكتشف المادة ويُعزِّز السؤال
    - response_node: يُولِّد الإجابة بـ system prompt متخصص
    """
    builder = StateGraph(ConversationState)
    builder.add_node("intent_node", intent_node)
    builder.add_node("context_node", context_node)
    builder.add_node("response_node", response_node)
    builder.add_edge(START, "intent_node")
    builder.add_edge("intent_node", "context_node")
    builder.add_edge("context_node", "response_node")
    builder.add_edge("response_node", END)
    return builder.compile()


# ── Singleton ──────────────────────────────────────────────────────────────────

# Singleton: مُهيَّأ مرة واحدة عند الإقلاع، مُحقَن عبر get_conversation_graph()
_conversation_graph: object | None = None


def get_conversation_graph() -> object:
    """يُعيد الـ graph المُهيَّأ — lazy singleton."""
    global _conversation_graph
    if _conversation_graph is None:
        _conversation_graph = build_conversation_graph()
    return _conversation_graph


async def invoke_graph(
    question: str,
    thread_id: str,
    correlation_id: str,
    history: list[dict[str, str]] | None = None,
) -> dict:
    """
    يستدعي الـ graph ويُعيد النتيجة.

    يُستخدم من main.py فقط — abstraction barrier.
    يُعيد: response, intent, subject, error, ui_component
    """
    graph = get_conversation_graph()
    initial_state: ConversationState = {
        "question": question,
        "intent": "general",
        "subject": "general",
        "enriched_question": question,
        "history": history or [],
        "response": "",
        "thread_id": thread_id,
        "correlation_id": correlation_id,
        "error": None,
        "ui_component": None,
    }
    config = {"configurable": {"thread_id": thread_id}}
    result = await graph.ainvoke(initial_state, config=config)
    return {
        "response": result.get("response", ""),
        "intent": result.get("intent", "general"),
        "subject": result.get("subject", "general"),
        "error": result.get("error"),
        "ui_component": result.get("ui_component"),
    }
