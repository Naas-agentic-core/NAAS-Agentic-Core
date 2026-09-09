# 📚 خريطة التوثيق الموحَّدة — Unified Documentation Map (D-156)

> **قاعدة السلطة الواحدة:** الحقيقة التشغيلية تعيش في مكانين فقط —
> **`CLAUDE.md`** (الدستور التشغيلي) و **`.memory/`** (الذاكرة المؤسسية، فهرسها `.memory/README.md`).
> كل ما في `docs/` **مرجع مساند** أو **أرشيف مُجمَّد**. عند أي تضارب: CLAUDE.md + `.memory/runtime_truth.md` يحسمان.

---

## 0) هرم السلطة (من يحسم ماذا؟)

| المستوى | المصدر | الدور |
|---------|--------|------|
| 🏛️ الدستور | `CLAUDE.md` | القوانين التشغيلية الدائمة + سجلّ العقائد §6.x (D-001→**D-287** · أحدثها **D-287** (الدفعةُ الآلية تسقط في بوّابةٍ لا تستطيع اجتيازها — حزمةُ القبول D-277 لا يكتبها بوت · والأرضيةُ التي لا ترتفع مع الشجرة تُمرِّر عودةً صامتة · 2026-08-28) · و**D-286** (الدفعة الآلية تُقاس مجموعةً لا فرادى — اثنتا عشرة دفعة Dependabot تحلّ فرادى ولا يحلّ مجموعُها · وثلاثةٌ من ستّة أعطاب لا يراها مُحلِّلٌ بل تشغيلٌ حيّ · 2026-08-24) · و**D-285** (أوّل قياسٍ على نظامٍ لم نكتبه — حارسٌ مفتوح المصدر يقبل قاعدةً لا يفرضها ويؤكّد قبولها · والآلية فئةُ يونيكود `Lo` المستبعَدة لا «ASCII» · ⛔ والقياس فنّد ادّعاءَين كِدتُ أرتكبهما · 2026-08-23) · و**D-284** («خفيف» يصير رقماً — جهاز الحوكمة ٧٠٪ من حجم المنتج · ١٣ من ٢١ دستوراً بلا استشهادٍ في كود المنتج · و⛔ قلّةُ الجرّ ليست حكماً بانعدام القيمة · 2026-08-23) · و**D-283** (المرجع بلا سلطةٍ ليس مرجعاً — ٤٩ من ٧٥ مصدراً `PENDING_CLASSIFICATION` وثلثاها ممنوعةٌ بنصّ القاعدة من أن تكون سلطة · مِسنَنة تقلّص-فقط ثنائية الاتجاه ببرهانٍ سلبي مُثبَت · 2026-08-23) · و**D-282** (قناة التمويل ليست خطّ إيراد — دخلٌ شخصي خارج دفاتر الكيان فلا يحكمه K3 ولا ينال إعفاءات المؤسّسة الناشئة · وتضارب أجل الترحيل يُعلَن ولا يُحسَم · 2026-08-23) · و**D-281** (البيئة تُغلِّف المُتحقِّق — مكافأةٌ حتمية تقرأ **المسار** لا المخرَج النهائي · الحلّ الإنجليزي بصفرٍ بنيويّاً · والمكتبة تُرجِع بياناتٍ ولا تطبع · 2026-08-23) · و**D-280** (أرشيف الحوادث أصلٌ قابل للبيع — ذخيرةُ ٥ أصنافٍ متمايزة الجذر مُشتَقّة من `issues.md` · قياسٌ حتمي بفارق 90 نقطة على أهدافٍ مرجعية · والبوّابات تبقى `ABSENT` لأنّ الآلة لا تعتمد نفسها · 2026-08-22) · و**D-273**: دستور التقنية العميقة والعملة الصعبة — سبع خطوط إيرادٍ مصرَّحةٍ حصراً · محرّمات 9 · إضافة لا حذف · و**D-272**: دستور مبادئ تصميم الأنظمة الوكيلية — قياسٌ محكَم من Google Research/DeepMind/MIT (arXiv:2512.08296) §0.24 · و**D-267**: دستور طبقة التحقّق — المُتحقِّق منتجٌ بحدٍّ مستقلّ والدليل قبل الادّعاء §0.19 · و**D-266**: دستور فرض الحوكمة — البرهان الثلاثي يمتدّ من الكود إلى الفارض §0.18 · و**D-265**: دستور حوكمة Spec Kit — طبقة ضبط تنفيذ فوق الدستورية L1–L10 · و**D-264**: دستور المخطط الدراسي التكيفي Adaptive AI Study Planner L1–L10 · وD-263: دستور المحرك التربوي — العقل التربوي كـmoat + القوانين العشرة الصارمة L1–L10، وD-262: قشرة تفويض `services/overmind/graph/main.py` + شرائح `graph/graph_support/`). **لا يحمل حالات ولا سرداً مؤرَّخاً** (D-188) · **الإضافة لا الحذف:** كل دستورٍ يعلو السابق في نطاقه دون إلغاء قانونٍ قائم |
| 📐 مواصفة البرنامج | [`../spec.md`](../spec.md) | برنامج التبسيط API-first (Phases 0→12) — **الهدف** المعماري لا الحقيقة الجارية. ليست دستوراً ثالثاً: §4 تُحيل إلى الدستور القائم |
| 🧠 الذاكرة | `.memory/` → [`README.md`](../.memory/README.md) | roadmap · decisions · issues · runtime_truth · pedagogical_os · pedagogy_engine_constitution · adaptive_study_planner_constitution · spec_kit_governance_constitution · governance_enforcement_constitution · naas_verification_constitution · secret_capture_constitution · ambient_identity_constitution |
| ⚖️ الدستور المعماري | [`architecture/MICROSERVICES_CONSTITUTION.md`](architecture/MICROSERVICES_CONSTITUTION.md) + [`ARCH_MICROSERVICES_CONSTITUTION.md`](ARCH_MICROSERVICES_CONSTITUTION.md) | حدود الخدمات |
| 📖 قواعد الوكلاء | [`../AGENTS.md`](../AGENTS.md) | قواعد التطوير + مشغّلات `ai_skills/` |
| 📄 مراجع مساندة | `docs/` (هذا الفهرس) | أدلة، عقود، ADRs |
| 🗄️ أرشيف مُجمَّد | [`archive/`](archive/README.md) | تقارير منتهية — لا تُستشهد كحقيقة |

