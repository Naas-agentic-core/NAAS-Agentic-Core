# 🧠 `.memory/` — الذاكرة المؤسسية الحيّة (الفهرس الموحَّد)

> **العقد**: `CLAUDE.md` هو الدستور التشغيلي؛ `.memory/` هو الذاكرة المؤسسية المُنسَّقة.
> كل معلومة تشغيلية قصيرة تعيش هنا — لا تقارير طويلة جديدة (CLAUDE.md §15 + D-156).
> قاعدة الصدق (§6.6): لا حقيقة بلا `import + call chain + runtime evidence`.

## 1) الملفات السيادية (تُحدَّث مع كل قرار — تحرسها بوّابة `doc-integrity`)

| الملف | الدور | السلطة |
|-------|------|--------|
| `roadmap.md` | 🧭 الرؤية الثورية وخارطة الطريق (M0→M11) — **المصدر الحيّ الوحيد** | دستوري |
| `decisions.md` | سجلّ القرارات المعمارية **D-001 → D-290** — كل قرار بسرده وجذره ودليله الحيّ. أحدثها: **D-290** (دستور اعتمادية الوكلاء والعملة الصعبة) · **D-289** (الحارسُ أستاذٌ لا رقابة) · **D-288** (القدرةُ لا تُطعِم طالباً) · **D-287** (الدفعة الآلية تسقط في بوّابةٍ لا تجتازها). | سجلّ ملزِم |
| `issues.md` | سجلّ الكوارث المُشخَّصة والمُصلَحة **ISS-001 → ISS-202** — كلٌّ بجذرها ودليلها الحيّ وشرط إغلاقها. أحدثها: **ISS-202** (ستّ صورٍ تعدم `required-ci`: `litellm==1.50.0` اختفى من PyPI — ✅ D-205 remedy) · **ISS-201** (حارسٌ يمزّق الإجابة — ✅ D-289) · **ISS-200** (صدارةٌ بلا endpoint — ✅ D-288). | سجلّ ملزِم |
| `runtime_truth.md` | جدول الحقيقة التشغيلية (ACTIVE/PARTIAL/DORMANT/ZOMBIE) | **الحقيقة المرجعية** |
| `context.md` | السياق التشغيلي المُلخَّص (يُحمَّل آلياً عند بدء الجلسات) | مرجع سريع |
| `architecture.md` | الخريطة المعمارية المُختصرة | مرجع |
| `tasks.md` · `progress.md` · `logs.md` | تتبّع المهام والتقدّم | تشغيلي |

## 2) العقائد (Doctrines — لا تُكسر بدون ADR)

