"""Platform Layer — sliced verbatim from the former doctrine.py (D-173 Stage 2a).

جزء من حزمة `app.services.skills.doctrine` — المصدر الوحيد للحقيقة لقواعد كل
Skill. لا تُعرَّف doctrines خارج هذه الحزمة (بوّابة skills-doctrine تحرس ذلك).
"""

from __future__ import annotations

from typing import Final

# ─────────────────────────────────────────────────────────────────────────────

#: نسخة doctrine بروتوكول الـ realtime.
REALTIME_PROTOCOL_DOCTRINE_VERSION: Final[str] = "1.0.0"

REALTIME_PROTOCOL_DOCTRINE: Final[tuple[str, ...]] = (
    "Control messages first: أي WS endpoint يستقبل رسالة بحقل `type` يجب أن "
    "يفحص أولاً ما إذا كانت رسالة تحكم (ping/heartbeat/noop) قبل معالجتها كسؤال.",
    'Ping ⇒ Pong: الرسالة `{"type":"ping"}` يجب أن تُرَدّ عليها بـ '
    '`{"type":"pong","ts":<iso-utc>}` فوراً بدون أي معالجة إضافية.',
    'Heartbeat ⇒ Ack: الرسالة `{"type":"heartbeat"}` يجب أن تُرَدّ عليها بـ '
    '`{"type":"heartbeat_ack","ts":<iso-utc>}`.',
    'Noop ⇒ Silent: الرسالة `{"type":"noop"}` تُبتلَع بصمت بدون رد (لا flooding).',
    "Heartbeat هو Skill، ليس inline code: يجب استخدام "
    "`app.services.skills.ws_heartbeat_skill.handle_control_message` — "
    "ممنوع نسخ منطق ping/pong في كل router (Single Source of Truth).",
    "Fail-open: إذا فشل إرسال pong (مثل client disconnected بين receive و send)، "
    "يُسجَّل DEBUG ولا يُكسَر loop — receive_json التالي سيكشف الإغلاق.",
    'Correlation: لو أرسل العميل `{"type":"ping","id":"..."}`، يجب أن '
    "يُضمَّن نفس الـ `id` في الـ pong لتمكين tracing.",
    "Backend-initiated heartbeat ليس بديلاً عن Application-level ping: uvicorn "
    "`--ws-ping-interval` يفحص الـ TCP layer فقط — لا يكشف إذا كان الـ handler "
    "عالق. الـ app-level heartbeat هو نظام liveness حقيقي للطبقة العليا.",
)


