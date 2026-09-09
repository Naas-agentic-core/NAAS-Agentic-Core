"""Probability generative-UI mixin (D-164 Slice 3 — extracted verbatim from the God-file).

Single responsibility: build the deterministic probability Generative-UI payloads the tutor
streams to the browser — concrete-label extraction (Abstraction Ban), probability-tree
detection, the calculated tree/combinations/full-exercise UI router (`_build_calculated_ui`),
and the async tree-props builder with guarded LLM label enrichment.

Mixed into `OrchestratorClient`; every `self._x`/`cls._x` resolves through the MRO —
behaviour is byte-identical to the pre-extraction God-file.
"""

from __future__ import annotations

import contextlib
import logging
import re

logger = logging.getLogger("orchestrator-client")


class ProbabilityUIMixin:
    """Deterministic probability Generative-UI builders (D-164)."""

    # Abstraction Ban (Cognitive Refactoring — V6.0):
    # تسميات عُقَد شجرة الاحتمالات يجب أن تكون ملموسة ومستخرَجة من سياق المسألة
    # ("كرة حمراء"، "سحب ناجح"، "قطعة معيبة") — لا رموز مجرّدة (A, B|A, Ā). نمط
    # هجين: استخراج حتمي أولاً، ثم LLM فقط عند عدم وجود كيان ملموس. حتى الـ
    # fallback النهائي ملموس ("الحدث الأول") — لا حرف A أبداً.
    # ─────────────────────────────────────────────────────────────────────────

    # كيانات ملموسة شائعة في مسائل بكالوريا الاحتمالات (لون + اسم، نتائج ثنائية).
    _CONCRETE_EVENT_PATTERNS: tuple[tuple[tuple[str, ...], str, str], ...] = (
        (("كرة حمراء", "كرات حمراء", "أحمر", "حمراء"), "كرة حمراء", "كرة غير حمراء"),
        (("كرة بيضاء", "كرات بيضاء", "أبيض", "بيضاء"), "كرة بيضاء", "كرة غير بيضاء"),
        (("كرة سوداء", "كرات سوداء", "أسود", "سوداء"), "كرة سوداء", "كرة غير سوداء"),
        (("كرة خضراء", "أخضر", "خضراء"), "كرة خضراء", "كرة غير خضراء"),
        (("معيب", "معيبة", "تالف", "تالفة", "défectueu"), "قطعة معيبة", "قطعة سليمة"),
        (("ناجح", "نجاح", "ينجح", "réussi", "succès"), "سحب ناجح", "سحب فاشل"),
        (("مدخن", "تدخين", "fumeur"), "مدخن", "غير مدخن"),
        (("مصاب", "مرض", "إصابة", "malade"), "مصاب", "سليم"),
        (("ذكر", "إناث", "أنثى", "ذكور"), "ذكر", "أنثى"),
        (("معطوب", "عطل", "panne"), "جهاز معطوب", "جهاز سليم"),
    )

    @classmethod
    def _extract_concrete_events(cls, normalized: str) -> dict[str, str] | None:
        """يستخرج تسميتين ملموستين من نص المسألة، أو None إن لم يجد كياناً."""
        first: tuple[str, str] | None = None
        second: tuple[str, str] | None = None
        for keywords, label, label_neg in cls._CONCRETE_EVENT_PATTERNS:
            if any(kw in normalized for kw in keywords):
                if first is None:
                    first = (label, label_neg)
                elif (label, label_neg) != first:
                    second = (label, label_neg)
                    break
        if first is None:
            return None
        if second is None:
            # حدث ثانٍ ملموس عام مرتبط بالسحب (مستوى شرطي)
            second = ("سحب ناجح", "سحب فاشل")
        return {
            "first": first[0],
            "first_neg": first[1],
            "second": second[0],
            "second_neg": second[1],
        }

    @classmethod
    def _detect_probability_tree(cls, question: str) -> dict[str, object] | None:
        """يكتشف طلبات شجرة الاحتمالات ويبني خصائص تصيير حتمية بتسميات ملموسة.

        يُفعَّل عند: (1) عبارة صريحة (شجرة احتمالات / probability tree / arbre de
        probabilité) أو (2) ذِكر "احتمال" مع وجود قيمة احتمالية رقمية. يستخرج حتى
        قيمتين احتماليتين لبناء شجرة ثنائية المستوى، وتسميات ملموسة من سياق
        المسألة (Abstraction Ban). يضع علم ``labels_generic`` ليُفعَّل إثراء الـ
        LLM لاحقاً عند الحاجة.
        """

        if not question or not isinstance(question, str):
            return None
        normalized = question.strip().lower()

        explicit_triggers = (
            "شجرة الاحتمال",
            "شجرة احتمال",
            "شجرة الاحتمالات",
            "مخطط الشجرة",
            "شجرة القرار",
            "probability tree",
            "tree diagram",
            "arbre de probabilit",
            "arbre pondéré",
            "diagramme en arbre",
        )
        has_explicit = any(trigger in normalized for trigger in explicit_triggers)
        has_probability_word = any(
            word in normalized for word in ("احتمال", "احتمالات", "probabilit", "proba")
        )

        # استخراج القيم الاحتمالية: كسور عشرية (0.3) أو نسب مئوية (30%)
        decimals = [float(m) for m in re.findall(r"\b0?\.\d+\b", normalized)]
        percents = [float(m) / 100.0 for m in re.findall(r"\b(\d{1,3})\s*%", normalized)]
        probs = [p for p in (decimals + percents) if 0.0 < p < 1.0][:2]

        if not has_explicit and not (has_probability_word and probs):
            return None

        def _complement(value: float) -> float:
            return round(1.0 - value, 4)

        p_first = probs[0] if probs else 0.5
        p_cond = probs[1] if len(probs) > 1 else 0.5

        events = cls._extract_concrete_events(normalized)
        labels_generic = events is None
        if events is None:
            # fallback ملموس عام — لا رموز مجرّدة أبداً (Abstraction Ban)
            events = {
                "first": "الحدث الأول",
                "first_neg": "عكس الحدث الأول",
                "second": "الحدث الثاني",
                "second_neg": "عكس الحدث الثاني",
            }

        tree = cls._build_tree_structure(events, p_first, p_cond, _complement)
        return {
            "title": "شجرة الاحتمالات",
            "is_illustrative": not probs,
            "labels_generic": labels_generic,
            "tree": tree,
        }

    @staticmethod
    def _build_tree_structure(
        events: dict[str, str],
        p_first: float,
        p_cond: float,
        complement: object,
    ) -> dict[str, object]:
        """يبني شجرة ثنائية المستوى بتسميات ملموسة. موضع العقدة يُمثّل الشرط."""
        _comp = complement  # callable
        return {
            "label": "البداية",
            "children": [
                {
                    "label": events["first"],
                    "p": round(p_first, 4),
                    "children": [
                        {"label": events["second"], "p": round(p_cond, 4)},
                        {"label": events["second_neg"], "p": _comp(p_cond)},  # type: ignore[operator]
                    ],
                },
                {
                    "label": events["first_neg"],
                    "p": _comp(p_first),  # type: ignore[operator]
                    "children": [
                        {"label": events["second"], "p": 0.5},
                        {"label": events["second_neg"], "p": 0.5},
                    ],
                },
            ],
        }

    @staticmethod
    def _build_calculated_tree_props(
        question: str,
        history_messages: list[dict[str, str]] | None = None,
    ) -> dict[str, object] | None:
        """يحسب شجرة احتمالات بكسور حقيقية عبر ProbabilityCalculatorSkill (D-075).

        Protocol V14.0 §3: الخلفية تحسب P(الحدث) = العدد/المجموع ديناميكياً من
        التركيبة العربية (مثل 4/11) بدلاً من إغراق الواجهة بقيمة 0.5 وهمية. كل
        عقدة تحمل (p_num/p_den) فتُصيّر الواجهة الكسر الدقيق. محروس بـ try/except —
        أي فشل يُرجع None ويسقط للمسار الحتمي القديم (`_detect_probability_tree`).
        """
        try:
            from app.services.skills.probability_skill import (
                ProbabilityCalculatorSkill,
                ProbabilityInput,
                ProbabilityModelOutput,
            )

            skill = ProbabilityCalculatorSkill()
            result = skill.analyze(ProbabilityInput(question=question, history=history_messages))
            if not isinstance(result, ProbabilityModelOutput):
                return None
            return {
                "title": result.title,
                "is_illustrative": False,  # قيم محسوبة حقيقية — ليست توضيحية
                "calculated": True,
                "with_replacement": result.with_replacement,
                "total": result.total,
                "composition": [
                    {
                        "label": item.label,
                        "count": item.count,
                        "p_num": item.p_num,
                        "p_den": item.p_den,
                        "p_decimal": item.p_decimal,
                    }
                    for item in result.composition
                ],
                "tree": result.tree,
            }
        except Exception:
            logger.warning("_build_calculated_tree_props_failed", exc_info=True)
            return None

    @staticmethod
    def _build_calculated_ui(
        question: str,
        history_messages: list[dict[str, str]] | None = None,
    ) -> dict[str, object] | None:
        """D-078 (V19.0 → V38.0): الموجِّه التربوي — يُرجِع حدث ui_component الصحيح.

        «دفعة واحدة» (سحب آني) → ``combinations_visualizer`` (تأليفي C_n^k)؛
        «على التوالي» / سحب مفرد → ``probability_tree``. هذا يمنع فرض شجرة
        تتابعية على مسألة آنية (كارثة تربوية). كاشف الإحباط (مفهمتش/كيفاش)
        يُفعِّل الأداة البصرياً عبر سياق المحادثة. محروس بـ try/except.

        المخرج: ``{"component": str, "props": dict, "fallback_text": str,
        "terminate_pipeline": bool, "routing_mode": str}`` أو None.

        ## V38.0 — نظام التوجيه الثنائي (Dual-Mode Routing)

        ### MODE_A — الوضع المباشر (Standard Direct Mode)
        يُستخدم عند السؤال المباشر أو طلب الحل العادي.
        - ``terminate_pipeline=True`` يُوقف المسار بعد المكوّن البصري.
        - ``companion_text`` (جملة واحدة) هو النص الوحيد المرافق.

        ### MODE_B — وضع البيداغوجيا العميقة (Deep Pedagogy Mode)
        يُفعَّل عند إشارات الحيرة («لم أفهم»، «اشرح لي»، «كيفاش»).
        - ``terminate_pipeline=False`` — المسار يبقى حياً.
        - المكوّن البصري يُبثّ أولاً، ثم يستمر السرد البيداغوجي من LLM.
        - القناتان (JSON + Markdown) منفصلتان تماماً — لا تلوّث متبادل.

        ## V28.0 — قانون الكبح النصي (Text-Wall Muzzle) — ساري في MODE_A فقط
        ``terminate_pipeline=True`` يُلزم ``chat_with_agent`` بإنهاء المسار
        فوراً بعد بثّ المكوّن البصري و``companion_text`` — لا LLM، لا synthesizer.
        """
        try:
            from app.services.capabilities.topic_authority import is_foreign_to_probability
            from app.services.skills.probability_skill import (
                CombinationsModelOutput,
                FullExerciseStoryOutput,
                ImpossibleCaseOutput,
                ProbabilityCalculatorSkill,
                ProbabilityInput,
                ProbabilityModelOutput,
            )

            # ISS-110 (D-101): حاجب تبديل الموضوع — إذا كان السؤال الحالي يذكر
            # صراحةً موضوعاً غير الاحتمالات فلا تُبنى أيّ واجهة احتمالات من سياق
            # الـ history حتى مع وجود حيرة.
            #
            # D-266 (ISS-159): كان الشرط `_c is not None and _c.canonical_id !=
            # "probability"` — فسؤال الفيزياء يُرجِع `None` من سجلّ الاسترجاع (يعرف
            # ثلاثة مواضيع رياضية لا غير)، فيسقط الشرط عند ساقه الأولى **ولا يعمل
            # الحارس**. الحاسم الآن واحد ويقرأ المنهاج كلّه.
            if is_foreign_to_probability(question):
                return None

            skill = ProbabilityCalculatorSkill()
            # ISS-131 (D-169 — قاعدة D-102): رسائل system لا تدخل كاشف السياق —
            # برومبت الإدمن يحوي «كرة/احتمال» فكان يجعل كل سؤال إدمن «سياق احتمالات»
            # ويُفعِّل خطوة تركيز زائفة. الحوار = رسائل الطالب/المساعد حصراً.
            _dialogue_history = [
                m
                for m in (history_messages or [])
                if isinstance(m, dict) and m.get("role") in ("user", "assistant")
            ]
            _combined_text = (
                question + " " + " ".join(str(m.get("content", "")) for m in _dialogue_history)
            )

            # D-122/D-123: حارس سياق الاحتمالات (مُعرَّف مبكراً — للتحصين والتركيز).
            # D-266 (ISS-159): نفس نقض المادة الموجبة قبل قراءة أيّ مفردة — «كرة»
            # تعني الكرة الفيزيائية أيضاً. النسخة الثانية من هذه المفاتيح تعيش في
            # `CognitiveVerificationMixin._is_prob_context`؛ كلتاهما تسأل الحاسم
            # الواحد أوّلاً، فلا تتفرّقان في القرار مهما تفرّقتا في المفاتيح.
            def _is_probability_context(text: str) -> bool:
                t = text or ""
                with contextlib.suppress(Exception):
                    from app.services.capabilities.topic_authority import (
                        is_foreign_to_probability,
                    )

                    if is_foreign_to_probability(t):
                        return False
                return any(
                    marker in t
                    for marker in ("كرات", "كرة", "كيس", "احتمال", "سحب", "نسحب", "p(a", "p(b")
                )

            # ─────────────────────────────────────────────────────────────────
            # D-123 — تحصين بالمحتوى الرسمي (history-immune):
            # الكارثة الحيّة: نص LLM مُهلوَس في الـ history («2 برتقالية + 3 زرقاء»)
            # كان يُسمّم استخراج التركيبة ⇒ كاروسيل خاطئ («سحب 2 من 11»/«كرة زرقاء»).
            # الحل: (1) جرّب السؤال وحده (تركيبة inline مثل «كيس فيه 4 حمراء و7 بيضاء»).
            # (2) إن لم توجد + سياق احتمالات (محادثة التمرين المُفهرَس) ⇒ ابنِ من
            # **المحتوى الرسمي للتمرين** + نية السؤال، بـ history=None ⇒ مناعة كاملة
            # من تلوّث الـ history. (3) آخر ملاذ: الاستخراج بالـ history (السلوك الأصلي).
            # هذا يضمن الكاروسيل الصحيح (2بيضاء/4حمراء/5خضراء) ⇒ terminate=True ⇒ صفر LLM.
            # ─────────────────────────────────────────────────────────────────
            def _result_ok(r: object) -> bool:
                return r is not None and getattr(r, "success", True) is not False

            # (1) السؤال وحده — يلتقط التركيبة الـ inline بلا تلوّث history.
            result = skill.analyze(ProbabilityInput(question=question, history=None))

            # (2) D-191 (ISS-140 د): التمرين قيد النقاش من مُحلٍّ واحد — **تمرين
            # الطالب في تاريخ المحادثة قبل التمرين المرجعي**. كان هنا حقنٌ مباشر
            # للمحتوى الرسمي (`f"{_official} {question}"`) يجعل أرقام التمرين
            # المخزَّن تفوز بالاستخراج، فيرى الطالب كيساً ليس كيسَه.
            if not _result_ok(result) and _is_probability_context(_combined_text):
                with contextlib.suppress(Exception):
                    from app.services.skills.exercise_context import resolve_exercise_context

                    _resolved = resolve_exercise_context(question, history_messages)
                    if _resolved is not None:
                        # **التركيبة** من التمرين المحسوم، و**النيّة** من سؤال الطالب
                        # الحاضر: الحيرة تُنتج قصّةً بصرية شاملة، والسؤال المباشر
                        # يُنتج مُصوِّر تأليفات. history=None ⇒ مناعة D-123 محفوظة.
                        _ctx_result = skill.analyze(
                            ProbabilityInput(
                                question=f"{_resolved.composition_text} {question}".strip(),
                                history=None,
                            )
                        )
                        result = _ctx_result if _result_ok(_ctx_result) else _resolved.combo

            # (3) آخر ملاذ — السلوك الأصلي (history). نادر بعد التحصين.
            if not _result_ok(result):
                result = skill.analyze(
                    ProbabilityInput(question=question, history=history_messages)
                )

            # V38.0 — Dual-Mode Routing: كشف نية الطالب قبل بناء الحمولة.
            # MODE_B يُفعَّل عند إشارات الحيرة — يُبقي المسار حياً للسرد البيداغوجي.
            # MODE_A هو الوضع الافتراضي — يُوقف المسار بعد المكوّن البصري.
            # ISS-114 (D-106): طلب توليد واجهة صريح («قم بتوليد واجهة تشرح
            # الحادثة») يُفعِّل MODE_B (مكوّن بصري + سرد بيداغوجي) — لا يصل
            # الطلب أبداً لـ LLM يكتب HTML خاماً.
            _is_deep_pedagogy = (
                ProbabilityCalculatorSkill.is_confusion(question)
                or ProbabilityCalculatorSkill.is_confusion(_combined_text)
                or ProbabilityCalculatorSkill.is_visual_request(question)
            )
            _routing_mode = "MODE_B" if _is_deep_pedagogy else "MODE_A"

            def _detect_focus_step(user_question: str) -> str | None:
                """يحدِّد خطوة الشرح المطلوبة صراحةً لتخصيص الواجهة والنص المرافق."""
                q = user_question.lower()
                if "p(a" in q or "نفس اللون" in q or "same color" in q:
                    return "same_color_event"
                # D-184: الاحتمال الشرطي صار خطوةً قائمةً بذاتها (كان يُطوى في
                # `same_color_event` فيُسأل الطالب عن الألوان بدل تغيّر الفضاء).
                if "شرطي" in q or "p_a" in q or "p a" in q:
                    return "conditional_event"
                # المتغيّر العشوائي **قبل** تكافؤ الجداء: تعريف X نفسه يحوي «زوجي»
                # («يمثل عدد الكرات التي تحمل رقماً زوجياً») فلا يُختطَف لخطوة B/C.
                if (
                    "x>1" in q
                    or "e(x" in q
                    or "الأمل" in q
                    or "المتغير" in q
                    # صياغة تعريف X نفسها («عدد الكرات التي تحمل رقماً زوجياً»).
                    # مميِّزة عن الحادثة C («جداء أرقامها عدد زوجي») بـ«عدد الكرات».
                    or ("عدد الكرات" in q and "زوجي" in q)
                ):
                    return "random_variable"
                if "جداء" in q and ("معدوم" in q or "صفر" in q):
                    return "sequential_zero_product"
                # D-182: حيرة حول *طريقة* السحب المتتالي (الجزء II: «على التوالي وبدون
                # إرجاع») — «لماذا نضرب تنازلياً»، «على التوالي»، «بدون إرجاع»، «الترتيب» —
                # يجب أن تستهدف خطوة السحب المتتالي لا خطوة الحدث الافتتاحية. قبل هذا،
                # لأنّ الكاشف لم يملك نمطاً للتنازل/التوالي كانت الحيرة تسقط للافتراضي
                # same_color_event فينحرف المعلّم إلى سؤال الألوان بدل سؤال الطالب الفعلي.
                if (
                    "تنازلي" in q
                    or "على التوالي" in q
                    or "بالتوالي" in q
                    or "بدون إرجاع" in q
                    or "بدون ارجاع" in q
                    or "دون إرجاع" in q
                    or "دون ارجاع" in q
                    or "ترتيب" in q
                ):
                    return "sequential_zero_product"
                # D-184: الحادثتان B وC (تكافؤ **جداء الأرقام**) لهما خطوتهما الآن.
                # كانتا تُوجَّهان إلى `same_color_event` فيُسأل الطالب عن الألوان
                # بينما سؤاله عن أرقام الكرات — انحراف موضوعي كامل. تأتي **بعد**
                # إشارات الطريقة (D-182) كي لا تُختطَف حيرة السحب المتتالي.
                if "p(b" in q or "p(c" in q or "فردي" in q or "زوجي" in q:
                    return "product_parity_event"
                # صياغة الطالب الطبيعية لجداء أرقام الكرات: «لماذا نضرب ثلاثة أرقام
                # في بعضها». إشارات الطريقة (D-182: تنازلي/على التوالي/الترتيب) تُفحص
                # **قبلها** فتفوز — فسؤال «نضرب تنازلياً» يبقى على السحب المتتالي كما
                # قرّر D-182، بينما «نضرب الأرقام» بلا إشارة طريقة يستهدف الحادثتين B وC.
                if ("جداء" in q or "نضرب" in q or "ضرب" in q or "حاصل" in q) and (
                    "أرقام" in q or "ارقام" in q or "رقم" in q
                ):
                    return "product_parity_event"
                if "فضاء" in q or "c(" in q or "تأليف" in q:
                    return "sample_space"
                return None

            # D-122: إشارات طبيعية لأجزاء التمرين («السؤال الأول» = P(A) = الحدث A)
            # — لا تحوي رمز P(A) لكنها تستهدف خطوة. تُطبَّق فقط ضمن سياق احتمالات
            # مؤكَّد (حارس أدناه) تجنّباً لتحميل احتمالات في محادثة موضوع آخر.
            def _detect_part_reference(user_question: str) -> str | None:
                q = user_question.lower()
                # السؤال 2 / المتغير العشوائي X (يُفحَص أولاً: «الثاني» أكثر تحديداً)
                if (
                    "السؤال الثاني" in q
                    or "السؤال 2" in q
                    or "السوال الثاني" in q
                    or "الجزء الثاني" in q
                ):
                    return "random_variable"
                # السؤال 1 / الحدث A (الافتراض الرئيسي لتمرين الاحتمالات)
                if (
                    "السؤال الاول" in q
                    or "السؤال الأول" in q
                    or "السؤال 1" in q
                    or "السوال الاول" in q
                    or "الجزء الاول" in q
                    or "الجزء الأول" in q
                    or "الجزء 1" in q
                    or "الحدث a" in q
                    or "الحادثة a" in q
                    or "حل السؤال" in q
                    or "حل السوال" in q
                ):
                    return "same_color_event"
                return None

            def _recover_recent_focus() -> str | None:
                """D-184: يسترجع بؤرة الحوار الجارية من الأدوار السابقة.

                «لم أفهم» تعني «لم أفهم ما شرحتَه للتوّ» — لا «ابدأ التمرين من
                أوّله». قبل D-184 كان غياب إشارة صريحة في السؤال الحالي يُصفّر
                البؤرة إلى الحدث الافتتاحي، فينحرف المعلّم إلى سؤال الألوان مهما
                كان الطالب يسأل عنه (كارثة الترانسكريبت الحي: «لم أفهم» بعد سؤال
                عن جداء الأرقام ⇒ «أيّ الألوان تعطينا 3 كرات من نفس اللون؟»).

                نمسح رسائل **الطالب وحده** من الأحدث للأقدم. استثناء رسائل المساعد
                مقصود ومُثبَت حياً: ردّ المساعد الأول يحوي نصّ التمرين كاملاً — وفيه
                «نفس اللون» و«فردي» و«زوجي» و«جداء» معاً — فلو قرأناه لعاد الكاشف
                دائماً بأول فرع (`same_color_event`) مهما سأل الطالب، أي إعادة إنتاج
                الكارثة نفسها من باب آخر. البؤرة نيّة **الطالب**، لا نثر المساعد
                (نفس منطق ISS-120: لا استخراج من النثر المُولَّد).
                """
                for _msg in reversed(_dialogue_history):
                    if _msg.get("role") != "user":
                        continue
                    _content = str(_msg.get("content", ""))
                    if not _content:
                        continue
                    _recovered = _detect_focus_step(_content) or _detect_part_reference(_content)
                    if _recovered:
                        return _recovered
                return None

            # D-122: حارس سياق الاحتمالات مُعرَّف مبكراً أعلاه (D-123) — يُعاد استخدامه هنا.
            _focus_step_id = _detect_focus_step(question)
            # D-122: لو لم يُطابق رمز صريح، جرّب الإشارة الطبيعية لجزء التمرين —
            # فقط ضمن سياق احتمالات (history) كي لا تُحمَّل احتمالات في موضوع آخر.
            # D-184: ثم البؤرة اللاصقة من الحوار — **قبل** السقوط الافتراضي.
            if _focus_step_id is None and _is_probability_context(_combined_text):
                _focus_step_id = _detect_part_reference(question)
                if _focus_step_id is None:
                    _focus_step_id = _recover_recent_focus()
                if _focus_step_id is None and _is_deep_pedagogy:
                    _focus_step_id = "same_color_event"

            # ISS-110: نقبل أيضاً `no_probability_intent_in_question` — سؤال متابعة
            # بخطوة تركيز صريحة (_focus_step_id) يُعاد تحليله بالسياق الكامل.
            _is_no_model = getattr(result, "success", True) is False and getattr(
                result, "reason", ""
            ) in ("no_model_extracted", "no_probability_intent_in_question")
            if (result is None or _is_no_model) and _focus_step_id and _dialogue_history:
                # ISS-131: الاستخراج من حوار الطالب/المساعد حصراً (لا نثر system).
                _history_context = " ".join(str(m.get("content", "")) for m in _dialogue_history)
                _contextual_question = f"{_history_context} {question}".strip()
                result = skill.analyze(
                    ProbabilityInput(question=_contextual_question, history=history_messages)
                )

            # ISS-110: نقبل أيضاً `no_probability_intent_in_question` — سؤال متابعة
            # بخطوة تركيز صريحة (_focus_step_id) يُعاد تحليله بالسياق الكامل.
            _is_no_model = getattr(result, "success", True) is False and getattr(
                result, "reason", ""
            ) in ("no_model_extracted", "no_probability_intent_in_question")
            if (result is None or _is_no_model) and _focus_step_id:
                with contextlib.suppress(Exception):
                    # D-191 (ISS-140 د): إعادة تحليل خطوة التركيز تمرّ بالمُحلّ
                    # الواحد أيضاً. الحقن المباشر للنصّ الرسمي هنا كان يُعيد إدخال
                    # أرقام التمرين المخزَّن حتى بعد أن نجح مسار الطالب أعلاه.
                    from app.services.skills.exercise_context import resolve_exercise_context

                    _resolved = resolve_exercise_context(question, history_messages)
                    if _resolved is not None:
                        _contextual_question = f"{_resolved.composition_text} {question}".strip()
                        result = skill.analyze(
                            ProbabilityInput(
                                question=_contextual_question, history=history_messages
                            )
                        )

            # D-117 (Fix 4 — best-effort): حيرة عامة («لم أفهم» بلا خطوة تركيز
            # محددة) بعد تمرين احتمالات → أعِد استخراج تركيبة الكيس من الـ history
            # فيُعاد بثّ البصري الحتمي بدل السقوط للـ LLM (مصدر الغارباج). إن تعذّر
            # الاستخراج يبقى result فاشلاً → return None → الإصلاحات 1-3 تضمن نظافة
            # مخرَج الـ LLM. (المفهوم=probability مضمون بحاجب تبديل الموضوع أعلاه.)
            _is_no_model = getattr(result, "success", True) is False and getattr(
                result, "reason", ""
            ) in ("no_model_extracted", "no_probability_intent_in_question")
            if (result is None or _is_no_model) and _is_deep_pedagogy and _dialogue_history:
                # ISS-131: الاستخراج من حوار الطالب/المساعد حصراً (لا نثر system).
                _history_context = " ".join(
                    str(m.get("content", "")) for m in _dialogue_history
                ).strip()
                if _history_context:
                    result = skill.analyze(
                        ProbabilityInput(question=_history_context, history=history_messages)
                    )

            def _companion_text_for_focus(default_text: str) -> str:
                """يبني نصاً مرافقاً موجهاً حسب طلب الطالب بدل تكرار عبارة عامة."""
                if _focus_step_id == "same_color_event":
                    # D-206 (L8): كان «سنشرح الآن خطوة الحدث المطلوب…» — إعلانُ أجندة.
                    # وفي الإنتاج (customer_messages 4598→4599) تلاه صفٌّ **فارغ**:
                    # الطالب سمع «سنشرح الآن» ولم يصله شرح. الوسيط أعلن عن نفسه ثمّ
                    # أخلف. البديل يُسمّي **موضوع الطالب** ولا يَعِد بشيء.
                    return "الحادثة A: ثلاث كرات من نفس اللون."
                if _focus_step_id == "random_variable":
                    return "سنركّز الآن على المتغير X وقانونه خطوة بخطوة داخل الواجهة."
                if _focus_step_id == "sample_space":
                    return "سنبدأ من فضاء العينة C(n,k) ثم نبني باقي النتائج عليه بصرياً."
                if _focus_step_id == "sequential_zero_product":
                    return (
                        "سنركّز على السحب المتتالي بدون إرجاع: لماذا يتغيّر عدد "
                        "الاختيارات المتاحة في كل سحبة."
                    )
                # D-184: بؤرتان جديدتان — نصّهما يتكلّم عن سؤال الطالب فعلاً
                # (أرقام الكرات / تغيّر الفضاء) لا عن الألوان.
                if _focus_step_id == "product_parity_event":
                    return (
                        "سنركّز على جداء أرقام الكرات: متى يكون فردياً ومتى يصير "
                        "زوجياً — لا على ألوانها."
                    )
                if _focus_step_id == "conditional_event":
                    return (
                        "سنركّز على الاحتمال الشرطي: كيف تُغيّر المعلومة المؤكَّدة "
                        "فضاء الحالات الممكنة قبل أي حساب."
                    )
                return default_text

            # V44.0 — AEK: استدعاء النواة التعليمية التكيّفية لإثراء الحمولة
            # بالحالة المعرفية والنية التربوية. غير حرج — أي فشل يُسجَّل ويُتجاوَز.
            _aek_state: dict[str, object] = {}
            try:
                from app.services.aek.kernel import AdaptiveEducationalKernel

                _aek_output = AdaptiveEducationalKernel().process(
                    question=question,
                    history=list(history_messages or []),
                )
                _aek_state = {
                    "cognitive_state": _aek_output.channel_a.cognitive_state,
                    "cognitive_intent": _aek_output.channel_a.cognitive_intent,
                    "abstraction_level": _aek_output.channel_a.abstraction_level,
                    "cognitive_load_index": _aek_output.channel_a.cognitive_load_index,
                    "narrative": _aek_output.channel_b.narrative,
                    "pacing_hint": _aek_output.channel_b.pacing_hint,
                }
            except Exception:
                logger.debug("aek_enrichment_skipped", exc_info=True)

            # V31.5 (Full Exercise OS): القصة التربوية الشاملة — Carousel متعدّد
            # الخطوات يغطّي التمرين كاملاً (معطيات → فضاء عيّنة → حدث مركّب →
            # متغيّر عشوائي). يُفعَّل عند حيرة الطالب. terminate_pipeline=True
            # يكبح جدار النص — companion_text (جملة واحدة) هو النص الوحيد.
            if isinstance(result, FullExerciseStoryOutput):
                return {
                    "component": "full_exercise_story",
                    # V38.0: MODE_B (confusion) keeps pipeline alive for deep narrative.
                    # D-116: الاحتمالات = مُعلّم بصري حتمي كامل ⇒ terminate دائماً
                    # (حتى عند الحيرة) — لا سرد LLM (مصدر الغارباج). البصري هو البيداغوجيا.
                    "terminate_pipeline": True,
                    "routing_mode": _routing_mode,
                    "companion_text": _companion_text_for_focus(result.companion_text),
                    "props": {
                        "title": result.title,
                        "ui_mode": result.ui_mode,
                        "calculated": True,
                        "n": result.n,
                        "k": result.k,
                        "total_combinations": result.total_combinations,
                        "exercise_steps": [
                            {
                                "step_index": s.step_index,
                                "step_id": s.step_id,
                                "title": s.title,
                                "render_kind": s.render_kind,
                                "visual_directives": s.visual_directives,
                                "numerical_state": s.numerical_state,
                                "pedagogical_message": s.pedagogical_message,
                            }
                            for s in result.exercise_steps
                        ],
                        "focus_step_id": _focus_step_id,
                    },
                    "fallback_text": (
                        f"شرح بصري شامل: سحب {result.k} من {result.n} "
                        f"(C={result.total_combinations}) عبر {len(result.exercise_steps)} خطوات."
                    ),
                    "aek_state": _aek_state,
                }

            # V28.0: الحالة المستحيلة — short-circuit كامل للـ pipeline.
            # terminate_pipeline=True يُوقف كل عقد LLM/شجرة/synthesizer لاحقة.
            # companion_text (≤ 120 حرف) هو النص الوحيد المسموح به مع المكوّن.
            if isinstance(result, ImpossibleCaseOutput):
                return {
                    "component": "impossible_draw_animation",
                    # V38.0: impossible_case always terminates in MODE_A.
                    # In MODE_B (confusion about impossible draw), pipeline stays alive
                    # so the LLM can explain WHY the draw is impossible pedagogically.
                    # D-116: الاحتمالات = مُعلّم بصري حتمي كامل ⇒ terminate دائماً
                    # (حتى عند الحيرة) — لا سرد LLM (مصدر الغارباج). البصري هو البيداغوجيا.
                    "terminate_pipeline": True,
                    "routing_mode": _routing_mode,
                    "companion_text": _companion_text_for_focus(result.companion_text),
                    "props": {
                        "title": result.title,
                        "ui_mode": result.ui_mode,
                        "visual_directives": {
                            "animation_hint": result.visual_directives.animation_hint,
                            "fallback_math": result.visual_directives.fallback_math,
                        },
                        "numerical_state": {
                            "available_items": result.numerical_state.available_items,
                            "requested_items": result.numerical_state.requested_items,
                            "item_color": result.numerical_state.item_color,
                        },
                        "pedagogical_message": result.pedagogical_message,
                        "item_label": result.item_label,
                        "container": result.container,
                    },
                    "fallback_text": result.pedagogical_message,
                    "aek_state": _aek_state,
                }

            if isinstance(result, CombinationsModelOutput):
                props = {
                    "title": result.title,
                    "calculated": True,
                    "draw_mode": "simultaneous",
                    "deep_dive": result.deep_dive,
                    "n": result.n,
                    "k": result.k,
                    "total_combinations": result.total_combinations,
                    "groups": [
                        {
                            "label": g.label,
                            "count": g.count,
                            "favorable_combinations": g.favorable_combinations,
                            # V30.0 — حارس الحلقة الداخلية: الواجهة تعرض
                            # pedagogical_string حين is_possible=False بدل C_n^k=0.
                            "is_possible": g.is_possible,
                            "pedagogical_string": g.pedagogical_string,
                            "color": g.color,
                        }
                        for g in result.groups
                    ],
                    "same_group_favorable": result.same_group_favorable,
                    "formula": result.formula,
                    # V30.0 — القصة البصرية الشاملة (Deep Dive storytelling).
                    "urn_state": result.urn_state,
                    "event_analysis": result.event_analysis,
                    # طلب الطالب المركّز: يسمح للواجهة بإبراز جزء محدد بدل العرض العام.
                    "focus_step_id": _focus_step_id,
                }
                return {
                    "component": "combinations_visualizer",
                    # V38.0: MODE_B (confusion) keeps pipeline alive for deep narrative.
                    # MODE_A terminates after the visual component (Text-Wall Muzzle).
                    # D-116: الاحتمالات = مُعلّم بصري حتمي كامل ⇒ terminate دائماً
                    # (حتى عند الحيرة) — لا سرد LLM (مصدر الغارباج). البصري هو البيداغوجيا.
                    "terminate_pipeline": True,
                    "routing_mode": _routing_mode,
                    "companion_text": _companion_text_for_focus(
                        "إليك الشرح البصري المفصل للتمرين خطوة بخطوة 🪄"
                    ),
                    "props": props,
                    "fallback_text": (
                        f"سحب آني: اختيار {result.k} من {result.n} → "
                        f"عدد التأليفات C({result.n},{result.k}) = {result.total_combinations}."
                    ),
                    "aek_state": _aek_state,
                }

            if isinstance(result, ProbabilityModelOutput):
                props = {
                    "title": result.title,
                    "is_illustrative": False,
                    "calculated": True,
                    "with_replacement": result.with_replacement,
                    "total": result.total,
                    "composition": [
                        {
                            "label": item.label,
                            "count": item.count,
                            "p_num": item.p_num,
                            "p_den": item.p_den,
                            "p_decimal": item.p_decimal,
                        }
                        for item in result.composition
                    ],
                    "tree": result.tree,
                }
                return {
                    "component": "probability_tree",
                    # V38.0: MODE_B (confusion) keeps pipeline alive for deep narrative.
                    # MODE_A terminates after the visual component (Text-Wall Muzzle).
                    # D-116: الاحتمالات = مُعلّم بصري حتمي كامل ⇒ terminate دائماً
                    # (حتى عند الحيرة) — لا سرد LLM (مصدر الغارباج). البصري هو البيداغوجيا.
                    "terminate_pipeline": True,
                    "routing_mode": _routing_mode,
                    "companion_text": _companion_text_for_focus(
                        "إليك الشرح البصري المفصل للتمرين خطوة بخطوة 🪄"
                    ),
                    "props": props,
                    "fallback_text": ("شجرة الاحتمالات (تعذّر عرض الرسم التفاعلي — هذا نص بديل)."),
                    "aek_state": _aek_state,
                }
            return None
        except Exception:
            logger.warning("_build_calculated_ui_failed", exc_info=True)
            return None

    async def _build_probability_tree_props(
        self,
        question: str,
        history_messages: list[dict[str, str]] | None = None,
    ) -> dict[str, object] | None:
        """غلاف غير متزامن: استخراج حتمي ثم إثراء LLM للتسميات عند الحاجة فقط.

        إذا فشل الاستخراج الحتمي في إيجاد كيان ملموس (``labels_generic=True``)،
        نحاول أولاً استخراج الكيانات من سياق المحادثة (history_messages) قبل
        اللجوء للـ LLM. هذا يحل Bug D: "اعطني شجرة الاحتمالات" بعد تمرين
        الاحتمالات 2024 يجب أن يُنتج "كرة حمراء" لا "الحدث الأول".

        Bug A fix: كل المسار محروس بـ try/except شامل — أي استثناء (بما فيه
        pydantic.ValidationError من get_settings() أو asyncio.TimeoutError من
        _enrich_tree_labels_with_llm) يُسجَّل ويُرجع None بدلاً من الانتشار
        للـ WebSocket handler وتسبيب 500 HTML bleed في Next.js DevTools.
        """
        try:
            # ── D-075 (Protocol V14.0): REAL probability calculation first ──
            # ProbabilityCalculatorSkill يحسب كسوراً حقيقية من تركيبة المسألة
            # العربية (P(حمراء)=4/11) بدلاً من القيمة الوهمية 0.5. يُحاول السؤال
            # ثم سياق المحادثة. عند النجاح نُرجع شجرة بكسور دقيقة (p_num/p_den).
            calc_props = self._build_calculated_tree_props(question, history_messages)
            if calc_props is not None:
                return calc_props

            props = self._detect_probability_tree(question)
            if props is None:
                return None
            if not props.get("labels_generic"):
                props.pop("labels_generic", None)
                return props

            # Bug D fix: محاولة استخراج كيانات ملموسة من سياق المحادثة أولاً
            # (أسرع وأكثر دقة من LLM عند وجود تمرين سابق في السياق)
            if history_messages:
                history_text = " ".join(
                    str(m.get("content", ""))[:2000]
                    for m in history_messages[-6:]
                    if isinstance(m, dict)
                ).lower()
                if history_text.strip():
                    context_events = self._extract_concrete_events(history_text)
                    if context_events is not None:
                        tree = props.get("tree")
                        if isinstance(tree, dict):
                            children = tree.get("children")
                            if isinstance(children, list) and len(children) == 2:
                                children[0]["label"] = context_events["first"]
                                children[1]["label"] = context_events["first_neg"]
                                for branch in children:
                                    sub = branch.get("children")
                                    if isinstance(sub, list) and len(sub) == 2:
                                        sub[0]["label"] = context_events["second"]
                                        sub[1]["label"] = context_events["second_neg"]
                        props.pop("labels_generic", None)
                        return props

            # محاولة إثراء عبر LLM (best-effort) عند غياب السياق
            with contextlib.suppress(Exception):
                enriched = await self._enrich_tree_labels_with_llm(question)
                if enriched is not None:
                    tree = props.get("tree")
                    if isinstance(tree, dict):
                        children = tree.get("children")
                        if isinstance(children, list) and len(children) == 2:
                            children[0]["label"] = enriched["first"]
                            children[1]["label"] = enriched["first_neg"]
                            for branch in children:
                                sub = branch.get("children")
                                if isinstance(sub, list) and len(sub) == 2:
                                    sub[0]["label"] = enriched["second"]
                                    sub[1]["label"] = enriched["second_neg"]
            props.pop("labels_generic", None)
            return props
        except Exception:
            logger.warning("_build_probability_tree_props_failed", exc_info=True)
            return None

    @staticmethod
    async def _enrich_tree_labels_with_llm(question: str) -> dict[str, str] | None:
        """يستخرج كيانات ملموسة عبر LLM ويُرجع dict تسميات أو None عند الفشل.

        محروس بـ timeout 8s. يرفض أي ناتج يحوي رموزاً مجرّدة (A/B بمفردها).
        """
        import asyncio
        import json

        from app.core.ai_gateway import get_ai_client

        system_prompt = (
            "أنت مستخرج كيانات لمسائل الاحتمالات. من نص المسألة، استخرج حدثين "
            "كعبارات اسمية عربية قصيرة وملموسة (مثل 'كرة حمراء'، 'قطعة معيبة'، "
            "'سحب ناجح'). ممنوع منعاً باتاً استخدام الرموز المجرّدة A أو B أو Ā. "
            "أعِد JSON فقط بهذا الشكل بلا أي نص آخر: "
            '{"first":"...","first_neg":"...","second":"...","second_neg":"..."}'
        )
        ai_client = get_ai_client()
        raw = await asyncio.wait_for(
            ai_client.send_message(system_prompt, question.strip()[:1200], temperature=0.2),
            timeout=8.0,
        )
        if not raw or not isinstance(raw, str):
            return None
        start = raw.find("{")
        end = raw.rfind("}")
        if start == -1 or end == -1 or end <= start:
            return None
        data = json.loads(raw[start : end + 1])
        keys = ("first", "first_neg", "second", "second_neg")
        if not all(isinstance(data.get(k), str) and data[k].strip() for k in keys):
            return None
        cleaned = {k: data[k].strip()[:60] for k in keys}
        # رفض الرموز المجرّدة (Abstraction Ban)
        banned = {"a", "b", "ā", "b̄", "a'", "b'"}
        if any(cleaned[k].lower() in banned for k in keys):
            return None
        return cleaned