| الملف | العقيدة |
|-------|---------|
| `pedagogical_os.md` | 📜 دستور نظام التشغيل التربوي (D-153) — السلسلة القانونية + القوانين السبعة |
| `pedagogy_engine_constitution.md` | 📜 دستور المحرك التربوي (D-263) — العقل التربوي كـmoat · القوانين العشرة الصارمة L1–L10 · ISS-174→ISS-177 · **الإضافة لا الاستبدال** |
| `adaptive_study_planner_constitution.md` | 📜 دستور المخطط الدراسي التكيفي (D-264) — Adaptive AI Study Planner · L1–L10 · ISS-178→ISS-181 · **الإضافة لا الاستبدال** |
| `spec_kit_governance_constitution.md` | 📜 دستور حوكمة Spec Kit (D-265) — طبقة ضبط تنفيذ فوق الدستورية · L1–L10 · ISS-182→ISS-185 · **الإضافة لا الاستبدال** |
| `governance_enforcement_constitution.md` | 📜 دستور فرض الحوكمة (D-266) — الفارض نفسه يخضع للبرهان الثلاثي · L1–L10 (وL9 **بلا فارضٍ آلي** ويُقال ذلك) · ISS-186 · حالتُه `docs/governance/CONSTITUTION_REGISTRY.json` |
| `naas_verification_constitution.md` | 📜 دستور طبقة التحقّق (D-267) — المُتحقِّق منتجٌ بحدٍّ مستقلّ والدليل قبل الادّعاء · L1–L10 · ISS-187→ISS-190 · **الإضافة لا الاستبدال** |
| `agent_reliability_hard_currency_constitution.md` | 📜 **دستور اعتمادية الوكلاء والعملة الصعبة (D-290)** — البرمجيات فوق العتاد والدليل قبل السرد · L1–L10 · تموضع غير قابل للتفاوض · بوابة عملة صعبة (K2/K3) · H1–H7 قابلة للدحض · **الإضافة لا الاستبدال** |
| `secret_capture_constitution.md` | 📜 دستور التقاط السرّ (D-268) — السرّ يُلتقط عند كل بابٍ مُعلَن أو لا يُقال إنه ملتقَط · L1–L10 · ISS-191 · المصدر الواحد `config/secret_catalog.json` · **الإضافة لا الاستبدال** |
| `ambient_identity_constitution.md` | 📜 دستور الهوية المعرفية المحيطة (D-269) — الطبقة الخامسة تُقرأ ولا تحكم، والقدرة تُثبَت بمسبارٍ لا بمفتاح · L1–L10 · ISS-192→ISS-193 · **الإضافة لا الاستبدال** |
| `agentic_runtime_doctrine.md` | طبقات الـ Agentic Runtime الـ13 مُقيَّمة بصدق (D-146) |
| `cognitive_lab_philosophy.md` | فلسفة المختبر المعرفي (ليس Chat Tutor) |
| `routing_philosophy.md` | عقيدة التوجيه (intent gates محدودة النطاق) |
| `runtime-rules.md` | قواعد runtime الدائمة |
| `aesthetics_of_absence.md` | جماليات الغياب — مصدر القوانين L8→L12 (D-206). كان موجوداً وغير مفهرَس حتى D-209 |
| `agentic_runtime_doctrine.md` | **حالة** طبقات التنسيق التسع + الثلاث عشرة (D-146/D-209). القانون في `docs/architecture/AGENTIC_ORCHESTRATION_DOCTRINE.md` |
| `coverage-roadmap.md` | خارطة التغطية (D-182). كان موجوداً وغير مفهرَس حتى D-209 |

## 3) الحقائق المتخصصة (Truth files)