---

## 1) البداية

| ملف | الدور |
|-----|------|
| [`START_HERE.md`](START_HERE.md) | نقطة البداية الوحيدة للمطورين الجدد — المسار التشغيلي الحي |
| [`DOCUMENTATION_CONTRACT.md`](DOCUMENTATION_CONTRACT.md) · [`DOCUMENTATION_MANIFEST.json`](DOCUMENTATION_MANIFEST.json) | عقد التوثيق الحي وبيانه الآلي؛ يحدد الوثائق الحية ويفحص كل Markdown غير مؤرشف؛ الفشل في بوابته يمنع الدمج |
| [`ARCHITECTURE.md`](ARCHITECTURE.md) | نظرة معمارية مبسطة (التفصيل الحيّ: CLAUDE.md §3) |
| [`REPOSITORY_MAP.md`](REPOSITORY_MAP.md) | خريطة المستودع |
| [`guides/BEGINNER_GUIDE.md`](guides/BEGINNER_GUIDE.md) · [`guides/NEWCOMER_CODEBASE_MAP.md`](guides/NEWCOMER_CODEBASE_MAP.md) | أدلة المبتدئين |
| [`guides/CODESPACES_TEST_GUIDE.md`](guides/CODESPACES_TEST_GUIDE.md) | العمل على Codespaces |

## 2) المعمارية والعقود

