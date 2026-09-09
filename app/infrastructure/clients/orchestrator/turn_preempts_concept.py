"""D-170 Stage A2: مراحل تعليم المفهوم + الاسترجاع المُفهرَس.

المصفوفة التصعيدية (D-138) ثم التعريفي (D-132) ثم المثال (D-136) ثم الإصغاء
النشط (D-130) ثم الاسترجاع المُفهرَس (D-101). الترتيب النسبي محفوظ حرفياً —
بوّابات الترتيب تقرأ المصدر المُركَّب عبر `TUTOR_SOURCE_FILES`."""

from __future__ import annotations

import contextlib
import logging
import time
import uuid
from collections.abc import AsyncGenerator

from app.infrastructure.clients.orchestrator.turn_context import TurnContext

# نفس اسم الـ logger القديم عمداً — استمرارية السجلات (نمط D-163/D-164).
logger = logging.getLogger("orchestrator-client")


class TurnPreemptsConceptMixin:
    """مراحل تعليم المفهوم: التصعيد، التعريف، المثال، الإصغاء النشط، الاسترجاع."""

    async def _stage_escalation_matrix(self, ctx: TurnContext) -> AsyncGenerator[dict | str, None]:
        """المصفوفة التصعيدية التكيّفية (D-138/D-139/D-147/D-159) — تعليم مفهوم مُسمّى."""
        question = ctx.question
        history_messages = ctx.history_messages
        context = ctx.context
        tutor_state = ctx.tutor_state
        # ─────────────────────────────────────────────────────────────────────
        # ISS-116 (D-138 — المصفوفة التصعيدية التكيّفية): تعليم **مفهوم مُسمّى** عبر
        # Escalation Matrix + Understanding-Signal + Misconception-Check، مُعايَرةً بقدرة
        # الطالب (support_level/BKT). concept-scoped ⇒ لا انحراف لـ event-A؛ ذاكرة التصعيد ⇒
        # لا تكرار؛ «اعطني مثال عددي» ⇒ محاكاة مصغّرة حتمية (L3)؛ دليل فهم ⇒ توقّف؛ مفهوم خاطئ ⇒
        # تدخّل مُوجَّه. المسار الأساسي لتعليم المفهوم المعروف؛ preempt التعريف أدناه يبقى
        # للمفاهيم الجديدة غير المُسجَّلة (LLM Listener-Definer). حكم المالك: «أقل تدخّل مفيد».
        # ─────────────────────────────────────────────────────────────────────
        try:
            from app.services.skills.micro_simulation_skill import get_micro_simulation_skill
            from app.services.skills.pedagogical_escalation_skill import (
                EscalationInput,
                get_pedagogical_escalation_skill,
            )
            from app.services.skills.semantic_property_skill import (
                PROPERTY_REGISTRY,
                get_semantic_property_skill,
            )
            from app.services.skills.student_state_skill import (
                StudentStateInput,
                get_student_state_skill,
            )

            _concept_teach_intents = frozenset(
                {"definition", "example_request", "confusion", "procedure", "hint_request"}
            )
            _esc_state = get_student_state_skill().read(
                StudentStateInput(question=question, history=history_messages)
            )
            _esc_hist = " ".join(
                str(m.get("content", "")) for m in (history_messages or []) if isinstance(m, dict)
            )
            _esc_sps = get_semantic_property_skill()
            # D-139: حارس الحساب — «احسب/كم/اوجد/بيّن/استنتج» تبقى للمسار الحسابي (لا تُفعَّل المصفوفة).
            # D-143: + «نضرب/ضربنا/ضرب/حصلنا على» — أسئلة العدّ/الجداء يتولّاها المسار الحسابي الحتمي
            # (defense-in-depth خلف preempt _build_probability_computational_answer)، لا سُلّم الحادثة A.
            _esc_ql = (question or "").lower()
            _esc_compute = any(
                m in _esc_ql
                for m in (
                    "احسب",
                    "أحسب",
                    "كم ",
                    "اوجد",
                    "أوجد",
                    "بيّن",
                    "بين ان",
                    "استنتج",
                    "نضرب",
                    "ضربنا",
                    "ضرب ",
                    "حصلنا على",
                )
            )
            # D-139: متابعة المفهوم — «كيف/لماذا/وضح/اشرح/مثال/لم أفهم/؟» تُمسَك حتى لو صُنّفت unknown
            # (كانت «كيف نضيق الإمكانيات» / «كيف نحصل على معدومة» تسقط لـ D-135 → نص الحادثة A).
            _esc_followup = any(
                m in _esc_ql
                for m in (
                    "كيف",
                    "لماذا",
                    "علاش",
                    "وضح",
                    "اشرح",
                    "بسط",
                    "؟",
                    "مثال",
                    "لم افهم",
                    "لم أفهم",
                    "مفهمتش",
                )
            )
            _esc_teach_ok = _esc_state.primary_intent in _concept_teach_intents or (
                _esc_state.primary_intent == "unknown"
                and (_esc_followup or _esc_sps.interpret(question) is not None)
            )
            _esc_active = (
                _esc_sps.detect_active_concept(question, history_messages)
                if _esc_teach_ok
                and not _esc_compute
                and self._is_prob_context(question + " " + _esc_hist)
                else None
            )
            if _esc_active is not None:
                # support_level من BKT (D-104/D-126) عبر context — يُعايِر الرُّتبة.
                try:
                    _esc_sup = int((context or {}).get("support_level") or 0) or None
                except (TypeError, ValueError):
                    _esc_sup = None
                # آخر رسالة طالب (للـ Misconception Check).
                _esc_last = next(
                    (
                        str(m.get("content", ""))
                        for m in reversed(history_messages or [])
                        if isinstance(m, dict) and m.get("role") == "user"
                    ),
                    question,
                )
                _esc_mis = _esc_sps.diagnose_misconception(
                    _esc_active.concept_id, _esc_last, history_messages
                )
                _esc_spec = PROPERTY_REGISTRY.get(_esc_active.property_id)
                # D-159 (WP-B): ذاكرة FSM الدائمة لهذا المفهوم من tutor_state.kc_progress —
                # تَنجو من نافذة الـ50 رسالة وإعادة تشغيل العملية (مسح النصّ يبقى شبكة أمان).
                from app.services.skills.kc_progress_schema import (
                    escalation_levels_of,
                    parse_kc_entry,
                )

                _esc_kcp = tutor_state.get("kc_progress") if isinstance(tutor_state, dict) else None
                _esc_kcp = _esc_kcp if isinstance(_esc_kcp, dict) else {}
                _esc_levels = escalation_levels_of(_esc_kcp, _esc_active.concept_id)
                # D-159 (WP-D): تشخيص الجذر عبر حواف الـ graph — حين يكون جذر الصعوبة
                # شرطاً مسبقاً ضعيفاً (بحسب الحالة الدائمة)، يستهدف التدخّلُ الجذرَ لا
                # العرَض («أساس فجوة الوهم»). fail-open ⇒ التدخّل الأصلي دون تغيير.
                _esc_intervention = _esc_mis.intervention if _esc_mis else None
                _esc_root = None
                if _esc_mis is not None:
                    with contextlib.suppress(Exception):
                        from app.services.skills.semantic_property_skill import diagnose_root

                        _esc_root = diagnose_root(_esc_mis.bkt_concept, _esc_kcp)
                        if _esc_root is not None:
                            _esc_intervention = _esc_root.intervention_text
                _esc_decision = get_pedagogical_escalation_skill().decide(
                    EscalationInput(
                        concept_id=_esc_active.concept_id,
                        title=_esc_active.title,
                        definition=_esc_active.definition,
                        example=_esc_active.example,
                        micro_sim=get_micro_simulation_skill().get_micro_simulation(
                            _esc_active.concept_id
                        ),
                        # D-147: سؤال خطوة التطبيق على التمرين — يستبدل الـ punt العام عند نفاد السُّلّم.
                        apply_step=get_micro_simulation_skill().get_apply_step(
                            _esc_active.concept_id
                        ),
                        intent=_esc_state.primary_intent,
                        frustration=_esc_state.frustration,
                        support_level=_esc_sup,
                        history=history_messages or [],
                        # ISS-149: نصّ الطالب الحاضر صريحاً — ذيل `history` يعني
                        # الرسالة الحاضرة في الإنتاج والسابقة في مُشغِّل العقود.
                        question=question,
                        evidence_markers=(_esc_spec.evidence_markers if _esc_spec else ()),
                        misconception_intervention=_esc_intervention,
                        misconception_mtype=(_esc_mis.mtype if _esc_mis else None),
                        # D-159 (WP-B): الرُّتب المُسلَّمة من الحالة الدائمة (FSM حقيقي).
                        delivered_levels=_esc_levels,
                    )
                )
                # D-143 (RC-4): حارس التكرار — إن كان نصّ المصفوفة مُكرّراً لرسالة مساعد سابقة
                # (مثل «مررنا بالتعريف والمثال والمحاكاة…» عند استنفاد السُّلّم)، نُصعّد إلى الحلّ
                # الرمزي الحتمي بدل إعادته حرفياً (يكسر التكرار اللانهائي). يعمل حتى لو تجاوز
                # نافذة التاريخ عبر _recently_emitted.
                if _esc_decision.text and self._recently_emitted(
                    _esc_decision.text, history_messages
                ):
                    # ISS-148: دفتر ما سُلِّم (كان غائباً ⇒ إعادة تفريغ كاملة).
                    from app.services.skills.kc_progress_schema import delivered_steps

                    _esc_alt = self._build_probability_direct_explanation(
                        question, history_messages
                    ) or self._build_symbolic_reveal(
                        question,
                        history_messages,
                        acknowledge=True,
                        delivered=delivered_steps(tutor_state),
                    )
                    if _esc_alt and not self._recently_emitted(_esc_alt, history_messages):
                        _esc_decision = _esc_decision.model_copy(update={"text": _esc_alt})
                if _esc_decision.text:
                    from app.services.skills.tutor_metrics import (
                        record_intent,
                        record_intervention,
                        record_repetition_avoided,
                        record_response_mode,
                    )

                    record_intent(_esc_state.primary_intent)
                    record_response_mode(_esc_decision.action)
                    record_repetition_avoided()  # المصفوفة تمنع التكرار بالتصميم.
                    if _esc_decision.action == "target_misconception" and _esc_mis is not None:
                        record_intervention(_esc_mis.mtype)
                    _esc_chars = 0
                    async for chunk in self._stream_markdown_typing(_esc_decision.text):
                        if not chunk:
                            continue
                        _esc_chars += len(chunk)
                        yield self._normalize_stream_event(
                            {"type": "assistant_delta", "payload": {"content": chunk}}
                        )
                    if _esc_chars > 0:
                        logger.info(
                            "pedagogical_escalation",
                            extra={
                                "concept": _esc_active.concept_id,
                                "action": _esc_decision.action,
                                "level": _esc_decision.strategy_level,
                                "intent": _esc_state.primary_intent,
                                "support_level": _esc_sup,
                                "root_concept": (_esc_root.root_concept_id if _esc_root else ""),
                            },
                        )
                        # D-159 (WP-B): كتابة الرُّتبة المُسلَّمة في الحالة الدائمة عبر دلتا
                        # kc_progress (يحفظها customer_chat عبر record_turn) — نهاية «FSM»
                        # الذي يُعيد بناء نفسه من مسح النصّ. fail-open مطلق.
                        with contextlib.suppress(Exception):
                            _esc_entry = parse_kc_entry(_esc_kcp.get(_esc_active.concept_id))
                            _esc_entry.attempts += 1
                            if _esc_decision.action == "teach" and _esc_decision.strategy_level:
                                _esc_entry.mark_escalation(f"L{_esc_decision.strategy_level}")
                                if _esc_entry.state == "not_addressed":
                                    _esc_entry.state = "explained"
                            elif _esc_decision.action == "mastered":
                                _esc_entry.state = "understood"
                                _esc_entry.evidence = "verified"
                            if isinstance(tutor_state, dict):
                                _esc_delta = tutor_state.setdefault("kc_progress_delta", {})
                                if isinstance(_esc_delta, dict):
                                    _esc_delta[_esc_active.concept_id] = _esc_entry.to_dict()
                        yield self._normalize_stream_event(
                            {"type": "assistant_final", "payload": {"content": ""}}
                        )
                        ctx.turn_complete = True
                        return
        except Exception:
            logger.warning("pedagogical_escalation_failed", exc_info=True)

    async def _stage_definitional(self, ctx: TurnContext) -> AsyncGenerator[dict | str, None]:
        """الـ preempt التعريفي العام (D-132/D-133/D-137) — «ما هو X» للمفاهيم الجديدة."""
        question = ctx.question
        history_messages = ctx.history_messages
        # ─────────────────────────────────────────────────────────────────────
        # ISS-116 (D-132 — Generalized Concept Understanding / preempt تعريفي عام):
        # «جاهزية للأسئلة الجديدة دائماً». إن كان السؤال نية تعريفية («ماذا نقصد بـ X»)
        # أو حيرة عن مفهوم مُسمّى («لم افهم المتغير العشوائي») ضمن سياق احتمالات ⇒ نُعرّف X
        # عبر interpret_or_define (السجلّ الحتمي أولاً، ثم الـ LLM Listener-Definer للمفاهيم
        # الجديدة). يسبق الالتقاط السقراطي لأن «لم افهم المتغير العشوائي» سؤال تعريفي جديد لا
        # إجابة على السؤال السقراطي السابق. يحلّ الكارثة: كان يُعاد بسؤال عن الحادثة A.
        # لا default مُجمَّد لمفهوم واحد. ممنوع على طلبات الحساب. D-138: المفاهيم المُسجَّلة
        # يتولّاها بلوك المصفوفة التصعيدية أعلاه؛ هذا يبقى للمفاهيم الجديدة غير المُسجَّلة.
        # ─────────────────────────────────────────────────────────────────────
        try:
            from app.services.skills.semantic_property_skill import get_semantic_property_skill
            from app.services.skills.student_state_skill import (
                StudentStateInput,
                get_student_state_skill,
            )

            _sps = get_semantic_property_skill()
            # D-133: قراءة حالة الطالب (نيّة + إحباط) كإشارة قرار — حتمي.
            _state = get_student_state_skill().read(
                StudentStateInput(question=question, history=history_messages)
            )
            _hist_text = " ".join(
                str(m.get("content", "")) for m in (history_messages or []) if isinstance(m, dict)
            )
            _ql = (question or "").lower()
            # D-133: الحيرة = primary_intent (أو secondary) لا markers مبعثرة.
            _confused = (
                _state.primary_intent == "confusion" or "confusion" in _state.secondary_signals
            )
            _compute = any(
                m in _ql
                for m in ("احسب", "أحسب", "كم ", "اوجد", "أوجد", "بين ان", "بيّن أن", "استنتج")
            )
            # D-137: نيّة التعريف من StudentState تُفعّل مسار التعريف أيضاً — «ما هو X»
            # يصنّفها StudentState `definition`، فلا تسقط لـ D-135 (كارثة «14 من 165» للشرطي).
            _wants_def = (
                _sps.is_definitional(question)
                or _state.primary_intent == "definition"
                or (_confused and _sps.interpret(question) is not None)
            )
            if _wants_def and not _compute and self._is_prob_context(question + " " + _hist_text):
                _def = await _sps.interpret_or_define(question)
                if _def is not None:
                    from app.services.skills.tutor_metrics import (
                        record_definitional_answer,
                        record_intent,
                        record_response_mode,
                    )

                    record_definitional_answer(_def.concept_id, resolved=True, source=_def.source)
                    record_intent(_state.primary_intent)
                    _text = (
                        f"## {_def.title}\n\n{_def.definition}"
                        if _def.title and _def.title != "تعريف"
                        else _def.definition
                    )
                    # D-133 (وصفة المالك): الحيرة ⇒ تعريف + **مثال ملموس** + **سؤال موجِّه واحد**
                    # — لا تعريف-فقط. المعطيات من المحرك الرمزي (محايدة للمفهوم)، السؤال محروس.
                    _mode = "define"
                    if _confused:
                        _mode = "confusion_enriched"
                        with contextlib.suppress(Exception):
                            _combo = self._load_canonical_combinations(question, history_messages)
                            if _combo is not None:
                                _balls = self._balls_brief(_combo)
                                _gq = await self._generate_guiding_question(_def.concept_id, _balls)
                                _text += f"\n\nلنربطها بهذا التمرين: {_balls}.\n\n" + (
                                    _gq or "هل يمكنك تطبيق هذا على معطيات الكيس؟"
                                )
                    record_response_mode(_mode)
                    _def_chars = 0
                    async for chunk in self._stream_markdown_typing(_text):
                        if not chunk:
                            continue
                        _def_chars += len(chunk)
                        yield self._normalize_stream_event(
                            {"type": "assistant_delta", "payload": {"content": chunk}}
                        )
                    if _def_chars > 0:
                        logger.info(
                            "definitional_preempt",
                            extra={
                                "concept": _def.concept_id,
                                "source": _def.source,
                                "intent": _state.primary_intent,
                                "frustration": _state.frustration,
                                "response_mode": _mode,
                            },
                        )
                        yield self._normalize_stream_event(
                            {"type": "assistant_final", "payload": {"content": ""}}
                        )
                        ctx.turn_complete = True
                        return
        except Exception:
            logger.warning("definitional_preempt_failed", exc_info=True)

    async def _stage_concept_example(self, ctx: TurnContext) -> AsyncGenerator[dict | str, None]:
        """مثال واعٍ بالمفهوم النشط (D-136/D-137) — «اعطني مثال» بلا انحراف للحادثة A."""
        question = ctx.question
        history_messages = ctx.history_messages
        # ─────────────────────────────────────────────────────────────────────
        # ISS-116 (D-136 — مثال واعٍ بالمفهوم النشط): «اعطني مثال» ⇒ مثال **المفهوم
        # الذي يجري الحوار عنه** (product_even/expected_value…) لا مثال الحادثة A الأعمى
        # الافتراضي (كارثة transcript: 4 أسئلة مختلفة ⇒ نفس مثال A). يسبق D-135 (المكبوح)
        # والاسترجاع المُفهرَس. لا تكرار (المعروض already ⇒ زاوية LLM محروسة).
        # ─────────────────────────────────────────────────────────────────────
        try:
            from app.services.skills.semantic_property_skill import get_semantic_property_skill
            from app.services.skills.student_state_skill import (
                StudentStateInput,
                get_student_state_skill,
            )

            _ex_state = get_student_state_skill().read(
                StudentStateInput(question=question, history=history_messages)
            )
            _ex_hist = " ".join(
                str(m.get("content", "")) for m in (history_messages or []) if isinstance(m, dict)
            )
            # D-137: يَفعل على example_request **أو** الحيرة مع مفهوم نشط — «لم أفهم» بعد شرح
            # الاحتمال الشرطي يُعيد إشراك المفهوم النشط (الاحتمال الشرطي) لا الحادثة A الافتراضية.
            _ex_confused = (
                _ex_state.primary_intent == "confusion"
                or "confusion" in _ex_state.secondary_signals
            )
            _ex_active = get_semantic_property_skill().detect_active_concept(
                question, history_messages
            )
            _ex_fire = _ex_state.primary_intent == "example_request" or (
                _ex_confused and _ex_active is not None
            )
            if _ex_fire and self._is_prob_context(question + " " + _ex_hist):
                _ce = await self._build_concept_example(question, history_messages)
                if _ce:
                    from app.services.skills.tutor_metrics import (
                        record_intent,
                        record_response_mode,
                    )

                    record_intent(_ex_state.primary_intent)
                    record_response_mode("example_first")
                    _ce_chars = 0
                    async for chunk in self._stream_markdown_typing(_ce):
                        if not chunk:
                            continue
                        _ce_chars += len(chunk)
                        yield self._normalize_stream_event(
                            {"type": "assistant_delta", "payload": {"content": chunk}}
                        )
                    if _ce_chars > 0:
                        logger.info("concept_example_preempt", extra={"intent": "example_request"})
                        yield self._normalize_stream_event(
                            {"type": "assistant_final", "payload": {"content": ""}}
                        )
                        ctx.turn_complete = True
                        return
        except Exception:
            logger.warning("concept_example_preempt_failed", exc_info=True)

    async def _stage_socratic_evaluation(
        self, ctx: TurnContext
    ) -> AsyncGenerator[dict | str, None]:
        """الإصغاء النشط — مُقيّم الإجابات السقراطي (D-130/D-155)."""
        question = ctx.question
        history_messages = ctx.history_messages
        context = ctx.context
        obs = ctx.obs
        _root_ctx = ctx.root_ctx
        _t0 = ctx.t0
        # ─────────────────────────────────────────────────────────────────────
        # ISS-116 (D-130 — الإصغاء النشط / مُقيّم الإجابات السقراطي):
        # إذا كانت أحدث رسالة مساعد سؤالاً سقراطياً طرحناه، فرسالة الطالب الحالية
        # = **إجابة** على ذلك السؤال — تُقيَّم وتُكافأ، لا تُعاد طباعة التمرين.
        # يسبق الاسترجاع المُفهرَس (#3) لأن إجابة الطالب الحرة («نفس اللون فقط،
        # الحمراء والخضراء») تحوي كلمات اللون فتُطابق _has_indexed_match فتُعيد
        # طباعة التمرين كاملاً (الخيانة البيداغوجية). قفل الحالة عبر التاريخ
        # (لا حقل دائم). حارس تبديل الموضوع (D-101) داخل is_response_to_socratic.
        #
        # ISS-122 (D-155): سؤال مفاهيمي/استفهامي أثناء الحوار («لم افهم العلاقة
        # بين 14 و 165»، «لماذا حصلنا على 14 و 165») **ليس إجابةً تُقيَّم** — كان
        # يُبتلع هنا فيسقط في سُلّم بدائل أصمّ. يسقط الآن لكتلة D-124/D-125
        # (شرح العلاقة/الاشتقاق). «هل هي 14 من 165» تبقى إجابة (تطلب تأكيداً).
        # ─────────────────────────────────────────────────────────────────────
        if (
            self._in_socratic_dialogue(question, history_messages)
            and not self._detect_conceptual_question(question)
            and not (question or "").strip().startswith(self._QUESTION_OPENERS_NOT_ANSWERS)
        ):
            se_streamed_chars = 0
            _tutor_state = (context or {}).get("tutor_state") if isinstance(context, dict) else None
            try:
                async for chunk in self._stream_socratic_evaluation(
                    question,
                    history_messages,
                    tutor_state=_tutor_state if isinstance(_tutor_state, dict) else None,
                ):
                    if not chunk:
                        continue
                    se_streamed_chars += len(chunk)
                    yield self._normalize_stream_event(
                        {"type": "assistant_delta", "payload": {"content": chunk}}
                    )
            except Exception:
                logger.warning("socratic_evaluation_preempt_failed", exc_info=True)

            if se_streamed_chars > 0:
                if _root_ctx:
                    with contextlib.suppress(Exception):
                        obs.end_span(
                            _root_ctx.span_id,
                            status="OK",
                            metrics={
                                "duration_ms": (time.perf_counter() - _t0) * 1000,
                                "fallback_path": 0.45,  # بين question-only والاسترجاع المُفهرَس
                                "stream_chars": float(se_streamed_chars),
                            },
                        )
                yield self._normalize_stream_event(
                    {"type": "assistant_final", "payload": {"content": ""}}
                )
                ctx.turn_complete = True
                return
            # إذا فشل البث (نادر) → نُكمل المسار العادي (لا إعادة طباعة بسبب fail-open)

    async def _stage_indexed_retrieval(self, ctx: TurnContext) -> AsyncGenerator[dict | str, None]:
        """الاسترجاع المُفهرَس (D-049/D-101) — طلب تمرين صريح يهزم الواجهة المحسوبة."""
        question = ctx.question
        history_messages = ctx.history_messages
        obs = ctx.obs
        _root_ctx = ctx.root_ctx
        _t0 = ctx.t0
        # ─────────────────────────────────────────────────────────────────────
        # ISS-056 (D-049 — Indexed Retrieval Preemption):
        # إذا طابق السؤال تمريناً محدداً في knowledge_index، نتجاوز كل
        # شيء (orchestrator + StateGraph + fallback chain) ونبث المحتوى
        # المُفهرَس النظيف مباشرة. هذا يحل كارثة JSON envelope leak عند المصدر.
        # ISS-CONV-C: نمرر history_messages لحل أسئلة المتابعة بالسياق.
        #
        # ISS-110 (D-101): هذه الكتلة تسبق الآن _build_calculated_ui — طلب
        # تمرين صريح («اعطني تمرين الدوال العددية») يهزم دائماً الواجهة
        # المحسوبة. قبل هذا الترتيب، MODE_A كان يُنهي المسار بمكوّن احتمالات
        # مبني من history التمرين السابق قبل وصول الاسترجاع المُفهرَس (كارثة حية).
        # ─────────────────────────────────────────────────────────────────────
        if self._has_indexed_match(
            question, history_messages
        ) and not self._is_short_answer_in_dialogue(question, history_messages):
            logger.info(
                "indexed_retrieval_preempt",
                extra={
                    "request_id": str(uuid.uuid4()),
                    "question_len": len(question),
                    "reason": "matched_knowledge_index_entry",
                },
            )
            ret_streamed_chars = 0
            try:
                async for chunk in self._stream_local_retrieval_response(
                    question, history_messages
                ):
                    if not chunk:
                        continue
                    ret_streamed_chars += len(chunk)
                    yield self._normalize_stream_event(
                        {"type": "assistant_delta", "payload": {"content": chunk}}
                    )
            except Exception:
                logger.warning("indexed_retrieval_preempt_failed", exc_info=True)

            if ret_streamed_chars > 0:
                if _root_ctx:
                    with contextlib.suppress(Exception):
                        obs.end_span(
                            _root_ctx.span_id,
                            status="OK",
                            metrics={
                                "duration_ms": (time.perf_counter() - _t0) * 1000,
                                "fallback_path": 0.5,  # preempt = أعلى من file_intelligence
                                "stream_chars": float(ret_streamed_chars),
                            },
                        )
                yield self._normalize_stream_event(
                    {"type": "assistant_final", "payload": {"content": ""}}
                )
                ctx.turn_complete = True
                return
            # إذا فشل البث (نادر جداً) → نُكمل المسار العادي