| الملف | النطاق |
|-------|--------|
| `architecture_truth.md` | حقيقة الحدود المعمارية |
| `observability_truth.md` | حقيقة الرصد (ما يعمل فعلاً مقابل الديكور) |
| `observability-topology.md` · `dashboard-inventory.md` · `path-map.md` | خرائط الرصد واللوحات والمسارات |
| `revenue_engine_truth.md` | **حالة** طبقات القيمة والإيراد (D-210→D-223) — 12 طبقة · 14 وحدة · 4 خطوط إيراد. القانون في `docs/VALUE_DOCTRINE.md` + `docs/REVENUE_ENGINE_SPEC.md`، وتحرسها `check_revenue_doctrine` |
| `cognitive_execution_truth.md` | **حالة** محرّك التنفيذ المعرفي (D-224/D-225) — ١٣ طبقة + ٤ آفاق سوق. القانون في `docs/architecture/COGNITIVE_EXECUTION_ENGINE.md`، وتحرسها `check_cognitive_execution` (بها **قفل D-187**: نموذجٌ لغوي موصولٌ بمُنفِّذ الصندوق ⇒ CI أحمر) |
| `secret_capture_truth.md` | **حالة** التقاط الأسرار (D-268) — ٧ وحدات + مصفوفة (سرّ × باب) كما قِيست قبل الإصلاح. القانون في `secret_capture_constitution.md`، وتحرسها `check_secret_capture_parity` |
| `ambient_identity_truth.md` | **حالة** الطبقة الخامسة (D-269) — ٩ وحدات. القانون في `ambient_identity_constitution.md` + `docs/architecture/AMBIENT_COGNITIVE_IDENTITY.md`، وتحرسها `check_ambient_identity` |
| `deep_tech_constitution_truth.md` | **حالة** دستور التقنية العميقة والعملة الصعبة (D-273) — ٧ خطوط إيراد (كلّها PROPOSED) · لا ACTIVE بلا دليلٍ حيٍّ (عقد/دفعة). القانون في `docs/DEEP_TECH_CONSTITUTION.md`، وتحرسها `check_deep_tech_constitution` |
| `agent_reliability_hard_currency_truth.md` | **حالة** دستور اعتمادية الوكلاء والعملة الصعبة (D-290) — `GATE_C = ABSENT` · H1–H7 بحالاتٍ مغلقة (كلّها بلا قياسٍ بعد) · حدود الأدلّة معلنة. القانون في `agent_reliability_hard_currency_constitution.md`، وتحرسها `check_agent_reliability_constitution` |
| `reference_backbone_truth.md` | **حالة** العمود الفقري المرجعي (D-274) — ١٥ مرجعاً مثبتاً، غير تشغيلي افتراضياً، لا حذف ولا استبدال صامت |
| `agent_context_truth.md` | **حالة** سياق الوكلاء الموحد (D-275) — سجل السلطة وتسلسل الإقلاع ومصفوفة ٦٢ مصدراً |
| `ci-gates.md` | فهرس بوّابات CI |
| `governance_weight_truth.md` | **حالة** ثِقَل الحوكمة (D-284) — كلفة كلٍّ من الدساتير الـ٢١ بالأسطر مقابل استشهاداتها الحيّة. الأرقام **مُولَّدة** بـ`scripts/research/measure_governance_weight.py`، و⛔ قلّةُ الجرّ ليست حكماً بانعدام القيمة (قانونٌ وقائيّ يعمل بمنعه لا بذكره) |
| `fx_doctrine_truth.md` | **حالة** عقيدة العملة الصعبة (D-273) — ٤ مسارات رسمية (تصدير رقمي + مزايا جبائية + قناة دفع بديلة + مضاعفة البنية التحتية) · ٤ محرمات (K1–K4) · ١٠ مراجع §99. القانون في `docs/FOREIGN_CURRENCY_DOCTRINE.md` |
| `naas_verification_truth.md` | **حالة** طبقة التحقّق (D-267) — ٨ وحدات + ٤ بوّابات قرار. القانون في `naas_verification_constitution.md` + `docs/architecture/NAAS_VERIFICATION_LAYER.md` + `docs/governance/GATE_STATE_MACHINE.md`، وتحرسها `check_naas_verification`. سجلّ الحالة الحيّ للبوّابات: `docs/governance/GATE_LEDGER.json` |
| `cognitive_twin_truth.md` | **حالة** التوأم الرقمي المعرفي (D-226/D-227) — ٨ محرّكات + ٣ آفاق. القانون في `docs/architecture/COGNITIVE_DIGITAL_TWIN.md`، وتحرسها `check_cognitive_twin` + `check_prerequisite_single_graph` |
| `code_quality_truth.md` | **حالة** أدوات جودة الكود الثلاث (D-235) — ماذا وجد Qodana وCodeScene وCodeRabbit، وحكمٌ لكل نتيجة حرجة (5 حقيقية · 8 كاذبة)، والحدود المُعلَنة، و**البرهان من سجلّ التشغيل** على أنّ للمِسنَن أسناناً. ⚠️ عدد Qodana **ليس درجة جودة**، و`.coderabbit.yaml` **PARTIAL** حتى تُبلِّغ مراجعةٌ إعداداً غير الافتراضي |
| `fragility-patterns.md` | أنماط الهشاشة المُوثَّقة (Patterns 1-4) |
| `architecture/websocket-topology.md` | طوبولوجيا WebSocket (سلسلة D-WS-*) |

## 4) ركائز المختبر المعرفي (Cognitive Lab pillars)

`cognitive_modeling.md` · `error_memory.md` · `dynamic_generation.md` ·
`interactive_object_ui.md` · `simulation_engine.md`

## 5) الـ Runbooks التشغيلية

| الملف | متى |
|-------|-----|
| `runbooks/e2e-codespaces.md` | التحقق الحيّ الكامل في Codespaces |
| `runbooks/realtime-recovery.md` | استعادة الزمن الحقيقي (WS) |
| `runbooks/supabase-bridge.md` | جسر SQL عبر HTTPS حين تُحجَب منافذ Postgres. كان موجوداً وغير مفهرَس حتى D-209 |

## 6) السجلات التاريخية المُجمَّدة (تُقرأ ولا تُحدَّث)

`diagnostic_2026_05_06.md` · `diagnostic_2026_05_06_rescue.md` ·
`observability-forensic-2026-05-07.md` · `langgraph_advanced_forensics.md` ·
`streaming_architecture_breakdown.md` · `architecture-audit-2026-05-21.md` ·
`content-audit-2026-05-21.md`