| ملف | الدور |
|-----|------|
| [`architecture/MICROSERVICES_CONSTITUTION.md`](architecture/MICROSERVICES_CONSTITUTION.md) | ⚖️ الدستور المعماري (عربي) |
| [`architecture/PRINCIPLES.md`](architecture/PRINCIPLES.md) | المبادئ المعمارية |
| [`adr/`](adr/) | سجلّات ADR (القرارات الحيّة في `.memory/decisions.md`)، ومنها [`ADR-016-live-documentation-contract.md`](adr/ADR-016-live-documentation-contract.md) لعقد التوثيق |
| [`architecture/`](architecture/) (runbooks: `MASTER_CUTOVER_RUNBOOK` · `PR1..PR5` · `LEGACY_*`) | كتيّبات هجرة الـ strangler-fig |
| [`architecture/ENGINEERING_DOCTRINE.md`](architecture/ENGINEERING_DOCTRINE.md) | ⚖️ عقيدة الهندسة — البحر الكامل مربوطاً بفارضٍ آلي؛ كل قانون يُسمّي بوّابته (محروسة: بوّابة غير موجودة ⇒ CI أحمر) |
| [`architecture/CS_KNOWLEDGE_MAP.md`](architecture/CS_KNOWLEDGE_MAP.md) | 🗺️ خريطة علوم الحاسوب ↔ المشروع — عشرون مجالاً بحالةٍ ودليلٍ ملفّي، تحرسها `check_cs_knowledge_map` (D-207) |
| [`architecture/AGENTIC_ORCHESTRATION_DOCTRINE.md`](architecture/AGENTIC_ORCHESTRATION_DOCTRINE.md) | 🎼 **عقيدة تنسيق الوكلاء (D-209)** — القانون لطبقات التنسيق التسع (Knowledge→…→Humans)، كلٌّ بفارضه. **الحالة** في [`../.memory/agentic_runtime_doctrine.md`](../.memory/agentic_runtime_doctrine.md)؛ تحرسهما `check_agentic_orchestration` (⛔ القانون لا يحمل حالة، ولا سُلَّم ثانٍ) |
| [`VALUE_DOCTRINE.md`](VALUE_DOCTRINE.md) | 💰 **قانون القيمة (D-210)** — لماذا يدفع أحدٌ في سوقٍ كلّ شيء فيه مجّاني: الوظائف الأربع + اختبار الحذف + الطبقات الاثنتا عشرة + **المحرَّمات التسعة** + 32 مرجعاً. **الحالة** في [`../.memory/revenue_engine_truth.md`](../.memory/revenue_engine_truth.md) |
| [`REVENUE_ENGINE_SPEC.md`](REVENUE_ENGINE_SPEC.md) | 💰 **قانون محرّك الإيراد (D-210→D-223)** — العقود والنماذج الرياضية والبوّابات لأربع عشرة وحدة. تحرسهما `check_revenue_doctrine` (⛔ القانون لا يحمل حالة، ووحدةٌ `ABSENT` لها كودٌ ⇒ CI أحمر) |
| [`architecture/COGNITIVE_EXECUTION_ENGINE.md`](architecture/COGNITIVE_EXECUTION_ENGINE.md) | 🧠⚙️ **قانون محرّك التنفيذ المعرفي (D-224/D-225)** — ١٣ طبقة من الفهم اللغوي إلى المعرفة المُتحقَّقة + تسلسل السوق. **الحالة** في [`../.memory/cognitive_execution_truth.md`](../.memory/cognitive_execution_truth.md)؛ تحرسهما `check_cognitive_execution` (⛔ فيها **قفل D-187**: توصيل نموذجٍ لغوي بمُنفِّذ الصندوق ⇒ CI أحمر) |
| [`architecture/COGNITIVE_DIGITAL_TWIN.md`](architecture/COGNITIVE_DIGITAL_TWIN.md) | 👤🧠 **قانون التوأم الرقمي المعرفي (D-226/D-227)** — رسم المنهاج · تتبّع المعرفة · التدخّل على الجذر · التكرار المتباعد + **حدّ المصداقية**. **الحالة** في [`../.memory/cognitive_twin_truth.md`](../.memory/cognitive_twin_truth.md) |
| [`API_FIRST_ARCHITECTURE.md`](API_FIRST_ARCHITECTURE.md) | عقيدة API-First |
| [`architecture/EXTENSION_SEAMS.md`](architecture/EXTENSION_SEAMS.md) | مقاعد التوسّع (Kafka/VectorDB/RAG/Skill-flags) + الرؤية الثورية (D-173) + مقعدا `deepseek-harness` §10 و`honcho-ai` §11 (D-271) |
| [`architecture/AMBIENT_COGNITIVE_IDENTITY.md`](architecture/AMBIENT_COGNITIVE_IDENTITY.md) | 🧠🔌 **مواصفة الطبقة الخامسة (D-271)** — نمذجةُ مستخدمٍ لطرفٍ ثالث بحدٍّ معماري: تُقرأ ولا تحكم، و⛔ لا يعبرها `content`. **القانون** في [`../.memory/ambient_identity_constitution.md`](../.memory/ambient_identity_constitution.md) و**الحالة** في [`../.memory/ambient_identity_truth.md`](../.memory/ambient_identity_truth.md)؛ تحرسها `check_ambient_identity` |
| [`adr/ADR-010-deepseek-harness-adoption.md`](adr/ADR-010-deepseek-harness-adoption.md) | 📌 **قرار تبنّي `deepseek-harness` (D-271)** — مقعدٌ بصفر كود: أسباب الرفض الأربعة وشرط إعادة الفتح الثلاثي (⛔ قفل D-187) |
| [`adr/ADR-006-polyglot-language-adoption.md`](adr/ADR-006-polyglot-language-adoption.md) | قرار تبنّي اللغات متعدّدة — **الحدّ هو العقد لا اللغة**؛ TypeScript مُتبنّىً، والتسع الباقيات مقاعد بشرط تبنٍّ (D-185) |
| [`contracts/`](contracts/) | عقود الـ API وقواعد الإصدار |
| [`OVERMIND_ARCHITECTURE.md`](OVERMIND_ARCHITECTURE.md) · [`architecture_map.md`](architecture_map.md) | خرائط الـ orchestrator |
| [`TYPE_SYSTEM.md`](TYPE_SYSTEM.md) · [`config/SETTINGS_LAYER.md`](config/SETTINGS_LAYER.md) · [`db/SESSION_FACTORY.md`](db/SESSION_FACTORY.md) · [`core/DEPENDENCY_LAYER.md`](core/DEPENDENCY_LAYER.md) · [`gateways/AI_GATEWAY.md`](gateways/AI_GATEWAY.md) | مراجع الطبقات |

