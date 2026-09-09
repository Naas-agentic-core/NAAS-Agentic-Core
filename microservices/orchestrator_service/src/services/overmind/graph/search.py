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
from microservices.orchestrator_service.src.services.llm.client import (
    PROVIDER_UNAVAILABLE_MESSAGE,
    AllModelsFailedError,
)
from microservices.orchestrator_service.src.services.overmind.latex_normalizer import (
    LatexStreamNormalizer,
    normalize_latex,
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

        # D-103: محتوى تمرين محقون ⇒ الاسترجاع سيتجاوز البحث الدلالي،
        # فلا حاجة لاستخراج filters عبر DSPy (يوفّر LLM call كامل).
        if str(state.get("exercise_content") or "").strip():
            emit_telemetry(node_name="QueryAnalyzerNode", start_time=start_time, state=state)
            return {"filters": QueryFilters(question=query)}

        from .main import format_conversation_history

        # Exclude the current user query from history ONLY for prompt formatting
        prompt_messages = messages
        if messages:
            last_msg = messages[-1]
            role = (
                last_msg.get("role") or last_msg.get("type")
                if isinstance(last_msg, dict)
                else getattr(last_msg, "type", getattr(last_msg, "role", ""))
            )
            if role in ("human", "user"):
                prompt_messages = messages[:-1]
        formatted_history = format_conversation_history(prompt_messages)

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

        # D-103: محتوى تمرين محقون من الـ monolith ⇒ تجاوز البحث الدلالي كلياً.
        # المصدر الوحيد = المحتوى المحقون — لا vector DB، لا خلط تمارين، لا tags خام
        # (يُحيّد سبب منع D-052 بالبناء).
        injected_exercise = str(state.get("exercise_content") or "").strip()
        if injected_exercise:
            docs = [
                LlamaDocument(
                    text=injected_exercise,
                    metadata={"source": "محتوى التمرين المرفق", "score": 1.0},
                )
            ]
            emit_telemetry(
                node_name="InternalRetrieverNode",
                start_time=start_time,
                state=state,
                retrieval_source="injected_exercise",
            )
            return {"retrieved_docs": docs}

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

        # D-103: مستند محقون واحد لا يحتاج cross-encoder — passthrough مباشر.
        if str(state.get("exercise_content") or "").strip():
            emit_telemetry(node_name="RerankerNode", start_time=start_time, state=state)
            return {"reranked_docs": list(docs)}

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
    D-113 (Socratic No-Answer): if the source is an EXERCISE the student must solve,
    NEVER reveal the final numeric result or a step the student can generate — guide
    with questions and graded hints instead. If it is a general-knowledge question,
    answer directly. Write your output clearly in Arabic."""

    context: str = dspy.InputField(desc="The raw retrieved exercise or document text.")
    conversation: str = dspy.InputField(
        desc="The recent conversation history including the user's active constraints."
    )
    query: str = dspy.InputField(desc="The user's original query.")
    response: str = dspy.OutputField(
        desc="The final synthesized response in Arabic obeying all constraints."
    )


# ─────────────────────────────────────────────────────────────────────────────
# D-103 (Change B): استشارة reasoning-agent (:8008 MCTS) للأسئلة الرياضية
# المعقدة قبل التوليف — تعميق الرسم بالوكلاء. fail-open مطلق: أي خطأ/مهلة/
# تعطيل ⇒ "" والتوليف يتابع بدون الاستشارة. لا تفشل دور الطالب أبداً.
# ─────────────────────────────────────────────────────────────────────────────
_REASONING_CONSULT_MARKERS: tuple[str, ...] = (
    "تكامل",
    "اشتقاق",
    "مشتق",
    "نهاية",
    "معادلة تفاضلية",
    "برهن",
    "أثبت",
    "اثبت",
    "استنتج",
    "ادرس الدالة",
    "ادرس تغيرات",
    "دالة أصلية",
    "دالة اصلية",
    "متتالية",
    "عدد مركب",
    "العدد المركب",
    "أعداد مركبة",
    "اعداد مركبة",
    "الأعداد المركبة",
    "الاعداد المركبة",
    "lim",
    "integral",
    "derivative",
    "prove",
)

_REASONING_HINT_MAX_CHARS = 4000


def _is_complex_math_query(query: str) -> bool:
    """كاشف حتمي محافظ — لا LLM: السؤال معقد رياضياً فقط عند وجود marker صريح."""
    text = str(query or "").strip()
    if len(text) < 15:
        return False
    lowered = text.lower()
    return any(marker in lowered for marker in _REASONING_CONSULT_MARKERS)


async def _consult_reasoning_agent(query: str) -> str:
    """يستشير reasoning-agent ويُرجع hint نصياً — أو "" عند أي تعذّر (fail-open)."""
    from microservices.orchestrator_service.src.core.prom_metrics import (
        record_reasoning_consult,
    )

    enabled = os.environ.get("ORCHESTRATOR_REASONING_CONSULT_ENABLED", "1").strip().lower()
    if enabled in ("0", "false", "no"):
        record_reasoning_consult("disabled")
        return ""
    if not _is_complex_math_query(query):
        record_reasoning_consult("skipped")
        return ""

    try:
        # D-103: السقف الافتراضي 35s — بنشمارك حي أثبت أن MCTS (depth 1) يستغرق
        # ~23s لمسألة تكامل بالتجزئة. سقف 20s كان يُهدر الوقت ثم يُسقط الـ hint
        # دائماً (timeout). «الجودة أولاً» (طلب المستخدم) ⇒ نمنحه فرصة الإكمال.
        timeout_raw = os.environ.get("ORCHESTRATOR_REASONING_CONSULT_TIMEOUT", "35")
        timeout_s = max(1.0, float(timeout_raw or "35"))
    except (TypeError, ValueError):
        timeout_s = 35.0

    try:
        # import كسول: يسهّل الاختبار (monkeypatch) ولا يكلّف وقت import الوحدة.
        from microservices.orchestrator_service.src.infrastructure.clients.reasoning_client import (
            reasoning_client,
        )

        data = await asyncio.wait_for(reasoning_client.reason_deeply(query), timeout=timeout_s)
        if isinstance(data, dict) and not data.get("error"):
            answer = str(data.get("answer") or "").strip()
            trace = str(data.get("logic_trace") or "").strip()
            hint = answer
            if trace and trace not in hint:
                hint = (hint + "\n" + trace).strip()
            if hint:
                record_reasoning_consult("success")
                logger.info("reasoning_consult success chars=%s", len(hint))
                return hint[:_REASONING_HINT_MAX_CHARS]
        record_reasoning_consult("error")
    except TimeoutError:
        record_reasoning_consult("timeout")
        logger.warning("reasoning_consult timeout after %.1fs", timeout_s)
    except Exception as exc:
        record_reasoning_consult("error")
        logger.warning("reasoning_consult failed: %s", exc)
    return ""


def _weave_reasoning_hint(base_text: str, reasoning_hint: str) -> str:
    """يُلحق hint الاستدلال بنص الـ prompt — صيغة موحَّدة للمواضع الثلاثة."""
    if not reasoning_hint:
        return base_text
    return f"{base_text}\n\nتحليل استدلالي مساعد (تحقق منه ولا تنسخه حرفياً):\n{reasoning_hint}"


# ── D-117: البروتوكول السقراطي الطبيعي (الطالب يرى التعليم لا هندسة التعليم) ─────
# السلطة الوحيدة للتعليم هي هذا الرسم (LangGraph). تعليمات **سلوكية** يتّبعها
# النموذج ولا يَنسخها — لا قالب مُرقَّم بعناوين (D-115 كان يُسرِّب «نوع المسألة /
# سؤال تشخيصي / أصغر خطوة» حرفياً للطالب). قصير عمداً (D-067: < 1500 حرف).
_SOCRATIC_CORE_PROMPT = (
    "أنت أستاذ بكالوريا جزائري تجلس بجانب الطالب وتُعلّمه بهدوء. تحدّث بطبيعية "
    "كمعلّم حقيقي، بالعربية فقط، بجُمل قصيرة دافئة — لا جدران نص.\n"
    "حين يحلّ الطالب تمريناً: لا تكشف الجواب النهائي أبداً (لا نتيجة نهائية، لا "
    "أرقام نهائية، لا كسور، لا $$\\boxed{}$$). أعطه فكرة واحدة أو خطوة صغيرة "
    "واحدة فقط، ثم اسأله سؤالاً واحداً يقوده للخطوة التالية، وانتظر محاولته.\n"
    "اكتب كأنك تخاطبه مباشرة، مثل: «لننظر إلى هذا الجزء فقط — جرّب أن تعدّ كم "
    "احتمالاً لدينا، وأخبرني بالنتيجة لنُكمل معاً».\n"
    "ممنوع منعاً باتاً أن تكتب أي وصف لطريقة تفكيرك أو أي عنوان داخلي مثل: «نوع "
    "المسألة»، «سؤال تشخيصي»، «أصغر خطوة»، «فهمت المطلوب»، «مستوى الدعم»، «توجيه "
    "تربوي»، «وضع الشرح العميق» — هذه لغة نظام داخلية لا يراها الطالب إطلاقاً.\n"
    "ممنوع أيضاً: كشف الجواب، مثال موازٍ، تغيير الموضوع، أي لغة غير العربية، أي "
    "HTML أو رموز أقواس غريبة.\n"
    "للمعرفة العامة (سؤال ليس تمريناً يحلّه الطالب): أجب مباشرة بإيجاز."
)
_SOCRATIC_DEPTH_CLAUSES: dict[int, str] = {
    1: (
        "\nالطالب مبتدئ غارق (إتقان منخفض): ثبّت فكرة واحدة فقط بأبسط لغة. ابدأ بـ "
        "«ما المعطى؟ ما المطلوب؟» ثم خطوة واحدة صغيرة جداً — لا تُكثر."
    ),
    2: "\nالطالب يبني المفهوم: تلميح موجِّه واحد ثم خطوة واحدة صغيرة.",
    3: "\nالطالب يبني المفهوم: تلميح موجِّه واحد ثم خطوة واحدة صغيرة.",
    4: "\nالطالب متمكّن: ادفعه ليستنتج القاعدة بنفسه — «ما الفرق عن الحالة السابقة؟».",
    5: "\nالطالب متمكّن: ادفعه ليستنتج القاعدة بنفسه — «ما الفرق عن الحالة السابقة؟».",
}


def _build_socratic_prompt(support_level: int) -> str:
    """يبني نظام البروتوكول السقراطي المنضبط بعمق تلميح يتبع support_level (1..5)."""
    clause = _SOCRATIC_DEPTH_CLAUSES.get(support_level, _SOCRATIC_DEPTH_CLAUSES[3])
    return _SOCRATIC_CORE_PROMPT + clause


class SynthesizerNode:
    def __init__(self):
        self.generator = dspy.Predict(EducationalSynthesizer)

    @staticmethod
    def _get_writer():
        """D-048: stream_writer إذا توفر."""
        try:
            from langgraph.config import get_stream_writer

            return get_stream_writer()
        except Exception:
            return None

    async def __call__(self, state: dict) -> dict:
        import json

        from .telemetry import emit_telemetry

        start_time = time.time()
        reranked = state.get("reranked_docs", [])
        filters: QueryFilters = state.get("filters")
        query = state.get("query", "")
        messages = state.get("messages", [])

        # D-115: البروتوكول السقراطي المنضبط — support_level (1..5) يحكم عمق التلميح
        # فقط (لا كشف، لا مثال موازٍ). افتراض 5 آمن. يَعكِس D-114 (المثال المكشوف).
        try:
            _support_level = int(state.get("support_level") or 5)
        except (TypeError, ValueError):
            _support_level = 5
        _socratic_prompt = _build_socratic_prompt(_support_level)

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

        # ISS-121 (D-154 — M10-S2.1) + D-163 (Stage 3): معلّم الاحتمالات الحتمي داخل
        # الـ orchestrator — خطوة هجرة roadmap M10-S2 (port مستقل، صفر LLM، صفر هلوسة).
        # خلف علم `ORCHESTRATOR_PROB_TUTOR_ENABLED` — **افتراضي مُفعَّل (ON)** بعد
        # الإثبات الحي على :8006 (scripts/verify_m10s2_port_live.py — 7/7). رافعة
        # الرجوع الفوري: `ORCHESTRATOR_PROB_TUTOR_ENABLED=0` (بلا deploy — نمط D-025).
        # fail-open مطلق ⇒ مسار الـ LLM عند أي تعذّر أو عند غياب exercise_content.
        _injected_for_tutor = str(state.get("exercise_content") or "").strip()
        if _injected_for_tutor and os.environ.get(
            "ORCHESTRATOR_PROB_TUTOR_ENABLED", "1"
        ).strip().lower() in ("1", "true", "yes"):
            try:
                from microservices.orchestrator_service.src.services.overmind.probability_tutor import (
                    deterministic_turn,
                )

                _det_text = deterministic_turn(
                    question=query,
                    exercise_content=_injected_for_tutor,
                    history=recent_messages,
                    support_level=_support_level,
                )
            except Exception:
                _det_text = None
            if _det_text:
                writer = self._get_writer()
                if writer is not None:
                    writer(
                        {
                            "chunk_type": "assistant_delta",
                            "content": _det_text,
                            "node": "synthesizer",
                        }
                    )
                from langchain_core.messages import AIMessage

                logger.info("probability_tutor_deterministic_turn (M10-S2.1)")
                return {
                    "final_response": {
                        "المصدر": "معلّم الاحتمالات الحتمي",
                        "مستوى_الثقة": "1.00",
                        "التمرين": _det_text,
                        "السنة": str(filters.year) if filters else "N/A",
                        "الشعبة": filters.branch if filters else "غير محدد",
                        "المادة": filters.subject if filters else "غير محدد",
                        "رقم_التمرين": filters.exercise_num if filters else 1,
                    },
                    "messages": [AIMessage(content=_det_text)],
                }

        # D-103 (Change B): استشارة reasoning-agent للأسئلة الرياضية المعقدة —
        # fail-open: "" عند أي تعذّر، والتوليف يتابع كالمعتاد.
        reasoning_hint = await _consult_reasoning_agent(query)

        # ISS-200 (D-288): تمييز «سلسلة النماذج سقطت كلها» عن «لا يوجد سياق».
        provider_down = False

        if not reranked:
            # ISS-STREAM-002: عند عدم وجود نتائج بحث → استخدم LLM مباشرة مع streaming
            writer = self._get_writer()
            text_val = ""
            source = "معرفة عامة"
            confidence = "0.70"
            if writer is not None:
                try:
                    from microservices.orchestrator_service.src.services.llm.client import (
                        get_ai_client as get_llm_client,
                    )

                    llm_client = get_llm_client()
                    # D-115: البروتوكول السقراطي المنضبط (قالب المالك) — فرع no-docs.
                    stream_messages = [
                        {"role": "system", "content": _socratic_prompt},
                        {"role": "user", "content": _weave_reasoning_hint(query, reasoning_hint)},
                    ]
                    # D-061 (ISS-074): تطبيع LaTeX على streaming chunks
                    from microservices.orchestrator_service.src.services.overmind.response_sanitizer import (
                        sanitize_chunk,
                    )

                    normalizer = LatexStreamNormalizer()
                    parts: list[str] = []
                    async for chunk in llm_client.stream_chat(stream_messages):
                        content = llm_client.extract_stream_content(chunk)
                        if not content:
                            continue
                        for safe_chunk in normalizer.feed(content):
                            # ISS-078 D-066: sanitize chunk قبل إرساله للعميل
                            sanitized = sanitize_chunk(safe_chunk)
                            if not sanitized:
                                continue
                            parts.append(sanitized)
                            writer(
                                {
                                    "chunk_type": "assistant_delta",
                                    "content": sanitized,
                                    "node": "synthesizer",
                                }
                            )
                    for tail_chunk in normalizer.flush():
                        sanitized_tail = sanitize_chunk(tail_chunk)
                        if not sanitized_tail:
                            continue
                        parts.append(sanitized_tail)
                        writer(
                            {
                                "chunk_type": "assistant_delta",
                                "content": sanitized_tail,
                                "node": "synthesizer",
                            }
                        )
                    text_val = "".join(parts).strip()
                except AllModelsFailedError as e:
                    logger.error(
                        "Synthesizer no-docs streaming: model chain exhausted — %s (chain=%s)",
                        e,
                        llm_client.model_chain(),
                    )
                    provider_down = True
                except Exception as e:
                    logger.error(f"Synthesizer no-docs streaming failed: {e}")
            if provider_down:
                # انقطاع المُزوّد حالةُ تشغيلٍ لا جهلٌ بالموضوع: النصُّ الجاهز القديم
                # («لا توجد تفاصيل متاحة») كان يُقرأ كإجابة ويُطفئ أي إنذار.
                text_val = PROVIDER_UNAVAILABLE_MESSAGE
            elif not text_val:
                text_val = "لا توجد تفاصيل متاحة."
        else:
            raw_doc_text = reranked[0].text
            source = reranked[0].metadata.get("source", "الإنترنت")
            confidence = str(reranked[0].metadata.get("score", 0.85))

            writer = self._get_writer()
            text_val = ""
            if writer is not None:
                # D-048: STREAMING — استدعاء raw OpenAI مع stream=True + custom events
                # نُحاكي نفس قالب EducationalSynthesizer signature ولكن بـ streaming.
                try:
                    # D-115: البروتوكول السقراطي المنضبط (قالب المالك) — فرع with-docs.
                    # نفس الـ system prompt المنضبط؛ المصدر سياق مساعد لا يُكشف منه الجواب.
                    system_msg = _socratic_prompt
                    user_msg = (
                        f"المصدر (سياق مساعد — لا تنسخه ولا تكشف منه نتيجة نهائية):\n{raw_doc_text}\n\n"
                        f"محادثة الطالب:\n{conversation_text}\n\n"
                        f"السؤال الحالي: {query}"
                    )
                    # D-103: حقن hint الاستدلال عند توفره (فرع with-docs)
                    user_msg = _weave_reasoning_hint(user_msg, reasoning_hint)
                    stream_messages = [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg},
                    ]
                    from microservices.orchestrator_service.src.services.llm.client import (
                        get_ai_client as get_llm_client,
                    )

                    llm_client = get_llm_client()
                    # D-061 (ISS-074): تطبيع LaTeX على streaming chunks
                    normalizer = LatexStreamNormalizer()
                    parts: list[str] = []
                    async for chunk in llm_client.stream_chat(stream_messages):
                        try:
                            # ISS-STREAM-002: extract_stream_content يدعم ChatCompletionChunk و dict
                            content = llm_client.extract_stream_content(chunk)
                            if not content:
                                continue
                            for safe_chunk in normalizer.feed(content):
                                # ISS-078 D-066: sanitize chunk قبل إرساله للعميل
                                from microservices.orchestrator_service.src.services.overmind.response_sanitizer import (
                                    sanitize_chunk,
                                )

                                sanitized = sanitize_chunk(safe_chunk)
                                if not sanitized:
                                    continue
                                parts.append(sanitized)
                                writer(
                                    {
                                        "chunk_type": "assistant_delta",
                                        "content": sanitized,
                                        "node": "synthesizer",
                                    }
                                )
                        except Exception:
                            continue
                    for tail_chunk in normalizer.flush():
                        from microservices.orchestrator_service.src.services.overmind.response_sanitizer import (
                            sanitize_chunk,
                        )

                        sanitized_tail = sanitize_chunk(tail_chunk)
                        if not sanitized_tail:
                            continue
                        parts.append(sanitized_tail)
                        writer(
                            {
                                "chunk_type": "assistant_delta",
                                "content": sanitized_tail,
                                "node": "synthesizer",
                            }
                        )
                    text_val = "".join(parts).strip()
                except AllModelsFailedError as e:
                    logger.error(
                        "Synthesizer streaming: model chain exhausted — %s (chain=%s)",
                        e,
                        llm_client.model_chain(),
                    )
                    text_val = ""
                    provider_down = True
                except Exception as e:
                    logger.error(f"Synthesizer streaming failed: {e}")
                    text_val = ""

            if provider_down:
                # ISS-200: DSPy يستدعي نفس المزوّد الميت — إعادة المحاولة به تُضيف
                # تعليقاً فقط؛ والرجوع إلى `raw_doc_text` كان يُلقي وثيقة الاسترجاع
                # الخام للطالب كأنها شرح، وهو ما ينقضّ عليه عقد D-115 صراحةً
                # («المصدر سياق مساعد لا يُنسخ ولا يُكشف منه نتيجة»).
                text_val = PROVIDER_UNAVAILABLE_MESSAGE

            if not text_val and not provider_down:
                # Fallback إلى DSPy (batch mode أو فشل streaming)
                try:
                    # D-103: حقن hint الاستدلال في مسار DSPy batch أيضاً
                    dspy_context = _weave_reasoning_hint(raw_doc_text, reasoning_hint)
                    prediction = await anyio.to_thread.run_sync(
                        lambda: self.generator(
                            context=dspy_context, conversation=conversation_text, query=query
                        )
                    )
                    raw_pred = getattr(prediction, "response", raw_doc_text).strip()
                    # D-061: تطبيع LaTeX حتى في batch mode
                    text_val = normalize_latex(raw_pred)
                except Exception as e:
                    logger.error(f"Synthesizer LLM generation failed: {e}")
                    text_val = (
                        "عذراً، تعذر صياغة الشرح المطلوب بسبب خطأ داخلي. يرجى إعادة صياغة السؤال."
                    )

        # D-064 (ISS-076): تنظيف foreign-script للمخرج التعليمي
        from microservices.orchestrator_service.src.services.overmind.response_sanitizer import (
            sanitize_response,
        )

        # D-114: support_level==1 يُعفي كتلة المثال المحلول الملفوفة من الحجب.
        text_val = sanitize_response(text_val, intent="educational", support_level=_support_level)

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

        from langchain_core.messages import AIMessage

        # ISS-056: AIMessage carries the human-readable text ONLY.
        # The metadata envelope lives in final_response for internal use; if any
        # downstream code accidentally surfaces `messages[-1].content` to the user,
        # they get the answer, never a JSON dump.
        return {
            "final_response": response_json,
            "provider_error": provider_down,
            "messages": [
                AIMessage(
                    content=text_val
                    or (PROVIDER_UNAVAILABLE_MESSAGE if provider_down else "لا توجد تفاصيل متاحة.")
                )
            ],
        }