> التقارير التاريخية الأقدم (خارج `.memory/`) مؤرشفة في **`docs/archive/`** (D-156).

## 7) وثائق السلطة خارج `.memory/` (تُقرأ مع الذاكرة، لا تُنافسها)

| الملف | الدور | العلاقة بالذاكرة |
|-------|------|------------------|
| `CLAUDE.md` (الجذر) | 🏛️ الدستور التشغيلي — **القوانين الدائمة فقط** (D-188) | يشير إلى `.memory/`؛ لا يحمل حالات ولا سرداً مؤرَّخاً |
| `spec.md` (الجذر) | 📐 **مواصفة برنامج التبسيط API-first** (Phases 0→12) — الهدف المعماري | ليست دستوراً ثالثاً: §4 منها تُحيل صراحةً إلى الدستور القائم و§15 تُلزم بتحديث `.memory/` |
| `roadmap.md §6.5` | الدَّين الهندسي (D1→D7) + خارطة الوكيل (M0→M4) | داخل `.memory/` — المصدر الحيّ لترتيب التنفيذ |
| `docs/VALUE_DOCTRINE.md` | 💰 **قانون** القيمة (D-210): لماذا يدفع أحدٌ في سوقٍ مجّاني — الوظائف الأربع + اختبار الحذف + المحرَّمات التسعة | الحالة في `revenue_engine_truth.md` — ⛔ لا يحمل حالات |
| `docs/REVENUE_ENGINE_SPEC.md` | 💰 **قانون** محرّك الإيراد (D-210→D-223): ماذا يُكتب بالضبط — العقود والنماذج والبوّابات | نفس القاعدة: القانون بلا حالة |
| `docs/architecture/COGNITIVE_EXECUTION_ENGINE.md` | 🧠⚙️ **قانون** محرّك التنفيذ المعرفي (D-224) — الحقيقة تُنفَّذ واللغة تصفها؛ والحتمي قبل التوليد البرمجي | الحالة في `cognitive_execution_truth.md` — ⛔ لا يحمل حالات |
| `docs/architecture/COGNITIVE_DIGITAL_TWIN.md` | 👤🧠 **قانون** التوأم الرقمي المعرفي (D-226/D-227) — الطالب قصّة مستمرّة؛ رسمٌ واحد للعلاقة؛ وحدّ المصداقية | الحالة في `cognitive_twin_truth.md` — ⛔ لا يحمل حالات |
| `docs/governance/CONSTITUTION_REGISTRY.json` | 🔒 **السجلّ الدستوري** (D-266) — دستور → قسم §0.x → وثيقة قانون → وثيقة حالة → فوارض | **حالة** — التنفيذ يُشتَقّ بالمسح ولا يُكتب |
| `docs/specs/` | 📐 المواصفات الحيّة (Spec-First · D-265 §2) | العقد المقيس؛ سجلّ البرهان في `spec.md §17b` |
| `docs/DOCUMENTATION_INDEX.md` | خريطة السلطة الكاملة لـ`docs/` | مرجع مساند |

## القواعد الملزِمة

1. **قرار جديد** ⇒ إدخال في `decisions.md` + قسم CLAUDE.md §6.x + تحديث `roadmap.md` إن مسّ المراحل.
2. **كارثة جديدة** ⇒ إدخال ISS-### في `issues.md` مع الجذر والدليل الحيّ.
3. **تغيير قدرة تشغيلية** ⇒ تحديث `runtime_truth.md` + `python scripts/runtime_truth.py --update` في نفس الـ PR.
4. **ممنوع** ملف MD تشغيلي جديد خارج `.memory/` — والتقارير المنتهية تذهب إلى `docs/archive/`.
5. **(D-188) هذا الفهرس عقدٌ مفروض آلياً**: أقصى `D-###` في `decisions.md` وأقصى `ISS-###`
   في `issues.md` **يجب** أن يظهرا في الجدول أعلاه، والسجلّان مرتَّبان تنازلياً (الأحدث أولاً).
   تفرضه بوّابة `scripts/fitness/check_memory_coherence.py` ضمن workflow `doc-integrity`.
   السبب: بين 2026-05 و2026-07 انحرف هذا الفهرس عن الواقع بثلاثة قرارات وكارثتين بلا أن يلاحظه أحد.
