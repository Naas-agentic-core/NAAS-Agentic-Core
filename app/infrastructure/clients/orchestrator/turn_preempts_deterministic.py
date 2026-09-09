"""D-170 Stage A1: مراحل الـ preempt الحتمية الأولى لدور الدردشة.

بوابة السياسة (D-144/D-145/D-158) ثم التحية (ISS-079) ثم شريحة السؤال المرقّم
(ISS-112) ثم الإجابة الحسابية (D-143). كتل منقولة من `chat_with_agent` بنمط
sub-generator + `TurnContext` — الترتيب يحكمه المُنسِّق في `chat_turn.py`.

إصلاح مرافق (D-170): إعادة تسمية ظلّ `obs = PolicyObservation(...)` إلى
`policy_obs` — الظلّ كان يقتل كل نداءات `obs.end_span` اللاحقة صامتاً."""

from __future__ import annotations

import contextlib
import logging
import time
import uuid
from collections.abc import AsyncGenerator

from app.infrastructure.clients.orchestrator.turn_context import TurnContext

# نفس اسم الـ logger القديم عمداً — استمرارية السجلات (نمط D-163/D-164).
logger = logging.getLogger("orchestrator-client")


class TurnPreemptsDeterministicMixin:
    """المراحل الحتمية: بوابة السياسة، التحية، السؤال المرقّم، الإجابة الحسابية."""

    async def _stage_policy_gate(self, ctx: TurnContext) -> AsyncGenerator[dict | str, None]:
        """بوابة السياسة (D-144) + defer (D-145) + محرّك الدور المعرفي (D-158) + الحلّ الرمزي."""
        from app.services.skills.concept_diagnosis_skill import (
            ConceptDiagnosisInput,
            get_concept_diagnosis_skill,
        )
        from app.services.skills.pedagogical_policy_engine import (
            PedagogicalPolicyEngine,
            PolicyObservation,
        )

        question = ctx.question
        history_messages = ctx.history_messages
        context = ctx.context
        # Extract current state (ISS-131: القيمة قد تكون None صراحةً — طبِّعها إلى dict
        # مع الحفاظ على هوية الـ dict المشترك حين يوجد — هو قناة الـ handoff لـ record_turn)
        _ts_raw = context.get("tutor_state") if isinstance(context, dict) else None
        tutor_state = _ts_raw if isinstance(_ts_raw, dict) else {}

        # Formulate Observation
        ConceptDiagnosisInput(question=question, history=history_messages)
        diagnosis = get_concept_diagnosis_skill().diagnose_deterministic(question)

        is_correct = self._verify_answer_against_combo(
            question, self._load_canonical_combinations(question, history_messages)
        )

        policy_obs = PolicyObservation(
            question=question,
            active_concept=diagnosis.concept or tutor_state.get("active_concept", ""),
            is_correct=is_correct,
            has_misconception=bool(diagnosis.misconception),
            detected_misconception=diagnosis.misconception or "",
            is_frustrated=False,  # Could be inferred from sentiment, using default
        )

        # Consult Policy Engine
        engine = PedagogicalPolicyEngine()
        policy_decision = engine.evaluate_turn(tutor_state, policy_obs)

        # ISS-131 (D-169): الحقن في dict الـ tutor_state **المشترك** — هو ما يقرأه
        # `customer_chat.record_turn` فعلاً (`tutor_state_ctx.get("policy_decision")`).
        # الحقن القديم في context الأعلى (D-144) لم يقرأه أحد قط، وكان يُسمِّم جسم
        # HTTP نحو الـ orchestrator (dataclass غير قابل لـ JSON ⇒ فشل كل المرشّحين
        # ⇒ ORCHESTRATOR_REQUIRED للأسئلة العامة). القرار الداخلي لا يركب السلك أبداً
        # (يُجرَّد في `_sanitize_wire_context`).
        if isinstance(tutor_state, dict):
            tutor_state["policy_decision"] = policy_decision

        # ── L2 (D-206 · ISS-144): نطاق الطالب عقد لا اقتراح ────────────────────
        # الجذر الحقيقي للكارثة، مُتحقَّقاً وقت التشغيل: الطالب قال «لقد طلبت السؤال
        # الأول فقط»، و`detect_question_only_request` **كشفته صحيحاً** (n=1)، لكنّ هذه
        # البوّابة — وهي المرحلة الأولى — بثّت probe الألوان وأنهت الدور، فلم تُشغَّل
        # `_stage_question_only` (المرحلة الثالثة) أبداً. أي أنّ العطب لم يكن في الكشف
        # بل في **الأسبقيّة**: أجندةُ النظام سبقت طلبَ الطالب الصريح.
        #
        # الحالة تُحسَب بعد `policy_decision` عمداً: الحالة التربوية تُحدَّث دائماً
        # (فلا نفقد `tutor_state`)، ولا نتنحّى إلّا عن **البثّ**.
        _scope_defers = self._scope_request_defers(question, history_messages)

        # Enforce Symbolic Truth explicitly: if question targets unmodeled mathematical event, force drift prevention
        _comp = (
            None
            if _scope_defers
            else await self._build_probability_computational_answer(question, history_messages)
        )
        if _comp:
            _comp_text, _comp_event = _comp
            if _comp_event.startswith("defer_"):
                # Strict drift prevention: Unmodeled event
                yield self._normalize_stream_event(
                    {"type": "assistant_delta", "payload": {"content": _comp_text}}
                )
                yield self._normalize_stream_event(
                    {"type": "assistant_final", "payload": {"content": ""}}
                )
                ctx.turn_complete = True
                return

        # D-158: طبقة القرار الموحَّدة فوق tutor_state المُخزَّن (خلف COGNITIVE_TURN_ENABLED،
        # افتراض OFF ⇒ سلوك اليوم دون تغيير). عند التفعيل تعترض دور الاحتمالات وتُصدِر خطوة
        # واحدة تدريجية (تقتل التفريغ + التكرار + سجن 600-حرف بنيوياً). fail-open ⇒ تسليم للكتل.
        if self._cognitive_turn_enabled() and not _scope_defers:
            _ct_text, _ct_delta = self._cognitive_turn(
                question, history_messages, tutor_state, policy_decision
            )
            if _ct_text:
                yield self._normalize_stream_event(
                    {"type": "assistant_delta", "payload": {"content": _ct_text}}
                )
                yield self._normalize_stream_event(
                    {"type": "assistant_final", "payload": {"content": ""}}
                )
                ctx.turn_complete = True
                return

        # In D-144, if the policy engine mandates a specific pedagogical action (e.g. symbolic reveal or intermediate scaffold)
        # we bypass the standard generative fallbacks and directly emit that action.
        if policy_decision.next_action == "symbolic_reveal" and not _scope_defers:
            # ISS-148: دفتر ما سُلِّم — بدونه يُعاد تفريغ ما رآه الطالب أصلاً.
            from app.services.skills.kc_progress_schema import delivered_steps

            _reveal_text = self._build_symbolic_reveal(
                question,
                history_messages,
                acknowledge=policy_obs.is_correct,
                delivered=delivered_steps(tutor_state),
            )
            if _reveal_text:
                yield self._normalize_stream_event(
                    {"type": "assistant_delta", "payload": {"content": _reveal_text}}
                )
                yield self._normalize_stream_event(
                    {"type": "assistant_final", "payload": {"content": ""}}
                )
                ctx.turn_complete = True
                return
        ctx.tutor_state = tutor_state

    @staticmethod
    def _scope_request_defers(question: str, history_messages: list[dict[str, str]] | None) -> bool:
        """هل يتنحّى بثُّ بوّابة السياسة لطلب نطاقٍ صريح من الطالب؟ (L2 · D-206)

        **الشرط مزدوج عمداً**: نيّة نطاقٍ صريحة **و** مرحلةٌ لاحقة تستطيع خدمتها فعلاً
        (`detect_question_only_request(...).recognized`). التنحّي بالشرط الأوّل وحده
        يُنتج **دوراً صامتاً** حين لا يوجد تمرينٌ في السياق — وهو استبدالُ كارثةٍ
        بأخرى أسوأ (§0: «لا فشل صامت»؛ L1: الفشل يُقصِّر ولا يُلغي الردّ).

        `fail-closed` عمداً: أيّ استثناء ⇒ `False` ⇒ يبقى سلوك البوّابة كما كان.
        الخطأ هنا يجب أن يُعيد النظامَ إلى حالته السابقة لا أن يُسكِته.
        """
        try:
            from app.services.capabilities.exercise_retrieval import (
                ExerciseRetrievalRequest,
                detect_question_only_request,
            )
            from shared.exercise_scope import resolve_scope

            if not resolve_scope(question, history_messages).explicit:
                return False
            decision = detect_question_only_request(
                ExerciseRetrievalRequest(question=question), history_messages
            )
            if decision.recognized:
                logger.info(
                    "scope_request_preempts_policy_gate",
                    extra={"reason": decision.reason, "n": decision.question_number},
                )
                return True
            return False
        except Exception:  # pragma: no cover - fail-closed
            logger.warning("scope_defer_check_failed", exc_info=True)
            return False

    async def _stage_greeting(self, ctx: TurnContext) -> AsyncGenerator[dict | str, None]:
        """التحية الحتمية (ISS-079/D-067) — أعلى أولوية، صفر LLM."""
        question = ctx.question
        obs = ctx.obs
        _root_ctx = ctx.root_ctx
        _t0 = ctx.t0
        # ─────────────────────────────────────────────────────────────────────
        # ISS-079 (D-067 — 2026-05-17): Greeting Fast-Path Preemption
        # كارثة المستخدم: "السلام عليكم" → رد etymological طويل بكلمات أجنبية
        # ("hopephe pepe aaaa" / "وتُستَخدم كتعبير ترحيبي" بدلاً من رد التحية)
        # السبب: نماذج OpenRouter المجانية تفسر التحية كسؤال علمي تحت
        # "أجب بدقة" system prompt → etymology طويلة بدلاً من رد بسيط.
        # الحل: ردود deterministic للتحيات الشائعة (0ms، 100% نظيف).
        # ─────────────────────────────────────────────────────────────────────
        try:
            from app.services.chat.local_graph import _greeting_fastpath_response

            greeting_response = _greeting_fastpath_response(question)
        except Exception:
            # D-158: أُزيل هنا التكرار الميت (PedagogicalPolicyEngine/evaluate_turn +
            # فحص defer مكرَّر يُهمَل ناتجه) الذي كان يعمل فقط لو فشل استيراد التحية.
            # المنطق الحقيقي (policy + defer) يجري مرة واحدة في أعلى الدالة.
            greeting_response = None

        if greeting_response:
            logger.info(
                "greeting_fastpath_preempt",
                extra={
                    "request_id": str(uuid.uuid4()),
                    "question_len": len(question),
                    "reason": "matched_greeting_fastpath",
                },
            )
            # ابث الرد كقطعة واحدة (التحية قصيرة بطبعها)
            yield self._normalize_stream_event(
                {"type": "assistant_delta", "payload": {"content": greeting_response}}
            )
            yield self._normalize_stream_event(
                {"type": "assistant_final", "payload": {"content": ""}}
            )
            if _root_ctx:
                with contextlib.suppress(Exception):
                    obs.end_span(
                        _root_ctx.span_id,
                        status="OK",
                        metrics={
                            "duration_ms": (time.perf_counter() - _t0) * 1000,
                            "fallback_path": 0.25,  # greeting = أعلى أولوية
                            "stream_chars": float(len(greeting_response)),
                        },
                    )
            ctx.turn_complete = True
            return

    async def _stage_question_only(self, ctx: TurnContext) -> AsyncGenerator[dict | str, None]:
        """شريحة السؤال المرقّم (ISS-112) — اقتطاع حتمي من النص الرسمي، صفر LLM."""
        question = ctx.question
        history_messages = ctx.history_messages
        obs = ctx.obs
        _root_ctx = ctx.root_ctx
        _t0 = ctx.t0
        # ─────────────────────────────────────────────────────────────────────
        # ISS-112 — «أعطني السؤال رقم N فقط» (question-only preempt):
        # يسبق الاسترجاع المُفهرَس: طلب سؤال مرقَّم محدد يجب أن يُقتطع من النص
        # الرسمي (صفر LLM) لا أن يُغرق الطالب بالتمرين كاملاً أو — أسوأ —
        # بحل مُهلوَس. نية الشرح («اشرح السؤال 2») لا تُختطف (الكاشف يرفضها).
        # صفر قطع مبثوثة ⇒ المسار يتابع طبيعياً (fail-open).
        # ─────────────────────────────────────────────────────────────────────
        qo_streamed_chars = 0
        try:
            async for chunk in self._stream_question_only_response(question, history_messages):
                if not chunk:
                    continue
                qo_streamed_chars += len(chunk)
                yield self._normalize_stream_event(
                    {"type": "assistant_delta", "payload": {"content": chunk}}
                )
        except Exception:
            logger.warning("question_only_preempt_failed", exc_info=True)

        if qo_streamed_chars > 0:
            if _root_ctx:
                with contextlib.suppress(Exception):
                    obs.end_span(
                        _root_ctx.span_id,
                        status="OK",
                        metrics={
                            "duration_ms": (time.perf_counter() - _t0) * 1000,
                            "fallback_path": 0.4,  # بين التحية والاسترجاع المُفهرَس
                            "stream_chars": float(qo_streamed_chars),
                        },
                    )
            yield self._normalize_stream_event(
                {"type": "assistant_final", "payload": {"content": ""}}
            )
            ctx.turn_complete = True
            return

    async def _stage_computational(self, ctx: TurnContext) -> AsyncGenerator[dict | str, None]:
        """الإجابة الحسابية الحتمية للاحتمالات (D-143/ISS-117) — قبل سُلّم الحادثة A."""
        question = ctx.question
        history_messages = ctx.history_messages
        # ─────────────────────────────────────────────────────────────────────
        # D-143 (ISS-117): أسئلة الاحتمالات الحسابية تُجاب حتمياً **قبل** سُلّم الحادثة A.
        # «لماذا نضرب 11×10×9» ⇒ مبدأ العدّ؛ «كيف حصلنا على 56» ⇒ الحادثة B (56/165 من أرقام
        # الكرات)؛ الحوادث غير المنمذجة (C/D/X/الأمل/الشرطي) ⇒ تأجيل حتمي صادق يُبعدها عن A.
        # صفر LLM في مسار الرياضيات (نقد المالك #1). يكسر اختطاف المصفوفة للأسئلة الحسابية.
        # ─────────────────────────────────────────────────────────────────────
        _comp = await self._build_probability_computational_answer(question, history_messages)
        if _comp is not None:
            _comp_text, _comp_event = _comp
            # D-143 (RC-4): لا تُعَد الإجابة الحسابية نفسها حرفياً عند تكرار السؤال. عند
            # التكرار نتقدّم لتمثيلٍ حتميّ **مختلف** (تخصيص بيداغوجي، نقد المالك #2) ثم
            # لمُوجِّه تقدّم — صفر LLM، صفر تكرار حرفي. لو استُنفِدت كلّها ⇒ نُسلّم للطبقة التالية.
            _comp_outcome = (
                "correct_event" if _comp_event in ("event_b", "combinations") else "deferred"
            )
            _comp_emit = True
            if self._recently_emitted(_comp_text, history_messages):
                _comp_var = self._probability_computational_variant(_comp_event, history_messages)
                if _comp_var and not self._recently_emitted(_comp_var, history_messages):
                    _comp_text, _comp_outcome = _comp_var, "advanced"
                else:
                    _comp_adv = self._probability_computational_advance_prompt()
                    if not self._recently_emitted(_comp_adv, history_messages):
                        _comp_text, _comp_outcome = _comp_adv, "advanced"
                    else:
                        _comp_emit = False
            if _comp_emit:
                with contextlib.suppress(Exception):
                    from app.services.skills.tutor_metrics import record_probability_routing

                    record_probability_routing(_comp_event, _comp_outcome)
                _comp_chars = 0
                async for chunk in self._stream_markdown_typing(_comp_text):
                    if not chunk:
                        continue
                    _comp_chars += len(chunk)
                    yield self._normalize_stream_event(
                        {"type": "assistant_delta", "payload": {"content": chunk}}
                    )
                if _comp_chars > 0:
                    logger.info(
                        "probability_computational_answer",
                        extra={
                            "event": _comp_event,
                            "outcome": _comp_outcome,
                            "stream_chars": float(_comp_chars),
                        },
                    )
                    yield self._normalize_stream_event(
                        {"type": "assistant_final", "payload": {"content": ""}}
                    )
                    ctx.turn_complete = True
                    return