## 3) التشغيل والنشر

| ملف | الدور |
|-----|------|
| [`DEPLOYMENT_GUIDE.md`](DEPLOYMENT_GUIDE.md) · [`MICROSERVICES_DEPLOYMENT_GUIDE.md`](MICROSERVICES_DEPLOYMENT_GUIDE.md) · [`MICROSERVICES_PLATFORM.md`](MICROSERVICES_PLATFORM.md) | النشر والتشغيل |
| [`WEBSOCKET_INFRASTRUCTURE.md`](WEBSOCKET_INFRASTRUCTURE.md) | بنية WebSocket + Troubleshooting (سلسلة D-WS-*) |
| [`migration/`](migration/) | كتيّبات خطوات الهجرة |
| [`advanced_knowledge_ingestion.md`](advanced_knowledge_ingestion.md) | خط إدخال المعرفة (RAG) |
| `../.memory/runbooks/` | ✳️ runbooks الحيّة (E2E Codespaces · Realtime recovery) |

## 4) الأمن والهوية والجودة

| ملف | الدور |
|-----|------|
| [`architecture/AUTHENTICATION_DOCTRINE.md`](architecture/AUTHENTICATION_DOCTRINE.md) | **قانون المصادقة** (D-236) — بابٌ واحد · عقد أخطاء واحد · هوية عميل واحدة · أنواع رموز مُصرَّحة. الحالة الحيّة في [`../.memory/auth_runtime_truth.md`](../.memory/auth_runtime_truth.md)، وإجراء التحقّق في [`../.memory/runbooks/login_e2e_verification.md`](../.memory/runbooks/login_e2e_verification.md) |
| [`iam_architecture.md`](iam_architecture.md) · [`permission_matrix.md`](permission_matrix.md) · [`policy_gate.md`](policy_gate.md) · [`roles_and_boundaries.md`](roles_and_boundaries.md) · [`audit_and_privacy.md`](audit_and_privacy.md) · [`customer_chat_access.md`](customer_chat_access.md) | الهوية والصلاحيات |
| [`quality/standards.md`](quality/standards.md) · [`quality/testing.md`](quality/testing.md) · [`guides/TESTING_GUIDE.md`](guides/TESTING_GUIDE.md) | الجودة والاختبار |
| [`governance/CONSTITUTION_REGISTRY.json`](governance/CONSTITUTION_REGISTRY.json) | 🔒 **السجلّ الدستوري** (D-266) — المصدر القانوني الوحيد الذي يربط كل دستور بوثيقة قانونه ووثيقة حالته وفوارضه. تحرسه `check_governance_registry.py`: بوّابةٌ على القرص لا يشغّلها شيء ⇒ CI أحمر |
| [`specs/`](specs/README.md) | 📐 **المواصفات الحيّة** (D-265 §2 · أُنشئت في D-266) — دورة Spec-First: خطة → تصميم → مهام → مواصفة → تنفيذ → برهان. كان الموطن مُعلَناً في الدستور وغير موجودٍ على القرص |
| [`governance/REPOSITORY_GOVERNANCE_MODEL.md`](governance/REPOSITORY_GOVERNANCE_MODEL.md) | حوكمة المستودع |
| [`governance/NO_BYPASS_CONTROL_PLANE.md`](governance/NO_BYPASS_CONTROL_PLANE.md) · [`../.github/branch-protection-policy.json`](../.github/branch-protection-policy.json) | نموذج التحكم ضد تجاوز التوثيق؛ يربط البوابات الداخلية بحماية `main` الحية |
| [`governance/REFERENCE_BACKBONE.md`](governance/REFERENCE_BACKBONE.md) · [`governance/REFERENCE_BACKBONE.json`](governance/REFERENCE_BACKBONE.json) | 🔒 العمود الفقري المرجعي المثبت؛ يربط خرائط التعلم والخوارزميات وتصميم الأنظمة والحرفية والوكلاء ببوابة `check_reference_backbone` وADR-013 |
| [`governance/SOURCE_ADOPTION_MATRIX.md`](governance/SOURCE_ADOPTION_MATRIX.md) · [`governance/SOURCE_ADOPTION_MATRIX.json`](governance/SOURCE_ADOPTION_MATRIX.json) | 🔒 مصفوفة كل مستودعات GitHub المكتشفة؛ لكل مصدر حالة وغرض وتطبيق وفارض ومالك، وتحرسها `check_source_adoption_matrix` |
| [`research/ALL_GITHUB_SOURCES_INVENTORY.md`](research/ALL_GITHUB_SOURCES_INVENTORY.md) · [`research/ALL_GITHUB_SOURCES_INVENTORY.json`](research/ALL_GITHUB_SOURCES_INVENTORY.json) | جرد قابل لإعادة التشغيل لكل الروابط الفريدة؛ لا يسمح بإخفاء مصدر داخل وثيقة أو تبعية |
| [`research/EVIDENCE_CATALOG.json`](research/EVIDENCE_CATALOG.json) | سجل الأبحاث والمعايير والمقررات الجامعية التي تثبت مبادئ القبول |
| [`research/UNIVERSITY_CURRICULUM_CATALOG.md`](research/UNIVERSITY_CURRICULUM_CATALOG.md) · [`research/UNIVERSITY_CURRICULUM_CATALOG.json`](research/UNIVERSITY_CURRICULUM_CATALOG.json) | **الكتالوج الكامل المستخرج** من صفحة Harvard CS الرسمية؛ كل مقرر ظاهر، مع تمييز حدود اللقطة وعدم ادعاء التاريخ الكامل |
| [`research/CURRICULUM_APPLICATION_MATRIX.md`](research/CURRICULUM_APPLICATION_MATRIX.md) · [`research/CURRICULUM_APPLICATION_MATRIX.json`](research/CURRICULUM_APPLICATION_MATRIX.json) | 🔒 بطاقة تطبيق لكل مقرر، ومصفوفة تحميل حسب نوع التغيير؛ لا مقرر مخفي أو غير مصنف |
| [`adr/ADR-014-full-curriculum-gate.md`](adr/ADR-014-full-curriculum-gate.md) | قرار جعل الكتالوج الكامل مرئياً وإلزامياً في حزمة القبول مع تطبيق انتقائي موثق لا ادعاء قراءة وهمي |
| [`guides/AGENT_CODE_CHANGE_PROTOCOL.md`](guides/AGENT_CODE_CHANGE_PROTOCOL.md) | البروتوكول التشغيلي الموحد لـClaude Code وCodex وأي وكيل: سياق → مصادر → كل المقررات → التطبيق → البرهان → القيمة |
| [`architecture/CODE_ACCEPTANCE_CONSTITUTION.md`](architecture/CODE_ACCEPTANCE_CONSTITUTION.md) · [`changes/CURRENT_CODE_ACCEPTANCE_PACKET.json`](changes/CURRENT_CODE_ACCEPTANCE_PACKET.json) | 🔒 لا إضافة كود بلا معايير ومصادر ودليل وتطبيق محلي وإثبات إنتاجي وتتبع تجاري وفحص حذف صفري؛ تحرسها `check_code_acceptance` |
| [`architecture/DUAL_TRACK_PRODUCT_SYSTEM.md`](architecture/DUAL_TRACK_PRODUCT_SYSTEM.md) · [`commercial/FOREIGN_CURRENCY_OPERATING_SYSTEM.md`](commercial/FOREIGN_CURRENCY_OPERATING_SYSTEM.md) · [`governance/DUAL_TRACK_ALIGNMENT.json`](governance/DUAL_TRACK_ALIGNMENT.json) | مساران متكاملان: هندسة المنتج وإنتاج/تصدير القيمة؛ لا إصدار تقني بلا قابلية إنتاج، ولا عرض تجاري بلا قدرة مثبتة |
| [`adr/ADR-015-dual-track-product-system.md`](adr/ADR-015-dual-track-product-system.md) | قرار الفصل التشغيلي بين مسار الهندسة ومسار الإنتاج مع بوابة التقاء إلزامية |
| [`adr/ADR-013-reference-backbone.md`](adr/ADR-013-reference-backbone.md) | قرار جعل المجموعة المرجعية إلزامية، مثبتة، إضافية، وغير تشغيلية بلا قرار جديد |
| [`diagnostics/CUTOVER_SCOREBOARD.md`](diagnostics/CUTOVER_SCOREBOARD.md) | 🤖 لوحة القطع (مولَّدة آلياً — لا تُحرَّر يدوياً) |