def get_realtime_protocol_summary() -> str:
    """يُرجِع ملخصاً موجزاً لـ doctrine بروتوكول الـ realtime (للـ logs/system prompts)."""
    return (
        f"[v{REALTIME_PROTOCOL_DOCTRINE_VERSION}] "
        f"{len(REALTIME_PROTOCOL_DOCTRINE)} قاعدة — "
        "ping/pong + heartbeat/ack موحَّد عبر Skill، fail-open، correlation IDs."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Skills Platform Doctrine (D-100 — Registry + Composition + Observability)
# ─────────────────────────────────────────────────────────────────────────────
#: نسخة doctrine منصّة الـ Skills الموحَّدة.
SKILLS_PLATFORM_DOCTRINE_VERSION: Final[str] = "1.0.0"

SKILLS_PLATFORM_DOCTRINE: Final[tuple[str, ...]] = (
    "Single registry: كل Skill يُسجَّل في `registry.get_skill_registry()` ببيانات "
    "وصفية موحَّدة (name, contract, primary_method, consumed_by, status).",
    "No ZOMBIE: كل Skill مُسجَّل يجب أن يملك مُستهلِكاً حيّاً في `consumed_by` — "
    "الـ CI gate يحرس على ذلك (مرآة D-073).",
    "Additive only: المنصّة لا تُعيد توصيل المسار الحيّ — تُوفِّر صياغة رسمية "
    "(compose_text_refinement) + سطح رصد (/api/v1/skills) دون لمس الدردشة الحيّة.",
    "Graceful degradation: كل خطوة في `compose_text_refinement` معزولة — فشلها "
    "يُتجاهَل ويُحتفَظ بالنص (لا يكسر المسار أبداً).",
    "Flagged dormants: الـ Skills المُفعَّلة من قدرات DORMANT (retrieval_rerank, "
    "mcp_tool) مُعطَّلة افتراضياً وتُرجِع None عند التعطيل (صفر تغيير سلوكي).",
    "Metric-emitter contract (§6.21): كل مقياس يُعرَض في المنصّة له مُصدِر حقيقي "
    "في الكود — لا zombie metrics.",
)


def get_skills_platform_summary() -> str:
    """يُرجِع ملخصاً موجزاً لـ doctrine منصّة الـ Skills (للـ logs/system prompts)."""
    return (
        f"[v{SKILLS_PLATFORM_DOCTRINE_VERSION}] "
        f"{len(SKILLS_PLATFORM_DOCTRINE)} قاعدة — registry موحَّد، no-ZOMBIE، "
        "additive، graceful degradation، flagged dormants، metric-emitter contract."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Content Integrity Doctrine (D-106 · ISS-114)
# ─────────────────────────────────────────────────────────────────────────────
# حارس نزاهة المحتوى المواجه للطالب — يلتقط الغارباج اللاتيني وتسريب HTML على
# كامل بثّ الإجابة (لا أول نافذة فقط). المُستهلِك: orchestrator_client (مخرج
# الـ orchestrator HTTP) + local_graph (المسار المحلي).
# ─────────────────────────────────────────────────────────────────────────────

#: نسخة doctrine نزاهة المحتوى.
#: 1.1.0 (D-289/ISS-201): استثناءٌ بنيوي (URL/مسار/مُعرِّف/شيفرة مُضمَّنة لا تُحذف)
#: + توسيع محافظة الـ allowlist بمفردات SI/الكيمياء/الملفات — لأن الحذف الأعمى كان
#: يُسلِّم إجابة مبتورة للطالب بعد إصلاح سلسلة النماذج نفسها.
CONTENT_INTEGRITY_DOCTRINE_VERSION: Final[str] = "1.1.0"

CONTENT_INTEGRITY_DOCTRINE: Final[tuple[str, ...]] = (
    "كل بثّ مواجه للطالب يمرّ عبر StreamIntegrityFilter على **كامل التيار** — "
    "لا أول 200 حرف فقط (ثغرة arabic_stream_guard التاريخية).",
    "الثغرة الأكبر مُغلقة: بثّ orchestrator-service (MODE_B) عبر HTTP لم يكن "
    "يمرّ بأي حارس — الآن يُلفّ بالمرشّح عند مخرج المونوليث (نقطة الاختناق "
    "الوحيدة المواجهة للطالب)؛ response_sanitizer للخدمة يبقى دفاعاً ثانوياً.",
    "وضع اللغة العربي (نسبة ≥ 0.5 في أول نافذة) يُفعِّل فلترة اللاتيني؛ الإجابة "
    "الفرنسية/Darija المشروعة تمرّ بلا حذف (تنظيف HTML فقط) — لا إفراط حذف.",
    "spans الرياضيات (LaTeX: $...$, $$...$$, \\(...\\), \\[...\\]) تُبثّ حرفياً "
    "أبداً — صفر مساس (قوانين D-051/D-062).",
    "الـ allowlist التقنية محافظة (مفردات رياضية + BAC فرنسية، مقارنة بعد "
    "NFD-strip): توسيعها = ترقية doctrine. كل ما عداها من لاتيني >2 حرف يُحذف.",
    "fail-open مطلق: أي استثناء في المرشّح ⇒ تعطيل دائم وإرجاع النص الخام — "
    "حارس النزاهة لا يكسر دور الطالب أبداً.",
    "HTML/JSX لا يصل نص الطالب أبداً — الواجهات حصراً عبر قناة ui_component "
    "المُهيكلة (Channel A — D-086)، لا عبر نص يكتبه الـ LLM.",
    "v1.1.0 — لا يُحذف لاتينيٌّ هو بنيةٌ نصية مقصودة: URL/مسار/مُعرِّف فيه رقم أو "
    ":/-. أو شيفرة مُضمَّنة بين علامتَي اقتباس خلفيّتين (`...`). غارباج النماذج "
    "(«experiences_random»، «Eingaben») يبقى محذوفاً؛ والقاعدة صُمِّمت كي لا "
    "تتحوَّل حمايةُ النزاهة إلى إتلافٍ للإجابة (D-289/ISS-201).",
)


def get_content_integrity_summary() -> str:
    """يُرجِع ملخص doctrine نزاهة المحتوى (للـ logs / system prompts)."""
    return (
        f"[v{CONTENT_INTEGRITY_DOCTRINE_VERSION}] "
        f"{len(CONTENT_INTEGRITY_DOCTRINE)} قاعدة — فلترة كامل البثّ، حماية "
        "اللاتيني التقني، LaTeX حرفي، fail-open، HTML ممنوع في نص الطالب."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Learning Path Doctrine (D-111 · المسار التعلّمي التكيفي)
# ─────────────────────────────────────────────────────────────────────────────
# القفزة التربوية فوق BKT (D-074): يقترح الخطوة التالية وصعوبة متكيفة من الإتقان.
# «المعيار الأعلى ليس الانبهار اللحظي، بل الاستقلال المعرفي» — فلسفة E-TAALEEM.
# ─────────────────────────────────────────────────────────────────────────────

#: نسخة doctrine المسار التعلّمي.
LEARNING_PATH_DOCTRINE_VERSION: Final[str] = "1.1.0"

LEARNING_PATH_DOCTRINE: Final[tuple[str, ...]] = (
    "يُبنى حصراً فوق student_mastery_probability (D-074) — لا يُعيد اختراع تتبّع "
    "الإتقان؛ يستهلك BKT_COGNITIVE_DOCTRINE و ADAPTIVE_PEDAGOGY_DOCTRINE.",
    "حتمي تماماً: نفس (المفهوم، الإتقان) ⇒ نفس التوصية — لا LLM، لا I/O داخل "
    "الـ Skill (الإتقان يُمرَّر من المُستدعي) — قابل لاختبار pytest.",
    "إتقان ≥ 0.7 ⇒ تقدّم للمفهوم التالي في تسلسل منهج BAC + صعوبة hard (الطالب جاهز للتحدّي).",
    "0.35 ≤ إتقان < 0.7 ⇒ ابقَ على المفهوم + صعوبة medium (ترسيخ قبل التقدّم).",
    "إتقان < 0.35 أو مجهول ⇒ ابقَ على المفهوم + صعوبة easy (ثبّت الأساس أولاً).",
    "التسلسل خريطة منهج ثابتة (لا overfitting لمسألة بعينها)؛ المفهوم الأخير في "
    "السلسلة يبقى عليه عند الإتقان (لا يخترع مفهوماً غير موجود).",
    "fail-open مطلق: أي تعذّر ⇒ توصية محايدة آمنة — لا يكسر دور الطالب.",
    "D-119: التوصية تُشتقّ وتُسجَّل خلف الكواليس (telemetry / لوحة المعلم) — "
    "لا تُعرَض كبطاقة للطالب (سطح الطالب = تعليم نظيف فقط، لا تتبّع مُكرَّر).",
)


def get_learning_path_summary() -> str:
    """يُرجِع ملخص doctrine المسار التعلّمي (للـ logs)."""
    return (
        f"[v{LEARNING_PATH_DOCTRINE_VERSION}] "
        f"{len(LEARNING_PATH_DOCTRINE)} قاعدة — فوق BKT، حتمي، 3 عتبات إتقان، "
        "تسلسل منهج ثابت، fail-open."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Mandatory Orchestration Doctrine (D-112 · العمود الفقري الإلزامي)
# ─────────────────────────────────────────────────────────────────────────────
# قرار المستخدم (2026-06-13): الخدمات المصغرة + الرسم الـ13-node هي القلب
# الإلزامي الوحيد. عند تعذّرها ⇒ خطأ صريح، لا fallback صامت إلى local_graph.
# ─────────────────────────────────────────────────────────────────────────────

#: نسخة doctrine العمود الفقري الإلزامي.
MANDATORY_ORCHESTRATION_DOCTRINE_VERSION: Final[str] = "1.0.0"

MANDATORY_ORCHESTRATION_DOCTRINE: Final[tuple[str, ...]] = (
    "الخدمات المصغرة + الرسم الـ13-node هي القلب الإلزامي الوحيد للتوليد — "
    "لا نتظاهر أن الرسم المحلي ذا العقدتين بديل عنها (runtime truth over synthetic certainty).",
    "عند تعذّر الـ orchestrator (تعذّر اتصال/empty_stream) ⇒ إطار error صريح بالرمز "
    "ORCHESTRATOR_REQUIRED ورسالة عربية واضحة — صفر سقوط صامت إلى local_graph.",
    "علم REQUIRE_ORCHESTRATOR=1 افتراضي مُفعَّل؛ =0 يُعيد الـ fallback القديم "
    "(rollback فوري بلا deploy — نمط D-025).",
    "المقايضة الصريحة: فقدان المرونة عمداً — سقوط الـ orchestrator في الإنتاج = "
    "انقطاع كامل (لا إجابة ضعيفة). القرار يخصّ المالك ومُوثَّق.",
    "الموصول حيّاً: orchestrator_client.chat_with_agent بعد فشل كل المرشّحين.",
)


def get_mandatory_orchestration_summary() -> str:
    """يُرجِع ملخص doctrine العمود الفقري الإلزامي (للـ logs)."""
    return (
        f"[v{MANDATORY_ORCHESTRATION_DOCTRINE_VERSION}] "
        f"{len(MANDATORY_ORCHESTRATION_DOCTRINE)} قاعدة — microservices-only، "
        "hard-fail ORCHESTRATOR_REQUIRED، علم rollback، مقايضة مرونة صريحة."
    )


# ── D-133: حالة الطالب كإشارة قرار — النيّة + الإحباط (إعادة توجيه المالك) ─────────────
STUDENT_STATE_DOCTRINE_VERSION: Final[str] = "1.0.0"

#: قوانين غير قابلة للكسر تحكم قراءة حالة الطالب (النيّة + الإحباط، D-133).
STUDENT_STATE_DOCTRINE: Final[tuple[str, ...]] = (
    "إشارة قرار لا قاموس labels: كل intent يجب أن يُنتج **نوع رد مغايراً** فعلاً (تعريف/مثال/"
    "خطوات/علاقة/تعريف+مثال+سؤال/تلميح). label بلا تغيير سياسة = فشل. القيمة في البيداغوجيا المغايرة.",
    "متعدّد الإشارات لا تصنيف جامد: الخرج primary_intent + secondary_signals — «لم أفهم X» = "
    "confusion + (definition) — تحفظ الحزمة النفسية/اللغوية كاملة، لا تقسيمها لنيّة واحدة صارمة.",
    "النيّة تُحدّد نوع الرد لا الكلمة: «لم أفهم X» = confusion (تعريف + مثال ملموس + سؤال موجِّه "
    "واحد)، لا تعريف-فقط ولا سقراطية متكررة؛ «أعطني مثالاً» = مثال قبل النظرية؛ «كيف نحسب» = خطوات.",
    "الإحباط حالة شعورية تُوقف التكرار: «لم أفهم»×كثير = frustration عالٍ ⇒ تقليل الأسئلة + كشف "
    "خطوة رمزية أقرب (socratic_budget→0)، ممنوع سقراطية متكررة على طالب محبَط.",
    "الإحباط لحظي يتلاشى لا هوية ثابتة (نقد المالك 3): يُحسب من نافذة حديثة، يتعافى فور رسالة "
    "غير-حيرة، يُغيّر السياسة لهذا الدور فقط، **لا يُخزَّن** كصفة طالب. لا I/O، لا حالة دائمة.",
    "LLM = مُفسِّر ثانوي لا حَكَم (نقد المالك 2): الكواشف الحتمية + BKT (knowledge tracing) هي "
    "السلطة؛ الـ LLM يُستدعى **فقط** عند primary=unknown (صياغة جديدة) ولا يطغى على إشارة حتمية.",
    "حتمي-أولاً + fail-open: markers أولاً ثم LLM للصياغات الجديدة؛ أي تعذّر ⇒ حالة آمنة "
    "(definition/none) — قراءة الحالة لا تكسر دور الطالب أبداً.",
)


def get_student_state_summary() -> str:
    """يُرجِع ملخص doctrine حالة الطالب (للـ logs)."""
    return (
        f"[v{STUDENT_STATE_DOCTRINE_VERSION}] {len(STUDENT_STATE_DOCTRINE)} قاعدة — "
        "إشارة قرار، متعدّد-إشارات، LLM مُفسِّر ثانوي، إحباط لحظي يتلاشى."
    )


# ── D-142 (Phase 2): مدير الحوار الموحَّد + الحالة الدائمة ─────────────────────────────
DIALOGUE_MANAGER_DOCTRINE_VERSION: Final[str] = "1.1.0"

#: قوانين غير قابلة للكسر تحكم سلطة قرار الدور التعليمي (D-142 Phase 2).
DIALOGUE_MANAGER_DOCTRINE: Final[tuple[str, ...]] = (
    "قرار الدور = f(دليل الفهم، قدرة الطالب، صعوبة الخطوة التالية) كل دور — لا «مصفوفة levels» "
    "جامدة (نقد المالك). الإشارات الثلاث تُحسَب حيّاً، لا «هل وصلنا level 3».",
    "التقدّم حتمي عند دليل فهم موثوق (verified رمزياً أو understood): اعتراف + خطوة تالية، "
    "ممنوع إعادة السؤال نفسه.",
    "لا تكرار حرفي: النصّ المُرشَّح المُكرّر لـ last_step_emitted (مرساة دائمة تنجو من نافذة "
    "التاريخ) ⇒ تصعيد للحلّ الرمزي، لا إعادة.",
    "لا قفز فوق قدرة الطالب: قدرة < صعوبة الخطوة التالية ⇒ خطوة وسطى أصغر، لا تمثيل أعلى من "
    "مستوى المتعلّم.",
    "الميزانية السقراطية **لكل مفهوم** (من الحالة الدائمة) لا عامّة تتسرّب بين المفاهيم؛ استنفادها "
    "⇒ حلّ رمزي لا سؤال إضافي.",
    "حتمي 100% (صفر LLM) قابل للاختبار بـ pytest؛ الأرقام/الصحّة من المحرك الرمزي؛ القدرة من BKT "
    "(D-126). fail-open: أي خطأ ⇒ السلوك القائم.",
    "بوّابة القياس (§2D): التوسّع مرهون بهبوط repetition_rate→0 + advance_after_correct≈100% + "
    "over-jump→0 + فجوة الوهم (D-126) ⤵ — لا توسيع للحالة قبل إثبات اللِّفت.",
    "D-158: قرار الدور يقرأ tutor_state.kc_progress الدائم (representations_delivered / _pending) "
    "لا مسح نصّ السجل؛ خطوة موجودة في representations_delivered لا تُعاد أبداً (منع تكرار عبر الكتل). "
    "طبقة _cognitive_turn خلف COGNITIVE_TURN_ENABLED هي المستهلِك الجديد فوق tutor_state المُخزَّن.",
)


def get_dialogue_manager_summary() -> str:
    """يُرجِع ملخص doctrine مدير الحوار (للـ logs)."""
    return (
        f"[v{DIALOGUE_MANAGER_DOCTRINE_VERSION}] {len(DIALOGUE_MANAGER_DOCTRINE)} قاعدة — "
        "evidence×ability×difficulty، تقدّم حتمي، لا تكرار، لا قفز، ميزانية لكل مفهوم."
    )


# ── D-135: محرّك حالة الفهم — Learning State («ماذا فهم الطالب فعلاً؟») ────────────────
UNDERSTANDING_STATE_DOCTRINE_VERSION: Final[str] = "1.2.0"

#: قوانين غير قابلة للكسر تحكم تتبّع حالة الفهم (Learning State، D-135).
UNDERSTANDING_STATE_DOCTRINE: Final[tuple[str, ...]] = (
    "Learning State هو المحور: القرار يُبنى على «ماذا فُهم وما بقي غير مفهوم» (حالة المكوّنات "
    "المعرفية)، لا على آخر رسالة. السؤال يتحوّل من «ما المفهوم؟» إلى «ماذا فهم الطالب فعلاً؟».",
    "KC-aware لا number-match (نقد المالك 1): الفجوة تُشخَّص بالمعنى (gap_signals)؛ المكوّنات المعرفية "
    "مُشتقّة من المحرك الرمزي (combo)؛ الرقم إشارة واحدة لا مستخرَج. «لماذا قسمنا على 3!» (بلا رقم) ⇒ kc_factorial.",
    "التكرار دلالي لا حرفي (نقد المالك 2): الحالة على مستوى المكوّن (شُرح/فُهم)، لا توقيع نصّي. مكوّن "
    "مفهوم لا يُعاد شرحه أبداً؛ «14/165» ≡ «14 من 165» ≡ «عدد الحالات 14» = نفس المكوّن.",
    "الفهم ببرهان لا صحة (نقد المالك 3): understood يتطلّب understanding_evidence (إظهار مرتبط بالمكوّن)، "
    "لا مجرّد correct_answer. «فهمت» المجرّدة = إقرار ضعيف لا برهان — لا تُرقّي المكوّن إلى مفهوم.",
    "استباقي لا تفاعلي (نقد المالك 4): مكوّن شُرح بلا فهم ⇒ تمثيل أعلى تلقائياً (شرح→مثال→تشبيه→سؤال "
    "تطبيقي) قبل شكوى الطالب «انت تكرر» — Adaptive Learning.",
    "الاعتراف والتقدّم أساسي: برهان فهم ⇒ «أحسنت ✅» + التقدّم لأوّل مكوّن غير مفهوم (الجبهة التعليمية)، "
    "تغيير الاستراتيجية لا مزيد كلام.",
    "الأرقام من المحرك الرمزي حصراً (ProbabilityCalculatorSkill/combo)؛ صفر LLM في الحقيقة؛ كل التمثيلات "
    "حتمية وتَنجو من حجب D-113. الـ LLM (سؤال موجِّه/تقييم) محروس فقط (D-128/D-130).",
    "D-159 (WP-C — تقاعد مسح النصّ): الحالة الدائمة (tutor_state.kc_progress) هي **سلطة** حالة المكوّنات "
    "(understood/explained) — مسح نصّ المحادثة fallback للأدوار السابقة على التخزين فقط. الترقية أحادية "
    "الاتجاه (الدائم يرفع ولا يُنزِل ما أثبته النصّ)، وقرار المحرّك (understood_kc_id + المكوّن المشروح) "
    "يُكتب فوراً في kc_progress عبر دلتا record_turn — الذاكرة تتراكم لا تُعاد هندستها كل دور.",
    "D-165 (ISS-129 — غاية التمرين = مكوّناته المعرفية): سؤال الغاية meta («ماذا نستفيد/نتعلم من هذا "
    "التمرين؟») يُجاب حتمياً من عناوين الـ KCs (exercise_purpose_summary — data-driven من combo، عناوين "
    "فقط بلا أي نسبة نهائية) ولا يُختطف بالـ probe التشخيصي أبداً؛ وأي سؤال غير-إجرائي لم تُجبه الطبقات "
    "الحتمية يهرب لطبقات الإجابة (D-112) **قبل** الـ probe — لا سؤال يُقابَل بسؤال يتجاهله.",
)


def get_understanding_state_summary() -> str:
    """يُرجِع ملخص doctrine حالة الفهم (للـ logs)."""
    return (
        f"[v{UNDERSTANDING_STATE_DOCTRINE_VERSION}] {len(UNDERSTANDING_STATE_DOCTRINE)} قاعدة — "
        "Learning State، KC-aware، تكرار دلالي، فهم ببرهان، تمثيل استباقي."
    )


# ── D-138: المصفوفة التصعيدية التكيّفية — Escalation + Understanding-Signal + Misconception ──
# ── D-147: نفاد السُّلّم ⇒ سؤال تطبيق مرتبط بالتمرين بدل الـ punt العام ──
# ── D-159 (WP-B): FSM دائم — الرُّتب المُسلَّمة من tutor_state.kc_progress لا مسح النصّ وحده ──
PEDAGOGICAL_ESCALATION_DOCTRINE_VERSION: Final[str] = "1.2.0"

#: قوانين غير قابلة للكسر تحكم المصفوفة التصعيدية التكيّفية (D-138).
PEDAGOGICAL_ESCALATION_DOCTRINE: Final[tuple[str, ...]] = (
    "السقالة تُختار بسؤال واحد قبل كل تدخّل (حكم المالك): «هل تناسب قدرة الطالب الحالية "
    "(support_level/BKT) وصعوبة الخطوة القادمة؟» — لا تُمرَّر كل الحالات عبر سلّم جامد L1/L2/L3. "
    "نفس النيّة + طالب مختلف ⇒ رُتبة مختلفة (مرونة لا جمود).",
    "التصعيد يعتمد على أثر الفهم (Understanding Signal) لا عدّ «لم أفهم»: دليل فهم المفهوم "
    "(evidence_markers — آلية لا تقليد عبارة) ⇒ action=mastered (توقّف + اعتراف). القيمة في تتبّع "
    "الإتقان لا تصنيف إجابة واحدة.",
    "Misconception Check قبل التصعيد (تشخيص دقيق للاستدلال): عقدة مُشخَّصة (diagnose_misconception) ⇒ "
    "action=target_misconception (intervention مُوجَّه) بدل تسلّق السلّم أعمى. كل عقدة لها bkt_concept صريح.",
    "Ability + Step-Difficulty Calibration: support_level (1..5 من BKT) يُعايِر الرُّتبة — قدرة منخفضة "
    "(1-2) ⇒ تصعيد أسرع لسقالة أعلى (محاكاة مصغّرة)؛ قدرة عالية (4-5) ⇒ رُتبة أخف (تعريف + سؤال موجِّه، "
    "student agency) لا إفراط في السقالة.",
    "ممنوع تكرار رُتبة استراتيجية: ذاكرة التصعيد (stateless من history) تمنع إعادة نفس المستوى؛ الحيرة ⇒ "
    "المستوى التالي غير المُسلَّم المُعايَر بالقدرة؛ استنفاد L3 ⇒ exhausted (تسليم لطيف، لا تكرار، لا L4 الآن).",
    "concept-scoped حصراً: تعمل على المفهوم النشط (detect_active_concept)، لا على مكوّنات تمرين البكالوريا "
    "(لا انحراف لـ event-A/نفس اللون). سُلّم الاستراتيجية: L1_DEFINITION → L2_ANALOGY → L3_MICRO_SIMULATION "
    "(L4_VISUAL مؤجَّل — لا واجهة توليدية في القلب الآن).",
    "policy أولاً، content-server ثانياً: المصفوفة تقرّر، MicroSimulationSkill يخدم L3. نقيس الأثر السلوكي "
    "فقط (تراجع التكرار + تدرّج الرُّتب + ارتفاع الإتقان BKT) — لا تحسين على «الرضا اللحظي».",
    "D-147: نفاد السُّلّم (exhausted) ⇒ سؤال «خطوة تطبيق» مرتبط ببنية هذا التمرين (APPLY_STEPS، concept-scoped) "
    "يقود الطالب للخطوة الأولى الملموسة — لا punt عامّ («أيّ خطوة تريد؟»). يبقى سؤالاً (توليد لا كشف) ⇒ يَنجو "
    "من حجب D-113؛ المفهوم غير المُغطّى يرجع للتسليم العامّ القديم (لا انحدار).",
    "D-159 (WP-B — FSM دائم): ذاكرة التصعيد سلطتها الحالة الدائمة (delivered_levels من "
    "tutor_state.kc_progress.escalation_levels — تَنجو من نافذة الـ50 رسالة وإعادة تشغيل العملية)، "
    "ومسح نصّ المساعد شبكة أمان للأدوار السابقة على التخزين — **الاتحاد** يمنع تكرار الرُّتبة من أي "
    "مصدر. كل رُتبة تُبثّ (action=teach) تُكتب فوراً في kc_progress عبر دلتا record_turn.",
)


def get_pedagogical_escalation_summary() -> str:
    """يُرجِع ملخص doctrine المصفوفة التصعيدية (للـ logs)."""
    return (
        f"[v{PEDAGOGICAL_ESCALATION_DOCTRINE_VERSION}] {len(PEDAGOGICAL_ESCALATION_DOCTRINE)} قاعدة — "
        "Escalation + Understanding-Signal + Misconception-Check + ability calibration."
    )


# ── D-138: محرّك المحاكيات المصغّرة الحتمي — خادم محتوى L3 ────────────────────────────
MICRO_SIMULATION_DOCTRINE_VERSION: Final[str] = "1.0.0"

#: قوانين غير قابلة للكسر تحكم محرّك المحاكيات المصغّرة (D-138).
MICRO_SIMULATION_DOCTRINE: Final[tuple[str, ...]] = (
    "حتمي 100% صفر-LLM (نقد MathDial): الأمثلة ثابتة في كود، لا يُولّدها نموذج (النماذج تكشف الحل "
    "مبكراً أو تُعطي feedback غير دقيق). محرّك المحتوى لا يخترع الأرقام.",
    "قصير جداً isomorphic لا شرح جديد كامل: ≤320 حرف (≤3 جُمل)، مُصمَّم للتشابه البنيوي مع المفهوم — "
    "أرقام صغيرة آمنة خاصة به (لا أرقام التمرين 11/165) فيَنجو من حجب D-113 ولا يكشف جواب التمرين.",
    "خادم L3 للمصفوفة لا مسار مستقلّ: يُستدعى فقط حين تقرّر المصفوفة التصعيدية أن الوقت مناسب "
    "لمحاكاة مصغّرة (قدرة منخفضة / طلب مثال عددي / استنفاد الرُّتب الأخفّ). مفهوم بلا محاكاة ⇒ None.",
)


def get_micro_simulation_summary() -> str:
    """يُرجِع ملخص doctrine المحاكيات المصغّرة (للـ logs)."""
    return (
        f"[v{MICRO_SIMULATION_DOCTRINE_VERSION}] {len(MICRO_SIMULATION_DOCTRINE)} قاعدة — "
        "deterministic، isomorphic، ≤320 حرف، خادم L3."
    )


# ─────────────────────────────────────────────────────────────────────────────
# Skill Doctrine Manifest (للـ CI gate)