## 5) مهارات الوكلاء (AI Skills)

[`ai_skills/`](ai_skills/) — مشغّلاتها مُعرَّفة في [`../AGENTS.md`](../AGENTS.md):
`bac-exercise-explanation` · `langgraph-agent-patterns` · `microservices-live-verification` ·
`fastapi-templates` · `database-schema-designer` · `python-performance-optimization` ·
`vercel-react-best-practices` · `web-design-guidelines` · `crafting-effective-readmes`

## 6) خارج النطاق الهندسي

| مجلد | المحتوى |
|------|---------|
| [`grant-program/`](grant-program/README.md) | 🎓 مواد برنامج المنحة (Theory of Change، الأثر، القوالب، `application/`، `toolkit/`) |
| [`archive/`](archive/README.md) | 🗄️ الأرشيف التاريخي المُجمَّد (108+ تقرير مؤرَّخ — D-156) |

---

## قواعد الإضافة (ملزِمة — تحرسها بوابة `doc-integrity`)

العقد التفصيلي لهذه القواعد هو [`DOCUMENTATION_CONTRACT.md`](DOCUMENTATION_CONTRACT.md)، ونطاق الوثائق الحية القابلة للفحص هو [`DOCUMENTATION_MANIFEST.json`](DOCUMENTATION_MANIFEST.json). أي ملف تشغيلي جديد يحتاج إدخالًا صريحًا في البيان، وإلا يفشل `check_documentation_contract.py`.

1. معلومة تشغيلية قصيرة ⇒ `.memory/*.md` — **لا ملف MD جديد في `docs/`**.
2. قرار معماري ⇒ `.memory/decisions.md` + قسم CLAUDE.md §6.x.
3. تقرير مؤرَّخ/تشخيص منتهٍ ⇒ `docs/archive/<فئة>/` (البوّابة تفشل على `PHASE_*`/`ULTRA_*` خارج الأرشيف).
4. أي ملف جديد هنا ⇒ سطر في هذا الفهرس في نفس الـ PR.
