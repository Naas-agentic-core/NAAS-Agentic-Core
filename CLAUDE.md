# CogniForge — Claude Code Context

> **The system is not a Chat Tutor. It is a Cognitive Lab / Thinking Engine that models, tests, and improves student reasoning.**
> Chat is an assistive interface only. The platform core is: Interactive Object UI, Cognitive Modeling, Error Memory, Adaptive Generation, and Simulation.
> **AI tutor for Algerian students** | FastAPI 8000 + Next.js 5000 + LangGraph 1.1.10
> Arabic / French / Darija | BAC preparation platform

---

## 0. Core System Doctrine: The Cognitive Lab

**Single writer. Single terminal frame. No silent failure.** These are operational laws, not aspirations.

The system must preserve the following principles permanently. Every future agent must inherit and obey these rules automatically:

- **Platform is a Pedagogical Engine, NOT an Answer Engine**: Long exercises or educational questions must trigger the pedagogical tutoring flow. The platform must first diagnose the initial cognitive gap, ask one short diagnostic question, and provide only the next missing hint. It must **never** default to dumping the full solution.
- **Strict Intent Routing Safeguards**: Analytical or educational inputs must strictly route to the `educational` pipeline (which engages the Socratic Tutor / Synthesizer). They must **never** fall back to `general_knowledge`.
- **Cognitive Lab Authority**: The platform is an engine that makes human reasoning observable, diagnosable, testable, and continuously improvable. Any future feature that improves chat while weakening the core pillars (Interactive Object UI, Cognitive Modeling, Error Memory, Adaptive Generation, Simulation) is architecturally incorrect.
- **Runtime truth over synthetic certainty**: Code presence ≠ runtime usage. A capability is real ONLY when proven by import + call chain + runtime evidence. Anything missing one of those three is treated as DORMANT or ZOMBIE until proven otherwise.
- **Instrumentation before visualization**: Dashboards must never outpace instrumentation.
- **Observability is for diagnosis, not decoration**: Every visualization must support debugging.
- **Unknown is better than fake certainty**: Dormant systems must not be presented as healthy.
- **Metrics require runtime evidence**: Every metric must have a semantic contract.
- **Traces and metrics are separate disciplines**: Treat them as such in architecture and implementation.
- **Forbidden anti-patterns**: High-cardinality labels are dangerous and strictly forbidden. Dual-writes to the database are forbidden.
- **CI truth-gate philosophy**: The project enforces architectural capability truths via static analysis in CI (`scripts/runtime_truth.py --check`), which strictly validates the codebase against `.runtime/truth_table.lock.json`. Do not bypass or break this gate.
- **Repository memory coherence**: Repository memory (`.memory/` and `CLAUDE.md`) must remain coherent, curated, and durable over time. It must reflect the actual runtime reality, not aspirational architecture.
- **ACTIVE (no-op) is not ACTIVE**: A component that is imported and called but produces no observable output due to missing configuration (e.g., `otel_setup.py` without `OTEL_EXPORTER_OTLP_ENDPOINT`) is not truly ACTIVE at runtime. Mark it `ACTIVE (no-op without ENV_VAR)` in the truth table.
- **No DATABASE_URL = no FastAPI**: The application cannot start without `DATABASE_URL` or `APP_DATABASE_URL`. A running uvicorn process is not proof of a healthy server — check `/health` response, not just the process list.
- **Process env wins over `.env` at module import time**: `app/core/settings/base.py:23` reads `os.environ.get("APP_DATABASE_URL")` before pydantic-settings reads `.env`. Secrets must be exported into the process environment before uvicorn starts, not just written to `.env`.
- **Stale state files are a finding**: `.devcontainer/state/app_healthy` from a previous run does NOT mean the current uvicorn is healthy. Always re-probe the live `/health` endpoint — never trust a state file timestamp.
- **Lifespan warmup must be timeout-guarded**: Any `ainvoke()` in an ASGI `lifespan()` context must use `asyncio.wait_for(..., timeout=30.0)`. Unbounded awaits block ASGI startup indefinitely, creating a "process alive, service dead" partial state.
- **Degraded ≠ Dead**: A microservice that passes `/health` but has a failed graph warmup is DEGRADED, not healthy. The `/health` endpoint must expose `startup_state` so operators can diagnose without restarting.
- **Zombie metrics are worse than no metrics**: A dashboard panel that always shows zero is indistinguishable from "system not running". Every dashboard metric must have a verified emitter in the application source (D-016).
- **Lock file staleness is a finding**: `.runtime/truth_table.lock.json` records the branch and timestamp it was generated on. Always check `generated_at_utc` before trusting it. A stale lock file means the CI drift gate may pass on false grounds.
- **PRIMARY model invariants (D-067 — 2026-05-17)**: ⛔ `nvidia/nemotron-3-nano-30b-a3b:free` MUST NEVER be PRIMARY. Live benchmark proved it returns `content=None` (English reasoning only) with system prompts > 1500 chars — caused real-user "pepepe aaaa" garbage catastrophe (ISS-079). ⛔ `openai/gpt-oss-20b:free` — verified in D-167 but **no longer served** (free tier publishes `"endpoints": []`): one provider error collapsed every student reply into one canned apology (ISS-200). PRIMARY is now `google/gemma-4-31b-it:free`, single-sourced in `shared/ai_models/model_chain.py`, and **capability is not servability** — servability is asked of the live registry by `scripts/verify_model_registry_live.py` (`make model-check`, run in `live-e2e.yml`), never of a comment nor of a test-only override that masks the very breakage it should measure (D-288 — 2026-09-09).
- **System prompt sanity (D-067)**: System prompts > 1500 chars are FORBIDDEN — they trigger reasoning-mode in free OpenRouter models. Box-drawing chars (U+2500–U+257F) like `━━━` are FORBIDDEN in prompts — they confuse tokenizers and cause degenerate output. Keep prompts < 1000 chars, use simple punctuation (`---`, `##`).
- **No reasoning→content leak (D-067)**: Gateway MUST NEVER redirect `delta.reasoning` to `delta.content`. The reverse of ISS-069 caused English thinking text ("We need to respond as a brilliant Algerian professor...") to be displayed to students as Arabic answers. If `content=None`, let the fallback chain trigger.
- **Greeting fastpath is mandatory (D-067)**: Every chat entry point (monolith `local_graph.py`, orchestrator's `ChatFallbackNode`, `chat_with_agent` preempt) MUST check `_greeting_fastpath_response` / `GreetingSkill` BEFORE calling LLM. Without this, free models return etymology for "السلام عليكم" (verified live ISS-079).
- **Stateful Pedagogical Progression is Mandatory**: The AI tutor must never rely purely on stateless chat history or naive string inference for its decisions. `TutorState` is the single source of truth for the student's pedagogical journey (e.g., `learning_stage`, `dead_ends`, `interventions_used`). The Monolith uses `PedagogicalPolicyEngine` linked to this state to strictly forbid loops and intent hijacking.
- **E-TAALEEM Zero Cognitive Overload (D-074 — Protocol V6.0)**: The platform serves 800,000+ Algerian Baccalaureate students. Abstract math symbols (`A`, `B|A`, `Ā`, `B̄`) are **permanently banned** from every generative-UI node label. This is an immutable pedagogical law, not a styling preference.
- **Abstraction Ban — Hybrid Extraction (D-074)**: Every generative-UI component MUST produce concrete, human-readable labels via the Hybrid Extraction Model — deterministic entity extraction first (`OrchestratorClient._extract_concrete_events`), LLM enrichment only when no concrete entity is found (`_enrich_tree_labels_with_llm`, timeout-guarded, A/B output rejected), and even the final fallback is concrete (`"الحدث الأول"`, never `"A"`). The orchestrator `_normalize_ui_component_event` + frontend `GenerativeUIRenderer` whitelist are the only render paths.
- **BKT is the foundational cognitive layer (D-074)**: Bayesian Knowledge Tracing (`app/services/skills/bkt_engine.py:BKTEngine`) is the cognitive substrate for ALL future autonomous pedagogical skills (adaptive difficulty, hints, learning paths). Any adaptive capability MUST build on `student_mastery_probability`, never re-invent mastery tracking. Governed by `BKT_COGNITIVE_DOCTRINE` (versioned in `app/services/skills/doctrine.py`, CI-validated by `scripts/fitness/check_skills_doctrine.py`).
- **BKT is append-only (D-074)**: `student_bkt_analytics` is strictly an **append-only interaction log** for time-series analytics. Each evaluation inserts ONE new row; prior mastery is read from the most-recent row per `(user_id, concept_id)`. No in-place updates, no upserts — the full temporal sequence is preserved. Mandatory schema: `concept_id`, `cognitive_load_estimate` (low/medium/high), `student_mastery_probability ∈ [0,1]`, `interaction_timestamp`.
- **BKT never breaks chat (D-074)**: Every BKT evaluation/persist/emit call (`customer_chat._evaluate_and_emit_bkt`) is isolated in `try/except` with its own DB session. A BKT failure is logged and swallowed — it must NEVER abort a student's chat turn.
- **Dual-Mode Routing is immutable (D-085 — 2026-05-23 · معدَّل بـD-116)**: `_build_calculated_ui` stamps every UI event with `routing_mode: "MODE_A" | "MODE_B"`. MODE_A = direct question, MODE_B = confusion («لم أفهم», «مفهمتش», «كيفاش», «اشرح لي»). The routing decision is made **inside** `_build_calculated_ui` — never re-computed in `chat_with_agent`; `routing_mode` is consumed downstream as `ctx.is_mode_b` (`turn_preempts_delivery.py`) to steer the fallback chain, and `_effective_question` in MODE_B prepends the Socratic instruction. ⚠️ **شرط `terminate_pipeline=False` لـMODE_B ألغاه D-116 (2026-06-16 · ISS-116)**: كل مكوّنات الاحتمالات تُنهي المسار (`True` في البُناة الأربعة) لأن سرد الـLLM بعد البصري كان مصدر غارباج حيّ. المُلغى لا يُعاد بلا ADR — وكان الدستور يحمل القاعدتين معاً حتى 2026-07-31 (D-192).
- **التمرين قيد النقاش مصدره واحد، وأوّلُه نصّ الطالب (D-191 — 2026-07-31 · ISS-140 د/د-2)**: `app/services/skills/exercise_context.py:ExerciseContextSkill` هو **الحاسم الوحيد**؛ ترتيبه: نصّ الطالب الحاضر ⇒ تمرينه في التاريخ (رسائل `user` فقط، D-102) ⇒ التمرين المرجعي **بتصريح منطوق** ⇒ `None`. الحرفية `CANONICAL_EXERCISE_QUERY` لها **موطن واحد** (كانت مكرَّرة في ٧ مواضع تُغذّي ١٢ موضع استدعاء، و`_load_canonical_combinations` تستقبل `question` و**ترميه** — فتعلّم الطالبُ مسألةً ليست مسألته). ⛔ **لا يُطبَع رقمٌ ولا كيانٌ لم يذكره الطالب دون تصريح** — ويشمل ذلك النصوص التعليمية الثابتة (`semantic_property_skill` · `understanding_state_skill` كانت تحمل تركيبة التمرين المرجعي حرفياً). السقوط إلى المرجعي يتطلّب **إشارة احتمالية موجبة**؛ «غياب موضوعٍ آخر» ليس دليلاً (ISS-140 أ). تحرسه `check_exercise_context_single_source` بدَينٍ مُجمَّد **فارغ**.
- **الكيانات المهيكلة نوعٌ لا شعار (D-191)**: `ParsedEntities`/`ParsedEntityComponent` (`probability_models.py`) هي عملة التركيبة، تُنتَج مرّةً واحدة (`extract_parsed_entities` من نصّ الطالب · `from_mapping` من بيانات مهيكلة مُلتزَمة في `knowledge_base/entities/*.json` — نفس شكل عمود `parsed_entities`) وتُستهلَك في كل مكان. **عمود `parsed_entities` في قاعدة البيانات ما زال بلا قارئ حيّ** ويُوثَّق كذلك (`.memory/runtime_truth.md`) — لا يُدَّعى وصلُه.
- **الكمّامة يبرّرها المكوّن المُسلَّم (D-191 · ISS-140 ج)**: `_stage_calculated_ui` يقرأ **حكم** `_normalize_stream_event`؛ سقوط الحمولة إلى `noop` (props > 16KB أو رفض تحقّق) ⇒ **لا `companion_text` ولا إطار نهائي**، وسجلّ `ui_component_dropped_promise_suppressed`، والمسار يبقى حيّاً. وعدٌ بشرحٍ لا يصل أسوأ من خطأ صريح (§0).
- **تعريف المفهوم واحد (D-193 — 2026-08-01)**: `shared/curriculum/registry.py` هو المصدر القانوني الوحيد لكل `concept_id` يُخزَّن أو يُصنَّف أو يُعرَض (٣٧ مفهوماً · رياضيات + فيزياء + علوم الطبيعة). كانت ثلاثة تعاريف متنافرة لا تتّفق أيّ اثنين (BKT · learning_path · memory_agent بمُعرَّفات مختلفة)، ونتيجتها أنّ أسئلة الفيزياء والعلوم كلّها تسقط إلى `"general"` — أي أنّ الطبقة المعرفية لا تقيس شيئاً في مادة معاملها **٦**. ⛔ **المُعرَّفات لا تُغيَّر** (مُخزَّنة في `student_bkt_analytics`)؛ الصيغ الأخرى `aliases`. `classify` تُرجِع `None` لا `"general"`. أداة التعريف تكسر العلامات المركّبة (ISS-109/112/114) فتُجرَّب صورة بلا أدوات تعريف؛ والعلامة القصيرة تختبئ داخل كلمة أخرى («شعاع» خطفت «الإشعاعي») فيحرسها اختبار بنيوي؛ والأولوية تُصرَّح بـ`specificity` لا تُصادَف.
- **القياس يصير جدولاً، والدعمُ يُقصِّر الفاصل (D-194 — 2026-08-01)**: `shared/scheduling/fsrs.py` (FSRS-5 حتمي، يرفع `SchedulingError` لا صفراً مضلِّلاً) + `ReviewSchedulerSkill` + `student_review_schedule` **مُلحَق-فقط**. إجابةٌ صحيحة بسقالةٍ كاملة ⇒ `HARD` لا `GOOD`، و`EASY` تتطلّب `support_level ≥ 5` **و** `durable ≥ 0.85` معاً — وإلّا أتمتنا وَهْم الطلاقة بدل محاربته (§0.6). غياب `support_level` = دعمٌ ثقيل (الغياب ليس دليل استقلال)، و`correctness_signal="unknown"` ⇒ **لا صفّ**. الجدولة معزولة ولا تكسر دور طالب.
- **الوليّ يرى ولا يقرأ الحلّ (D-195/D-196 — 2026-08-01)**: الربط **برضا الطالب بنيوياً** (`guardian_user_id` يبدأ `NULL`؛ لا مسار يربط حساب قاصر بلا فعلٍ منه)، ورمزٌ عشوائي تعمويّاً يُستبدَل مرّة، و`is_linked` بوّابة كلّ قراءة (مُعرَّف المسار ليس تفويضاً)، وغير المرتبط **404 لا 403**. ⛔ **تقرير الوليّ لا يستعلم عن `content` إطلاقاً** — حمايةٌ بنيوية لا مُرشِّح: مقتطفٌ واحد يجعله باباً خلفياً إلى الحلّ الممنوع (D-113). وفجوة الوهم تُعرَض له لا تُخفى. والمواظبة تُحسَب بتقويم الطالب (`Africa/Algiers`) لا UTC — ٠٠:٣٠ محلّياً هي اليوم السابق في UTC، فالحساب على UTC يكسر مواظبة كلّ من يدرس ليلاً.
- **الأرقام تعترف بجهلها (D-197/D-198 — 2026-08-01)**: أسماء أحداث المنتج قائمة مغلقة (`shared/analytics/events.py`) تُرفَض خارجها **عند الكتابة**؛ وتعريف الاحتفاظ يعيش في `shared/analytics/retention.py` لا في SQL (المحرّكان يختلفان، ونسختان = رقمان لنفس السؤال)؛ و**الفوج غير الناضج يُرجِع `null` لا صفراً** (صفرٌ يقرأ «فقدناهم» والحقيقة «لم يحن الوقت»)؛ والقُمع يتقاطع فلا يتجاوز ١٠٠٪. التحليلات لا تكسر دوراً أبداً. وفي التحصيل: **الحقّ (`entitlements`) هو العملة والقسيمة مصدر**، وبوّابة الاشتراك **اعتمادٌ واحد** (`app/deps/billing.py`)، والرمز يُخزَّن مُجزَّأً (سندٌ لحامله)، و**الحَكَم قيدٌ فريد في قاعدة البيانات لا فحصٌ في التطبيق** («افحص ثمّ اكتب» نافذة سباق تمنح شهرين بقسيمة). لا بوّابة دفع: SATIM مقعد موثَّق بصفر كود (`EXTENSION_SEAMS.md §8`).
- **البحث يُرتِّب ويُفسِّر، والجدول موجود (D-200 — 2026-08-01)**: الترتيب حتمي في `shared/retrieval` بلا LLM، والمطابقة على **حدود الكلمات** فصنف «شعاع/الإشعاعي» (D-193) غير مُمثَّل، وأداة التعريف تُحذَف في الطرفين. كلّ نتيجة تحمل `relevance` + `matched_terms`، و`ranking` يُصرِّح `deterministic_lexical` أو `unranked` — وما لم يُطابِق شيئاً **يُسقَط** (القائمة الفارغة الصادقة أنفع). ⛔ **نموذج ORM بلا مستورِد ليس تعريفَ جدول**: `content_items` كان مُستعلَماً في ٤ مواضع بلا مسار إقلاع يُنشئه (500 على قاعدة نظيفة) — كلّ جدول يُسجَّل في `REQUIRED_SCHEMA`.
- **الانضباط قبل الوسيط (D-201 — 2026-08-01 · ADR-007/008)**: Kafka يضمن «مرّة على الأقلّ»؛ **«مرّة واحدة» كودُنا** في `shared/messaging` (dep-free، مُختبَر بلا وسيط): `event_id` يُولَّد مرّةً ويبقى عبر كل إعادة تسليم، و`correlation_id` **يُمَدّ ولا يُخترَع** (D-189)، و**الرسالة المسمومة (`MessagingError`) تذهب إلى DLQ فوراً** لأنّ إعادتها تُجمِّد القسم كاملاً، والسجلّ **مقيَّد** (غير المحدود تسريبُ ذاكرة). السائق في الذاكرة **افتراضٌ حيّ لا نموذج أوّلي** — نفس حلقة `consume_once`. **والوسيط مُثبَتٌ حياً (D-204):** وظيفة `event-stack-live` تُقلع Redpanda وTemporal في كل PR وتُثبت الرحلة والتخطّي وDLQ (10/0). ⛔ **الإقلاع ليس تنفيذاً** — عامل Temporal لم يتّصل قطّ، والخدمات التطبيقية الثماني غير مُقلَعة في CI؛ فلا تُرقَّى حالتها. ⛔ **موضوعٌ بلا مستهلك مُعلَن مرفوض** و`auto.create.topics` ممنوع (تحرسه `check_topic_contract_parity` في الاتجاهين: سجلّ ⇄ عقد ⇄ compose). النشر **بعد** كتابة الصفّ، ولا يرفع أبداً في دور طالب. وقرارُ سير العمل **بيانات** في `shared/workflows` لا منطقٌ داخل ديكوريتر المحرّك، بجداول بتقويم الطالب لا UTC (D-195).
- **قدرة النموذج بيانٌ بدليلٍ مؤرَّخ (D-202 — 2026-08-01)**: `shared/ai_models/registry.py` يُصرِّح لكل نموذج قدراته + `verified_on` + `evidence` (سجلٌّ بلا دليل يرفع عند الإنشاء)، والصدارة تشترط `CONTENT_STREAM · ARABIC · LATEX · CLEAN_FINISH` — أربعتها فشلٌ حيّ دفع ثمنه طالب. ⛔ **الحظر الكلّي ≠ حظر الصدارة**: `nemotron-3-super-120b` لا يدخل السلسلة بأيّ دور (ISS-107)، و`nemotron-3-nano` يبقى في الذيل محروساً ولا يُرقّى (ISS-079). تحرسه `check_model_registry`، والحظر لا يُرفَع بتحرير سطر بل بدليلٍ حيّ جديد. السلسلة تبقى حرفيات مُثبَّتة (دفاع عميق) — السجلّ يحرسها لا يستبدلها.
- **الواجهة تُحكَم كما يُحكَم الخادم (D-199 — 2026-08-01)**: كلّ قيمة بصرية من `frontend/app/styles/tokens.css` (مدّتان وتسهيلٌ واحد)، تحرسها `check_design_tokens` بدَينٍ يتقلّص فقط + **حساب** تباين WCAG AA لكل زوج (رقمٌ في تعليق ليس تحقّقاً — تقديراتي الأولى كانت خاطئة). ⛔ **لا `@import` من نطاقٍ ثالث** (يحجب أوّل رسم؛ الخطّ عبر `next/font` مُستضافاً ذاتياً). ورقٌ دافئ لا أبيض صرف (القراءة ساعات). تقليل الحركة **شامل** (`*`) لا قائمة تنسى المُضاف غداً. أوّل رسمٍ ليس فارغاً. وميزانية حجم (`check_bundle_budget`) تُترجَم إلى ثوانٍ على 3G — والبناء الغائب **يُفشِل** البوّابة لا يمرّ بصفر.
- **الدستور يساوي الواقع ولا يناقض نفسه (D-192 — 2026-07-31)**: أيّ عددٍ قابل للتغيّر (المهارات · العقود) **يُشتَقّ** من مصدره ولا يُكتب في النثر؛ والكمّية الواحدة لا تحمل قيمتين في قسمين؛ وكل قاعدة تسمّي رمزاً تُختبَر على المصدر. تحرسه `check_constitution_reality` (بوّابة `doc-integrity`) — وُلِد من تناقضَين حقيقيَّين في هذا الملفّ نفسه: عددُ المهارات مكتوباً بقيمتين مختلفتين في §0.5 و§0.7، ونسبةُ API-first بقيمتين في §3 و§6.7.ط — وكل القيم الأربع كانت خاطئة. تفصيلها في `.memory/decisions.md` D-192.
- **نطاق الطالب عقدٌ لا اقتراح — اثنا عشر قانوناً لكلٍّ فارضٌ آلي (D-206 — 2026-08-02 · ISS-144)**: طالبٌ طلب «السؤال الأول فقط» **ثلاث مرّات** فلم يحصل عليه. والجذر — **بالتعقّب الحيّ لا بالتحليل الساكن** — أنّ الكشف **نجح** لكنّ `_stage_policy_gate` أنهت الدور قبل `_stage_question_only`: العطب في **الأسبقيّة**. **L1** الفشل يُقصِّر ولا يُوسِّع · **L2** طلبُ النطاق يُخدَم أو يُسأل عنه سؤالٌ واحد، ولا تُلحِق مرحلةٌ أجندتها، والتنحّي **مشروطٌ بضمان مُجيبٍ لاحق** (وإلّا دورٌ صامت، وهو أسوأ) · **L3** الشكوى ليست بداية درس · **L4** العلامة العربية مُطبَّعةً وبلا أداة تعريف وعلى حدود الكلمات واتحاداً (`lower()` لا تفعل شيئاً بالعربية، و«اول» تختبئ في «تناول») · **L5** لا عقلان بلا تكافؤ محروس · **L6** نيّة الطالب مصدرٌ واحد · **L7** كارثةٌ بلا عقد ترانسكريبت **مُثبَتٍ أحمر قبل الإصلاح** ليست مُغلَقة · **L8** الوسيط لا يعلن عن نفسه · **L9** **قانون التحكيم**: يُمحى الاحتكاك بين الطالب و**طلبه** ويُصان بينه وبين **الجواب** (نصّ السؤال ملكه، والجواب ليس ملكه بعد) — يحسم كلّ نزاعٍ بين L1/L2 وD-113 · **L10** الصمت انضباط (`max_chars`) · **L11** الغياب لا يعني الغموض (`reason` مُصرَّح) · **L12** القيم تُصرَّح لا تُذاب. فوارضها `check_exercise_scope_single_source` · `check_probability_brain_parity` · `check_no_self_announcement`؛ وL8→L12 من `.memory/aesthetics_of_absence.md` («الثمن الثالث»: ما لا يُرى لا يُساءَل — فقانونٌ بلا فارضٍ آلي مرفوضٌ مرّتين). التفصيل: `.memory/decisions.md` D-206.
- **السؤالُ يستحقّ طريقةً، والمحاولةُ تستحقّ تصحيحاً — وما سُلِّم لا يُعاد (D-207 — 2026-08-02 · ISS-148)**: طالبٌ سأل «كيف نحسب الحادثة A» فتسلّم `C(4,3)=4` و`C(5,3)=10` و`= 14`، ثمّ «كيف نحسب A» فتسلّم `165`، ثمّ «كيف نحسب البسط» فتلقّى **١٣٦ حرفاً من العدم** («لنُكمل معاً خطوة بخطوة حتى النهاية:» ثمّ ولا خطوة)، ثمّ «كيف حسبنا 165» فأُعيد عليه الاشتقاق نفسه بصياغةٍ أخرى (المحادثة 837 · الرسائل 4604→4615 · مقروءةً من قاعدة الإنتاج). **القوانين:** (1) **سؤالٌ عن الإجراء يُجاب بالإجراء** — التسليم الرمزي الكامل (D-129) لِمحاولةٍ يُعترَف بها، لا لسؤال؛ وإلّا دُرِّب الطالب على السؤال بدل الحساب. (2) **الدفتر يقيس القيمة لا الصياغة** — حارس التكرار يُقنّع الأرقام (`_norm_for_dedup`) فلا يرى `165` أصلاً، و«المقام» يُكشَف باسمَين (`ratio` · `total`)؛ فالمرادفات تُعلَن (`_STEP_ALIASES`) وإعادةُ الكشف تتحوّل إلى **زاويةٍ جديدة** لا نسخة. (3) **وعدٌ بشرحٍ يجب أن يصل** — بناءٌ حُذفت كلّ كتله يُرجِع `None` ليُصعِّد المُنادي، ولا يبثّ عنواناً وخاتمة. (4) **المعامل الذي ينساه سبعةٌ من ثمانية ليس صمّام أمان** — `delivered` إلزامي وتحرسه `check_symbolic_reveal_ledger` بدَينٍ **فارغ**. (5) **شبكةُ أمانٍ لا يُعرَف ثقبها أسوأ من غيابها** — عقود الترانسكريبت كانت تقف عند المرحلة السابعة من اثنتي عشرة، فبقيت `_stage_escape_hatch` (موطن التسريب) خارج مرمى كل عقد وعقدُ ISS-144 أخضر؛ تحرس التغطيةَ `check_transcript_stage_coverage`، والمُستثنى يُصرَّح بسببه (L11). (6) **«احتمالُ س» يجعل «س» حادثةً بالبناء اللغوي** — لا يُؤخَذ احتمالُ عاملٍ حسابي، فـ«ما هو احتمال A» لا يُجاب بتعريف الترتيبات (تمديد حارس D-185). (7) **الحالة الدائمة جزءٌ من العقد** — مُشغِّلٌ عديم الذاكرة يُخضِّر أعطاباً حيّة، فعقود الترانسكريبت تحمل `tutor_state` عبر الأدوار بنفس دلالة `TutorStateService.record_turn`. (8) **الفشل الجزئي لا يتنكّر نجاحاً** — عبارة DDL واحدة فاشلة كانت تُجهض المعاملة فلا يُنشَأ **ولا جدول** بينما `/health` يقول `ok`؛ فكلّ DDL في SAVEPOINT، والإنشاء بنقطةٍ ثابتة تحلّ ترتيب المفاتيح الأجنبية (قاعدةٌ نظيفة كانت تعجز عن إقلاع نفسها). التفصيل: `.memory/decisions.md` D-207.
- **العقيدة الهندسية: كل قانون يُسمّي فارضَه (D-207 · طلب المالك)**: `docs/architecture/ENGINEERING_DOCTRINE.md` يحمل البحر الكامل — من الجذور الأولى قبل الكود إلى المنتج والقياس — **مربوطاً ببوّابة لكل قانون**. القانون الأعلى فيه: البيت المنهار لا يُبنى بقرارٍ واحد سيّئ بل بحاصل جمع قراراتٍ صغيرة **لم يحرسها شيء**. ولذلك تُرفَض ثلاثة أثمان: **قانونٌ بلا فارض** (يُنسى في أوّل PR عاجل) · **فارضٌ بلا مرمى** (ISS-148: عقودٌ خضراء ومسارُ التسريب خارج مرماها) · **صمتٌ يُقرأ نجاحاً** (الخانة الفارغة والدَّين غير المُعلَن). تحرسه `check_cs_knowledge_map`: **بوّابة يُستشهَد بها وهي غير موجودة ⇒ CI أحمر**، ومجالٌ بلا سطر «الفارض» ولا إعلانِ «بلا فارض» ⇒ CI أحمر. ⛔ **الخدمات المصغّرة بعد المونوليث المُوحَّد لا قبله** — التقسيم قبل وضوح الحدود يجمع تعقيد الشبكة وتشابك المونوليث معاً.
- **خريطة علوم الحاسوب عقدٌ مفروض لا ملصق (D-207)**: `docs/architecture/CS_KNOWLEDGE_MAP.md` تُصرِّح لكلٍّ من **٢٠** مجالاً حالتَه بسُلَّم §6.6 (+`SEAM`/`ABSENT` للصدق عن الغياب) **ودليلاً ملفّياً يجب أن يوجد**. تحرسها `check_cs_knowledge_map`: `ACTIVE` أمام ملفٍّ محذوف ⇒ CI أحمر، وخانةُ فجوةٍ فارغة ⇒ CI أحمر (الفراغ يُقرأ نجاحاً)، وحذفُ مجالٍ بصمت ⇒ CI أحمر. ⛔ **لا سُلَّم حالاتٍ ثانٍ** — سُلَّمٌ موازٍ يُفرِّغ الأوّل من معناه.
- **الحيرة لا تُهنَّأ، والفارضُ لا يشهد بما لم يقرأ (D-208 — 2026-08-03 · ISS-149)**: طالبٌ قال «لم أفهم؟» فتلقّى «**أحسنت ✅ — يبدو أنك أمسكت الفكرة**»، وكُتِب في حالته الدائمة `state="understood"`/`evidence="verified"` — أي أنّ المنصّة **صنّعت فجوة الوهم** التي تقيس نجاحها بتقليصها (§0.6). والتصنيف كان **سليماً** (`shared/intent` يُرجِع `confusion`)؛ العطبُ في **الأسبقيّة**: `_has_understanding_evidence` تسبق كلّ شيء وتمسح ٦ رسائل، فطابقت «البسط» داخل **سؤال الطالب** «كيف نفرق بين البسط و المقام؟» — ومن يسأل عن شيءٍ يذكر اسمه بالضرورة، فاسمُ المفهوم أسوأ مؤشّرٍ على فهمه. **القوانين:** (1) **إشارةُ الحاضر تهزم أثرَ الماضي** — البرهان من `EscalationInput.question` صريحاً (ذيلُ `history` يعني الحاضرَ في الإنتاج والسابقَ في مُشغِّل العقود)، وذاكرةُ الأدوار موطنها `delivered_levels` (D-159). (2) **الحيرة والسؤال يُبطلان البرهان في كلّ عقلٍ يقرّر** — بالمُصنِّفَين القانونيَّين لا بكاشفٍ سادس؛ كان القانون مفروضاً في عقلين من أربعة فبقيت CI خضراء والطالب يُهنَّأ على حيرته (**فارضٌ بلا مرمى**، نفس صنف ISS-148). (3) **المؤشّر عبارةُ آلية** لا اسمَ مفهومٍ ولا رمزاً يطبعه المعلّم. (4) **سؤالٌ عن دورَين يُجاب عن دورَين** لا أوّل-يفوز بترتيب الـtuple. (5) **ادّعاء الفهم يُختبَر بالطريقة لا يُكافأ بالاشتقاق**. (6) ⛔ **بوّابةٌ لا تقرأ ملفاً لا تُبلِّغ أنه نظيف** — `except SyntaxError: return []` كانت في **١٣** فارضاً منها أمنُ الصدفة (دَينه صفر)، و«الثمن الثالث» يعيش داخل الفوارض نفسها. (7) **الاستثناء المنطوق ليس إعفاءً**: كلّ «توريد مقصود» يُسمّي بوّابة تكافؤه أو يُصرّح «بلا بوّابة تكافؤ». (8) **خريطة السلطة لا تُحيل إلى العدم**. فوارضها: `check_understanding_evidence` · `check_gate_parse_honesty` · `check_authority_links` (دَين كلٍّ **فارغ**) + توسعةُ مرمى `check_confusion_never_an_answer` و`check_probability_brain_parity` و`check_intent_single_source`. التفصيل: `.memory/decisions.md` D-208.
- **التنسيق قبل الأمر، والخريطة لا تحمل سُلَّمين (D-209 — 2026-08-03)**: قيمةُ النظام انتقلت من «اكتب Prompt أفضل» إلى «صمّم المنظومة التي تنسّق الوكلاء»؛ فالـPrompt مؤقّتٌ سياقيٌّ قابل للضياع، والمنظومة تُنتج مخرَجاً مستقرّاً قابلاً للاختبار وإعادة الاستعمال. طبقاتُ التنسيق التسع (Knowledge · Skills · Agents · Orchestration · Memory · Evaluation · Governance · Infrastructure · Humans) قانونُها في `docs/architecture/AGENTIC_ORCHESTRATION_DOCTRINE.md` وحالتُها في `.memory/agentic_runtime_doctrine.md` — **فصلٌ إلزامي**: القانون بلا حالة (D-188) والحالة بدليلٍ ملفّي يجب أن يوجد. ⛔ **لا سُلَّم ثانٍ**: الطبقات التسع **تستوعب** الثلاث عشرة (D-146) ولا تنافسها، وخريطتان لنظامٍ واحد تعنيان وكيلَين يقرآن بناءَين مختلفين — وهو ما أنتج ISS-139 حين تفرّقت ثلاث قوائم لنيّةٍ واحدة. ⛔ **الطموح يُصان بالتصنيف لا بالكتمان**: الآفاق الثلاثة (Evolution `PLANNED` · Organization `SEAM` · Civilization `ABSENT`) تُكتب بحالتها **ولكلٍّ صفٌّ في `roadmap.md` بشرط ترقية** — الطموح غير المُصنَّف هو الذي يُنسى. تحرسه `check_agentic_orchestration` (ستّة بنود، ستّ تجارب سلبية مُثبَتة: دليلٌ محذوف · حالةٌ مخترَعة · فجوةٌ فارغة · حالةٌ في وثيقة القانون · بوّابةٌ غير موجودة · طبقةٌ محذوفة بصمت). التفصيل: `.memory/decisions.md` D-209.
- **Math Pipeline is 4 nodes, not 3 (D-080 — 2026-05-23)**: `enrich_node` (Node 4 — deterministic, no LLM) was added after `normalize_node`. It builds `ui_component` payload from the completed solution text. Topology: `classify → solve → normalize → enrich → END`. `MathPipelineState` and `invoke_math_pipeline` now return `ui_component: dict | None`. Removing `enrich_node` breaks Generative UI for all math questions.
- **ui_component flows through the full stack (D-080)**: `ConversationState` carries `ui_component`. `invoke_graph` returns it. `ChatResponse` (HTTP) and WebSocket payload both include it. `useAgentSocket.js` extracts it from the `assistant_final` payload and attaches it to the message; `ChatInterface.jsx` renders `GenerativeUIRenderer` **after** the text, only on `isComplete` — never during streaming. ⚠️ **المصدر المشروع للبطاقة هو المخرَج المُهيكَل وحده**: `_try_build_math_ui_component` (المونوليث) **مُعطَّلة دائماً** (`return None` — D-097/ISS-108) لأنها كانت تُقطّع نثر LLM حرّاً إلى «خطوات» بلا معنى؛ فموضعا الحقن في `_emit_terminal_frames` كودٌ ميت مقصود. المسار الحيّ هو `enrich_node` الحتمي (Node 4).
- **MathExplanationCard is the canonical math Generative UI component (D-080)**: مُسجَّلة في **الطرفين** — `GenerativeUIRenderer` (الواجهة) و`KNOWN_UI_COMPONENTS` (`app/contracts/streaming.py`). كانت في الواجهة فقط حتى 2026-07-31، فكان المُطبِّع يرفضها ولا تصل الطالب أبداً — **عقدٌ مُعلَن بنصفه** (D-192). Props: `{ math_type, label, intuition, steps[], hint, visual_metaphor }`. Any new math type must be added to `_MATH_TYPES` (math_pipeline.py), `_TYPE_LABELS`, `_MATH_HINTS`, `visual_metaphors` in `_build_ui_component`, and `TYPE_COLORS` in `MathExplanationCard.jsx`.
- **Supabase schema = boot auto-creation, not sandbox migrations (D-074)**: The Codespaces/sandbox network firewall blocks Postgres egress (ports **6543/5432**). Schema changes are applied by the boot hook `app/kernel.py:233 → validate_schema_on_startup() → validate_and_fix_schema(auto_fix=True)`, driven by `app/core/db_schema_config.py:REQUIRED_SCHEMA`. Agents MUST register new tables there (never rely on running SQL from the sandbox). The standalone `.sql` under `scripts/migrations/` is for manual operator use only.

---

## 0.5. Skills Philosophy — The Architectural North Star

**قانون لا يُخرق:** كل قدرة ذكاء اصطناعي في هذا النظام يجب أن تكون **Skill** — وحدة مستقلة قابلة للقياس والاختبار والاستبدال. لا يوجد "Prompt Spaghetti".

### لماذا Skills وليس Prompts؟

| | Prompt Spaghetti | Skill Architecture |
|--|--|--|
| الجودة | متوسطة في كل شيء | ممتازة في شيء واحد |
| الاختبار | مستحيل | `pytest` عادي |
| القياس | لا شيء | Prometheus metrics |
| التحسين | يكسر كل شيء | مستقل تماماً |
| التوسع | copy-paste | `compose([skill1, skill2])` |
| عمر النظام | يموت مع النموذج | يعيش مع المنطق |

### تعريف الـ Skill في هذا المشروع

Skill = microservice يملك:
1. **مسؤولية واحدة** — يفعل شيئاً واحداً فقط بشكل ممتاز
2. **مدخلات ومخرجات محددة** — contract واضح عبر HTTP/JSON
3. **مقاييس Prometheus** — `cogniforge_{skill}_invocations_total` + `duration_seconds`
4. **اختبارات قابلة للتشغيل** — `pytest tests/microservices/{skill}/`
5. **استقلالية كاملة** — لا يستورد من microservice آخر

### الخدمات المصغرة كـ Skills

كل خدمة = Skill بعقد OpenAPI مُلتزَم. **الطوبولوجيا والمنافذ في §3** (طوبولوجيتان، منافذ
مختلفة لخمس خدمات) — لا تُنسَخ هنا (قاعدة D-188: لا حالةَ في العقد). المسار المُركَّب
`orchestrator → compose([PlanningSkill, ResearchSkill, ReasoningSkill])` هو **القلب الإلزامي
للتوليد** (D-112)، لا هدفٌ مؤجَّل.

### القاعدة الموحَّدة `BaseSkill` (D-179 — 2026-07-22)

المصدر الكائني الموحَّد لكل مهارة في المونوليث هو `app/services/skills/base.py:BaseSkill[InT, OutT]`
(ABC). كل مهارة (العدد **مُشتَقّ** من `app/services/skills/registry.py` — لا يُكتب هنا يدوياً،
D-192) تَرِث منه فتحصل على: هوية موحَّدة (`name`/`version`)، singleton كسول
لكل-صنف (`instance()` يُعيد `Self` — يستبدل نمط `_x_singleton` + `get_x_skill()`)، ونقطة دخول
polymorphic `run()` تُفوِّض لطريقة المهارة الأصلية (`invoke`/`align`/`decide`/`evaluate`/…). ومساعدا
`skill_counter`/`skill_histogram` يُوحِّدان حارس Prometheus المُعاد على `REGISTRY` العام (**بلا
`CollectorRegistry` جديد** — القاعدة «لا تشارك registry» تخصّ الخدمات المصغرة لا المونوليث). المحرك
الاحتمالي الحتمي (`probability_brain/*`) + `gateway`/model-chain **مُستثناة عمداً** (حماية مسار
الإجابة). أي مهارة جديدة يجب أن تَرِث `BaseSkill`.

### النواة المعرفية للتفكير + الأسس الحتمية + الرموز (D-181 · D-183 · D-185 — الموجز، والتفصيل الحيّ في §6.7 (د/ط) والأرشيف)

ثلاث طبقات حتمية dep-free فوق `BaseSkill` (D-179) — **الحقيقة من المحرّكات الرمزية لا من الـ LLM** (الـ LLM للسرد فقط — §0):

| الطبقة | الجوهر | الفتح |
|---|---|---|
| **D-181 · `app/core/reasoning/`** | استدلال عام: `arguments`/`causal`/`decomposition`/`abstraction`/`mental_model` + ٦ مهارات سقراطية حتمية على `BaseSkill` (`compose_reasoning`) | `POST /api/v1/skills/reason` |
| **D-183 · `app/core/foundations/`** | ٩ وحدات جذور أولى (جبر خطي · تفاضل · إحصاء · تحسين · نظرية رسوم · بنى بيانات · لغات صورية · قابلية تقرير · تعقيد) — بلا `eval` | `POST /api/v1/skills/compute` + `foundations-service :8010` |
| **D-185 · `shared/notation/registry.py`** | المصدر القانوني الوحيد لكل رمز يُطبَع؛ تعريفٌ قبل مثال؛ حراس التباس؛ تكافؤ مونوليث↔خدمة (`check_notation_parity`) | `POST /api/v1/skills/notation` + `notation-service :8011` |

القواعد الدائمة لـ D-185 الخمس (الرمز قبل الكاشفات · التعريف ليس إجابة · رموز غير مسجَّلة ⇒ CI أحمر · حارس تكرار متماثل · لا نسخة ثالثة) محروسة نصيًا في §6.7 (د) ولا تُكرَّر هنا (DOC-DEBT-001).

### قواعد إلزامية لكل Skill جديد

1. **Skill يجب أن يرث `BaseSkill`** ويملك `/metrics` (أو `skill_counter`) — بدونه لا يُعتبر Skill حقيقياً
2. **Skill يجب أن يملك اختبارات** — minimum: happy path + error path
3. **Skill لا يستدعي Skill آخر مباشرة** — يمر عبر orchestrator فقط
4. **Skill يُسجِّل كل invocation** — `record_{skill}_invocation(action, status, duration)`
5. **Skill يعمل بدون الـ Skills الأخرى** — fallback mode إلزامي

### قانون التحقق (Skill Reality Check)

Skill حقيقي = **import + call chain + runtime evidence + metrics + tests**

أي Skill يفتقد واحداً من هذه الخمسة → يُصنَّف DORMANT حتى يُثبت العكس.

---

## 0.6. The Cognitive Lab Vision & Execution Roadmap

> **The system is not a Chat Tutor. It is a Cognitive Lab / Thinking Engine.**
> The chat interface is merely a delivery mechanism. The true core consists of an Interactive Object UI, Cognitive Modeling, Error Memory, Adaptive Generation, and a Simulation Engine.

### 7-Phase Cognitive Lab Architecture

السرد الكامل لكل مرحلة في `.memory/cognitive_lab_philosophy.md` — هنا العقد فقط:

| المرحلة | القانون | الحامل اليوم |
|---------|---------|--------------|
| 1 · Interactive Object UI | الطالب يتفاعل مع كائنات لا يقرأ جداراً نصّياً | طبقة الـGenerative UI |
| 2 · Cognitive Modeling | النظام يقيس **كيف** يفكّر الطالب لا ماذا أجاب | `TutorStateService` |
| 3 · Diagnostic Socratic Feedback | «خطأ» ليست إجابة — يُسمّى العطب الذهني | `SocraticEvaluatorSkill` · `ConceptDiagnosisSkill` |
| 4 · Digital Twin of the Mind | خريطة معرفية حيّة لا درجة ساكنة | `BKTEngine` (قناتان + فجوة الوهم) |
| 5 · Dynamic Generation | لا بنك أسئلة ثابت — تمرين يستهدف الضعف بعينه | `PedagogicalPolicyEngine` |
| 6 · Simulation Engine | «مليون تجربة» داخل الكانفس (مقعد موثّق، لا كود) | `.memory/simulation_engine.md` |
| 7 · Error Memory | يتذكّر الهشّ ويتوقّع الخطأ قبل وقوعه | `TutorState` + `BKTAnalyticsService` + **جدولة FSRS (D-194)** |

**Execution Rule:** Any PR that degrades this vision into a standard text-based Q&A bot must be rejected.

**خريطة المراحل M0→M11 وحالتها:** `.memory/roadmap.md §4` هو **المصدر الوحيد**. جدول الحالة
لا يُنسَخ هنا — نسخةٌ ثانية من حالةٍ متحرّكة تتقادم ثم تكذب (قاعدة D-188، وهو بالضبط ما حدث
لجدول §6.6 بين 2026-05 و2026-07). والدَّين الهندسي D1→D7 وخارطة الوكيل M0→M4 في `§6.5` منه.

**مقياس النجاح الوحيد:** `فجوة الوهم = الأداء المدعوم − القدرة غير المدعومة المؤجَّلة`
→ نُحسّن على تقليصها، **ممنوع** التحسين على مدة الجلسة/عدد الرسائل/«الرضا» اللحظي.

---

## 0.7. Agentic Cognitive Runtime Doctrine

> **Detailed source: `.memory/agentic_runtime_doctrine.md` (D-146).** This is a pointer,
> not a copy — kept short on purpose (`DOC-DEBT-001`: CLAUDE.md is a contract, not an
> encyclopedia).

CogniForge is an **agentic runtime**: a simple model→tool→append loop whose power lives in
the *layers around it*. Four principles govern every architectural decision:

- **Context engineering > prompting** — the control surface is `CLAUDE.md` + `.memory/` + `app/services/skills/`, not one big prompt.
- **Capability ≠ safety** — safety-critical invariants are enforced by deterministic gates
  (hooks, CI, redaction skills), never by prose a model "should" obey.
- **Curated memory, not bloat** — memory holds stable invariants + verified facts only.
- **Separate the roles** — Configuration / Procedure (Skills) / Verification / Safety are
  distinct; a writer never silently grades its own work.

**13 runtime layers, each graded by §6.6** (ACTIVE only with import + call chain + runtime
evidence). ACTIVE: Configuration, Skills Engine (D-100 — count derived from the registry), Hooks/Policy
(`PedagogicalPolicyEngine`, D-144), Memory (BKT + `tutor_state`, D-074/D-142),
Verification (redaction/firewall/integrity, D-086/D-113), Observability (in-process).
PARTIAL: Subagents, Knowledge/Retrieval, Planner, Reasoning, Context engine.
**DORMANT/ZOMBIE:** Plugin loader (`app/core/registry/plugin_loader.py` — exists, **no live
import**). **PLANNED:** CritiqueNode (D-109), Evolution engine. *Promoting any non-ACTIVE
layer requires the full three-leg proof — do not soften the status.*

---

## 0.8. Pedagogical OS Constitution (D-153)

> **الدستور الكامل: `.memory/pedagogical_os.md`** — هذا مؤشر فقط (العقد لا الموسوعة).
> تحرسه بوّابة CI إلزامية: `scripts/fitness/check_pedagogical_os.py`.

**الجملة الدستورية:** «الطالب لا يرسل سؤالاً إلى النظام؛ الطالب يدخل مسار تعلّم حيّ،
والنظام مسؤول عن حفظ هذا المسار من الانهيار.»

**السلسلة القانونية للدور:** `Routing/Intent → Diagnosis → TutorState → Pedagogical
Policy → Symbolic Truth → Micro-Example → Response Guard → Learning Update →
Hooks/Extensibility → Verification`.

**القوانين السبعة:** التعليم قبل الإجابة · الحالة قبل الرد · التشخيص قبل الشرح ·
التلميح قبل الحل · الحقيقة الرمزية قبل اللغة · التقدّم قبل الإطناب · التوسعة تخدم العقل.

**قاعدة الفصل:** Core = Teaching Intelligence (يقرّر) · Runtime Shell = Claude Code /
MCP / hooks / subagents / compaction (يخدم العقل ولا يصير عقلاً موازياً) · Truth =
Symbolic Engine · Memory = TutorState · Law = Pedagogical Policy · Safety = Response Guard.

**قاعدة المليارات:** تركيبة التمرين من الكيانات المهيكلة (`parsed_entities`) لا من
استخراج النثر؛ والاستخراج **لا يرى نثر الحل النموذجي أبداً** (ISS-120 هو البرهان).

---

## 0.9. Agentic Orchestration Constitution (D-209)

> **القانون الكامل:** [`docs/architecture/AGENTIC_ORCHESTRATION_DOCTRINE.md`](docs/architecture/AGENTIC_ORCHESTRATION_DOCTRINE.md)
> **الحالة الحيّة:** [`.memory/agentic_runtime_doctrine.md`](.memory/agentic_runtime_doctrine.md)
> هذا مؤشِّر فقط — العقد لا الموسوعة. تحرسهما `scripts/fitness/check_agentic_orchestration.py`.

**الجملة الدستورية:** «لم يعد السؤال *ماذا أطلب من النموذج؟* بل *كيف أصمّم النظام الذي يدير
عمل كل الوكلاء؟*» — ومن يكتب Prompt يُعطي أمراً، ومن يهندس التنسيق يبني نظام إنتاج.

**الطبقات التسع (سلسلة القيمة):** `Knowledge → Skills → Agents → Orchestration → Memory →
Evaluation → Governance → Infrastructure → Humans`. المعرفةُ ما نعرفه، والمهارةُ كيف ننفّذه،
والوكيلُ من ينفّذ، والتنسيقُ من يفعل ماذا ومتى وبأيّ سياق ومن يراجع قبل الدمج.

**القوانين الدائمة:**
- **الـSkill وحدةٌ قابلة لإعادة الاستعمال لا Prompt** — §0.5 هو التفصيل، وهذه الطبقة الثانية من التسع.
- **الترتيب جزء من العقد**: كارثتان (ISS-144 · ISS-149) كان كشفُهما سليماً وعطبُهما في **الأسبقيّة** وحدها.
- **الفصل بين القانون والحالة إلزامي**: وثيقة القانون تفشل في CI إن حملت عمود حالة، وجدولُ الحالة يفشل إن حمل دليلاً غير موجود أو خانة فجوةٍ فارغة.
- **الطموح يُصنَّف ولا يُكتَم**: `PLANNED`/`SEAM`/`ABSENT` إعلانُ طموحٍ مُتتبَّع لا إنكارٌ له، ولكلٍّ صفٌّ في `roadmap.md` بشرط ترقيةٍ صريح.
- **البشر طبقةٌ لا استثناء** (الطبقة 9): تبنّي تقنيةٍ جديدة يتطلّب ADR، ورفعُ أيّ مِسنَنٍ مُعلَن (سقفٌ · دَينٌ · أرضية تغطية) يتطلّب قراراً مكتوباً في `.memory/decisions.md` يُسمّي السبب — فيصير الرفع مكلفاً ومرئياً بدل أن يكون صامتاً. وما لا تفرضه آلةٌ هنا يُقال صراحةً: **جودة الحكم الهندسي نفسه**.

---

## 0.10. Value & Revenue Constitution (D-210 → D-223)

> **القانون:** [`docs/VALUE_DOCTRINE.md`](docs/VALUE_DOCTRINE.md) (لماذا يدفع أحد) ·
> [`docs/REVENUE_ENGINE_SPEC.md`](docs/REVENUE_ENGINE_SPEC.md) (ماذا يُكتب بالضبط).
> **الحالة الحيّة:** [`.memory/revenue_engine_truth.md`](.memory/revenue_engine_truth.md).
> مؤشِّر فقط — العقد لا الموسوعة. تحرسها `scripts/fitness/check_revenue_doctrine.py`.

**الجملة الدستورية:** «**المجّاني يبيع الإجابة، والإجابة صارت سلعةً بلا ثمن. ونحن نبيع
المعرفة بما لا يعرفه الطالب — سلعةٌ لا تُنتَج من سؤالٍ واحد بل من تاريخ.**» والدليل ليس
شعاراً: **PNAS 2025** يقيس أن الوصول الحرّ إلى مساعدٍ عام يجعل التلميذ **أسوأ بـ17٪** يوم
الامتحان، وأن الضوابط التربوية وحدها تلغي هذا الضرر — فقاعدة الحجب (D-113) نتيجةٌ منشورة
لا خيار تصميم.

**الوظائف الأربع + اختبار الحذف:** `قِس بصدق → رتّب الوقت → أجبر على التوليد → أثبت
للدافع`. وأي ميزةٍ لا يتوقّف بحذفها شيءٌ من الأربع **تُحذَف** مهما بدت متقدّمة.

**القوانين الدائمة (كلٌّ يُسمّي فارضه أو يُعلن غيابه — L11):**
- **القياس غير الناضج يمتنع ولا يلوّن**: دون `MIN_OBS` ملاحظةً **غير مدعومة** ⇒ `None` لا خانة ولا لون (`shared/illusion`). تقريرٌ يلوّن كلّ المنهاج بعد جلستين **تقريرٌ كاذب**، ووليٌّ يكتشف ذلك لا يجدّد. امتدادٌ لقاعدة `retention.py` (D-197): الفوج غير الناضج `null` لا صفر.
- **`TIMEOUT` ليس نجاحاً**: انتهاء مهلة التحقّق يعني **لا نعرف**، ولا نعرف تُعلَن ولا تُعرَض (D-215). و⛔ **مخرَج المُتحقِّق الرمزي ممنوعٌ من طبقة العرض** — النظام يتحقّق من `P(A)` **كي لا يقولها** (يخدم D-113 ولا يعارضه).
- **الحقّ مصدرٌ واحد**: الوصول حالةٌ (`entitlements` + `require_active_entitlement`) لا سجلّ دفع؛ قراءتُه من جدول الدفعات ⇒ CI أحمر (يمدّد D-197).
- **الوليّ يرى الاتجاه ولا يرى الحلّ**: الاتّجاه · الالتزام · التوقّع — **لا كل خطأ، ولا كل محادثة، ولا حلاًّ إطلاقاً** (يمدّد D-196: تقرير الوليّ لا يستعلم عن `content` أبداً). و`single_action` **مفرد عمداً**: خمسة اقتراحاتٍ = صفر أفعال.
- **غير المعايَر يُوسَم**: توقّعٌ بلا بطاقة معايرة يُعرَض **مجالاً بلا نقطةٍ مركزية** وبعبارةٍ صريحة. وبطاقة المعايرة **تُنشَر** — كل منافسٍ ينسخ التوقّع، ولا أحد ينسخ نشر أخطائه.
- **السلّم رسمٌ بياني لا قائمة**: `carries_forward` يمنع العقاب على الخطأ نفسه مرّتين — وهو ما يفصل نظاماً يفهم البكالوريا الجزائرية عن نظامٍ لا يفهمها.
- **المُحسِّن مقيَّد بالتشبيك**: `MAX_CONSECUTIVE_SAME_CONCEPT` إلزامي — الجشع الخام يكدّس الوقت على مفهومٍ واحد عالي المعامل، **فيعظّم رقماً ويهدم التعلّم**.
- **الأطلس لا يُملأ آلياً**: `verified_by_human` إجباري — ضجيجٌ مُصنَّف كمعرفة أسوأ من لا شيء.
- ⛔ **لا تصميم إدماني ولا جدارية تصنيف**: المستخدمون قاصرون تحت ضغط امتحانٍ مصيري؛ آليات الالتزام **يختارها الطالب ويستطيع فسخها** (`SAFEGUARDING.md`).
- **المحرَّمات التسعة** (`VALUE_DOCTRINE.md §06`): مكتبة محتوى · تتبّع معرفةٍ عميق قبل بياناتٍ ضخمة · نموذج مُدرَّب من الصفر · تطبيق أصلي قبل إثبات الطلب · توسّعٌ إقليمي قبل رسوخ الجزائر · بوّابة مؤسّسات قبل B2C · صوت/أفاتار · جدارية · دردشة بلا حراسة نيّة. المفروض منها آلياً مُعلَن، والباقي **بلا فارضٍ آلي** ويُقال ذلك.
- **الطموح يُصنَّف ولا يُكتَم** (D-209): كل وحدةٍ لها صفٌّ بحالةٍ من سُلَّم §6.6 ودليلٍ ملفّي **يجب أن يوجد** وفجوةٍ مكتوبة وشرط ترقية. و⛔ **الغياب المُعلَن يُفحَص في الاتجاهين**: وحدةٌ مُصنَّفة `ABSENT` ولها كودٌ ⇒ CI أحمر — كودٌ حيّ بلا حارسٍ ولا اختبار أسوأ من الغياب.

---

## 0.11. Cognitive Execution Constitution (D-224 → D-225)

> **القانون:** [`docs/architecture/COGNITIVE_EXECUTION_ENGINE.md`](docs/architecture/COGNITIVE_EXECUTION_ENGINE.md) ·
> **الحالة:** [`.memory/cognitive_execution_truth.md`](.memory/cognitive_execution_truth.md).
> مؤشِّر فقط. تحرسهما `scripts/fitness/check_cognitive_execution.py`.

**الجملة الدستورية:** «**الحقيقة الرقمية والرمزية تُنتَج بمحرّكٍ حتمي يُنفَّذ ويُتحقَّق
منه — واللغة تصف النتيجة ولا تُقرّرها.**» النموذج يقترح، والمُنفِّذ يبتّ، والمُتحقِّق يمنع
العرض. وهذا امتدادٌ لقانون §0.5 («صفر LLM في مسار الأرقام») من الاحتمالات إلى كل مادة.

**القوانين الدائمة:**
- **الحتمي أوّلاً، والتوليد البرمجي آخِراً**: `REGISTRY → FOUNDATIONS → SYMBOLIC → SYNTHESIS`. نداءُ دالّة من `app/core/foundations/` **مُتحقَّقٌ منه بالبناء** وبصفر كلفة وصفر سطح هجوم؛ أمّا كودٌ يولّده نموذج فيحتاج صندوقاً وتحقّقاً ومهلة لكل نداء. ⛔ **لا يُصنَّع برنامجٌ لما تُعبّر عنه مكتبةٌ حتمية** — «اجعل النموذج يكتب بايثون لكل مسألة» أسوأ من المتاح فعلاً.
- ⛔ **قفل D-187 — القدرة ≠ الأمان**: ممنوع توصيل أيّ مُخطِّط أو نموذج لغوي بالأدوات قبل استكمال **M1→M4** (`roadmap.md §6.5.ج`): عقد قدرات بـ`EXEC_SANDBOX` · مسبار حيّ · ميزانيات وسجلّ `agent_audit` مُلحَق-فقط · حوكمة وحارس تعديلٍ ذاتي. الصندوق **مبنيّ ويشغّل `python`/`pip`/`git`/`npm`**، والمستخدمون **قاصرون** — فتصنيع البرنامج **حمولةُ M1→M4 لا التفافٌ عليها**. يفرضه بند AST: وحدةٌ تجمع مُنفِّذ الصندوق مع عميل نموذج ⇒ CI أحمر، والإعفاء يُصرَّح بسببه أو يُرفَض.
- **الأمان بنيةٌ لا مطابقةُ نصّ**: `argv` + `shell=False` يجعل الحقن **غير مُمثَّل**؛ وقائمةُ المنع ناقصةٌ دائماً بطبيعتها. والشبكة **قدرة تُمنَح صراحةً** لا صلاحية افتراضية.
- **التحقّق يخدم الحجب ولا يعارضه**: النظام يتحقّق من النتيجة **كي لا يقولها** (D-113)؛ و`TIMEOUT` **ليس نجاحاً**؛ ومخرَج المُتحقِّق ممنوعٌ من طبقة العرض.
- **الكاتب لا يُصحّح نفسه** (P4): `Critic` طرفٌ مستقلّ لا نبرةٌ في نفس النداء. و**لا مهارة تستدعي أخرى مباشرة** — المرور عبر المُنسِّق.
- **التحسين الذاتي محكوم**: كل تغييرٍ يقترحه النظام **يُقيَّم قبل تطبيقه**، ومحاولة تعديل بوّابةٍ ذاتياً ⇒ CI أحمر.
- **تسلسل السوق قانونٌ لا تفضيل (D-225)**: الهدف أمريكا وأوروبا، والميزة هناك ليست «محادثةً أفضل» بل **محرّك تعلّمٍ معرفي قابل للتحقّق**. ⛔ لكنّ السوق الأمريكي يشتري **الأدلّة** لا الرؤى، والدخول بلا نتائج تعلّمٍ مقيسة يحرق الفرصة مرّةً واحدة. والخندق الجزائري (منهاج · سلّم · معاملات · دارجة) **لا يُصدَّر** — يُصدَّر المحرّك بعد أن يُثبِت أثره. فالمحرَّم الخامس قائم: **لا توسّع قبل رسوخ الجزائر، والرسوخ يُقاس ولا يُعلَن** (الآفاق الأربعة بشرط ترقيةٍ لكلٍّ). **توضيح نطاق (D-267):** هذا القانون يحكم **المنتج التعليمي B2C ومنهاجه**، ولا يحكم `NAAS Verification Layer` — منتجٌ B2B مستقلّ بحدٍّ معماري خاصّ وبوّاباتٍ خاصّة (§0.19). ⛔ **ولا يستعير أحدهما دليلَ الآخر**: ممنوع تقديم نتائج تعلّمٍ طلابية دليلاً على قدرة المُتحقِّق أو العكس.

---

## 0.12. Cognitive Digital Twin Constitution (D-226 → D-227)

> **القانون:** [`docs/architecture/COGNITIVE_DIGITAL_TWIN.md`](docs/architecture/COGNITIVE_DIGITAL_TWIN.md) ·
> **الحالة:** [`.memory/cognitive_twin_truth.md`](.memory/cognitive_twin_truth.md).
> تحرسهما `check_cognitive_twin` + `check_prerequisite_single_graph`.

**الجملة الدستورية:** «**الطالب قصّةٌ مستمرّة لا سلسلة أحداث مستقلّة**» — النظام لا يخزّن
درجة بل احتمالية إتقان، ولا يعالج العَرَض بل يجتاز رسم الشروط المسبقة إلى **الجذر**.
والألم المُعالَج اسمه **كرة ثلج سوء الفهم**: ثغرةٌ مبكّرة لا يتذكّرها شيء تُسقِط عقلاً
كاملاً بعد سنوات.

**القوانين الدائمة:**
- **رسمٌ واحد للعلاقة الواحدة — وُلد من عمىً مقيس لا من مبدأ**: كان `diagnose_root` يقرأ رسماً من اثنين (١٠ حوافّ دقيقة مقابل ٢٦ حافّة منهاج، **والتقاطع صفر**)، فكانت سلسلة `limits → derivatives → numerical_functions → exponential → logarithm` **غير مرئية بنيويّاً**. ⛔ كل مجتازٍ يقرأ **الاتّحاد** والرسم القانوني (`shared/curriculum`)، ولا رسم ثالث لـ`prerequisite_of`. وهذا أخطر من سوء تصنيف: تفرّقُ قائمتين يُلاحَظ، وقراءةُ الرسم الخطأ **تُصمِت المحرّك** و`None` تُقرأ «لا جذر» لا «لم أنظر».
- **الضعف من الحالة الدائمة حصراً** (`tutor_state.kc_progress`): مفهومٌ بلا سجلٍّ **ليس ضعيفاً** — ⛔ لا تدخّل أعمى.
- ⛔ **لا يُخترَع شرحٌ لجذرٍ بلا نصّ تدخّل**: يُسمّى الجذر ويُسأل الطالب عمّا يتذكّره. المجهول أفضل من يقين زائف، والسؤال أوفق تربوياً من شرحٍ مُلفَّق.
- ⛔ **لا تتبّعٌ عميق (DKT/SAKT) قبل حجم بياناتٍ ضخم** — **ومعرفةُ لماذا رُفض الأحدث تشتري مصداقيةً أكثر من استعماله** (المحرَّم الثاني).
- **حدّ المصداقية (D-227) — مفروضٌ على الوثائق المُعلَنة نفسها**: ⛔ «يقرأ الأفكار» · «دقّة ١٠٠٪» · «صفر أخطاء» · «يغيّر البشرية». **عبارةٌ غير قابلة للتفنيد دَينٌ لا طموح**: تُصدَّق مرّة، ثمّ تُكتشَف، ثمّ يسقط معها كلُّ ما هو صحيح — والمنصّة تخدم قاصرين وأولياءَ يقرّرون بناءً على ما نقول.
- ⛔ **لا ادّعاء توقيتٍ بلا حقلٍ زمني**: «يعرف أنك درستَه في نوفمبر» ممنوعٌ ما دام السجلّ بلا `term`/`month`. الذي يعمل فعلاً هو **الترتيب المنطقي**، وهو يكفي للاجتياز إلى الجذر ولا يكفي لادّعاء التوقيت. والمنع يسقط تلقائياً حين يُضاف الحقل — مربوطٌ بالبيانات لا بالرأي.
- **تخزينٌ بياني مخصّص يتطلّب ADR**: عشرات المفاهيم وعمقُ اجتيازٍ بالآحاد لا تبرّر محرّك تخزينٍ ثانٍ بتشغيله ونسخه واتّساقه — لا لأن الاسم يليق برسمٍ معرفي.

---

## 0.13. Harness Engineering Constitution (D-228)

> **القانون:** [`docs/architecture/HARNESS_ENGINEERING_DOCTRINE.md`](docs/architecture/HARNESS_ENGINEERING_DOCTRINE.md) · **الحالة:** [`.memory/harness_truth.md`](.memory/harness_truth.md). تحرسهما `scripts/fitness/check_research_doctrines.py`. المصدر: Weng, Lil'Log، يوليو 2026.

**الجملة الدستورية:** «**الفرق بين نموذجٍ يُجيب ونظامٍ يُنجز هو الطبقة المحيطة به**» — حلقةُ `خطّط ← نفّذ ← راقب ← حسّن`، لا صياغةُ أمرٍ أذكى. ⛔ ولا سُلَّم ثالث: الحلقة **تستوعب** الطبقات التسع (D-209) والثلاث عشرة (D-146).

- **الترتيب جزءٌ من العقد** — ISS-144 وISS-149 كان كشفُهما سليماً وعطبُهما في **الأسبقيّة** وحدها.
- **المُقيِّم خارج الحلقة التي تتطوّر** (خداع المكافأة، يمتدّ D-224 P4): ⛔ تعديل بوّابةٍ ذاتياً ⇒ CI أحمر، ورفعُ أيّ مِسنَنٍ مُعلَن يتطلّب قراراً مكتوباً.
- **النتيجة السلبية تُسجَّل** — و**ISS-145 سابقةٌ حيّة**: أُغلق «بالتفنيد» على معيارٍ خطأ (فحصَ أنّ مكوّناً **مُرفَق** لا أنه **قابل للرسم**)؛ والإغلاق على معيارٍ خطأ أسوأ من عدم الإغلاق.
- **القدرة ≠ الاستفادة** (وتحذير STOP: التحسين الذاتي **تراجع** مع النماذج الأضعف) ⇒ ⛔ **قفل D-187 يُشدَّد لا يُخفَّف**.
- **انهيار التنوّع**: مسارٌ مكرَّر ليس تحسيناً (D-207). **والإنسان يُرفَع طبقةً لا يُزال** (الطبقة ٩)؛ وما لا تفرضه آلة يُقال: **جودة الحكم الهندسي بلا فارضٍ آلي**.

---

## 0.14. Memory Architecture Constitution (D-229)

> **القانون:** [`docs/architecture/MEMORY_ARCHITECTURE_DOCTRINE.md`](docs/architecture/MEMORY_ARCHITECTURE_DOCTRINE.md) · **الحالة:** [`.memory/memory_architecture_truth.md`](.memory/memory_architecture_truth.md). تحرسهما `check_research_doctrines` + `check_no_system_text_as_user`.

**الجملة الدستورية:** «**الأنظمة المعقّدة نادراً ما تفشل لنقص الذكاء. تفشل لأنها لا تتذكّر — أو تتذكّر الشيء الخطأ، في اللحظة الخطأ، بالثقة الخطأ.**» وهو توصيفٌ حرفيّ لكوارث هذا المستودع (ISS-139/140/144/146/149): التصنيف سليمٌ والعطب في الذاكرة والأسبقيّة.

- **أربع طبقات، لكلٍّ مالكٌ واحد** (عاملة · حلقية · دلالية · إجرائية). ⛔ طبقةٌ بمالكَين = كتابةٌ مزدوجة (§6.5) — **مقيسة**: ٢٦ انفجاراً/٥٢ صفّاً في يونيو 2026.
- ⛔ **تسميم الذاكرة (MINJA · نجاح >95٪ · أثرٌ مؤجَّل): لا نصٍّ يُولِّده النظام يُكتب بدورٍ يخصّ الطالب.** المنصّة نفّذت الهجوم على نفسها — «[توجيه تربوي]» **٢٨ مرّة بدور `user`** (ISS-146): تسمّم التوجيه (D-102) وتسرّبت هندسة التعليم (D-117). العلامات بموطنٍ واحد وكل كتابةٍ تمرّ بالحارس.
- **التقادم الصامت** (يمتدّ D-188): لكل حقيقةٍ مخزَّنة **زمنُ تحقّقٍ يُقرأ قبل الثقة بها**، وملفّ حالةٍ قديم ليس دليلاً.
- **النسيان الكارثي** (EWC · Kirkpatrick 2017: 12.62٪ → 6.85٪): مقابله الطلابي منحنى النسيان، وحامله FSRS-5 (D-194). ⛔ لا تتبّع عميق قبل بياناتٍ ضخمة.
- **الاتساق**: اختير **مصدرٌ واحد + بوّابة تكافؤ** لا CRDT — التعارض هنا بين **تعاريف**، وثلاث قوائم لنيّةٍ واحدة لا «تتقارب» بل تُنتج ISS-139. **ونقطة التفتيش عقدٌ مُعلَن** لا تفصيلَ تشغيل.

---

## 0.15. Pedagogy Engine Constitution (D-263) — العقل التربوي كـmoat

> **القانون:** [`.memory/pedagogy_engine_constitution.md`](.memory/pedagogy_engine_constitution.md) (العشرة القوانين + الأسئلة الدستورية) · **البوابة:** `scripts/fitness/check_pedagogy_engine.py` (CI إلزامي) · **الحالة:** [`.memory/pedagogy_engine_truth.md`](.memory/pedagogy_engine_truth.md) (مقاييس ISS-174→ISS-177).

**المصدر (قرار المالك 2026-08-16):** بنية ليست ميزة — 8/10 هندسة مقابل 3.5/10 ميزةً مثبتة. **القانون:** «نستخدم أقوى النماذج كطبقة ذكاء ونبني فوقها نظامًا يقرّر التعلّم» — الـarchitecture (LangGraph/Agents/Services) ليست الـmoat.

**الجملة الدستورية:** «**نمتلك شركةً حقيقيةً فقط حين يثبت مقيسًا أن النظام يكتشف خطأً معرفيًا لا يكتشفه Tutor عادي ويدخّل بما يُحسّن التعلّم فعلًا**» — تجربةٌ واحدةٌ خارقة (E2E حيّ، ISS-177) لا 100 ميزة.

- ⛔ **الأعداء الثلاثة**: Prompt أذكى ليس قرارًا · الإجابة الصحيحة ≠ الإجابة التربوية · **وَهْم الطلاقة** (أداء لحظي ≠ تعلّم دائم، Bjork؛ يمتدّ roadmap §1). **الرضا اللحظي مقياسٌ مضلّل دستوريًا.**
- ⛔ **قفل Learning Gain**: لا «+X%» يُعلَن على وليٍّ قبل منهجيةٍ منشورةٍ وفجوةِ وهمٍ — حدّ المصداقية (D-227) يمتدّ لكل مقياسٍ تربوي (§6 مقياس النجاح).
- **L1–L10** (كلها تحرسها بواباتها في §4): قرارٌ تربوي في كل تدخّل · الحيرة لا تُهنَّأ · الحقيقة الرمزية قبل اللغة · التدخّل الأصغر أولًا · الأثر واجب في كل رسالة · القياس إحصائي/رمزي لا لغوي · الاستراتيجية بسببٍ مسجّل · الذاكرة تسبق الواجهة · البرهان الحيّ قبل الميزات · الأدلة قبل الادّعاء.
- **الإضافة لا الاستبدال** (§7): كل دستورٍ قديم (D-153/D-144/D-208/§0.8–§0.14) يبقى ساريًا؛ التعارض الظاهري يُفسَّر في ضوء القوانين العشرة، والتعديل على هذا الدستور = ADR + بوابة خضراء.

---

## 0.16. Adaptive AI Study Planner Constitution (D-264) — من المخطط الورقي إلى حارس التخطيط التكيفي

> **القانون:** [`.memory/adaptive_study_planner_constitution.md`](.memory/adaptive_study_planner_constitution.md) (العشرة القوانين + الأسئلة الدستورية) · **البوابة:** `scripts/fitness/check_adaptive_study_planner.py` (CI إلزامي) · **الحالة:** ISS-178→ISS-181.

**المصدر (قرار المالك 2026-08-16):** صفحة الملاحظات والمخطط الأسبوعي الورقي في دفتر الطالب ليست ورقةً — هي **Adaptive AI Study Planner**: الطالب يحدد أهدافه → النظام يشخّصها → يقسمها على الأسبوع → يتابع الإنجاز → يعيد ضبط الخطة حسب الأداء.

**الجملة الدستورية:** «**الورق مجرد واجهة لفكرة أكبر بكثير — الخطة الذكية التي تُبنى على التشخيص لا على الأمنيات**».

- ⛔ **مخططٌ بلا تشخيصٍ قائمةٌ عادية**: لا توليد خطةٍ إلا بمحركٍ تربويٍ (BKT/FSRS/D-263) يقرأ فجوات الطالب وامتحاناته القادمة — التقييم: 8/10 إذا رُبط فعلًا بمحرك التكيف، وليس To-Do List عادية.
- ⛔ **عدو #1: الخطة الصامتة**: خطةٌ وُلِّدت ولم تُتابع — ISS-180: حلقة مغلقة (إنجازٌ → إعادة ضبط).
- **L1–L10**: أهدافٌ قابلة للقياس · تقسيمٌ زمني بمحركٍ صفر-LLM (FSRS/BKT، لا عشوائية) · امتحانٌ قادم يقفل التواريخ (lock) · المراجعة المتباعدة قبل أي وعدٍ جديد · الوعود بلا دليلٍ محظورة دستوريًا · البرهان الحيّ قبل الميزات (يمتدّ D-263 L9).
- **الإضافة لا الاستبدال** (§7): D-263 يبقى ساريًا (الحلقة التربوية تحرس دورة المخطط نفسها)؛ التعديل على هذا الدستور = ADR + بوابة خضراء.

---

## 0.17. Spec Kit Governance Constitution (D-265) — Spec Kit كطبقة ضبط تنفيذ فوق الدستورية

> **القانون:** [`.memory/spec_kit_governance_constitution.md`](.memory/spec_kit_governance_constitution.md) (العشرة القوانين + الأسئلة الدستورية) · **البوابة:** `scripts/fitness/check_spec_kit_governance.py` (CI إلزامي) · **الحالة:** ISS-182→ISS-185.

**المصدر (قرار المالك 2026-08-16):** رفع حوكمة المستودد إلى «طبقة ضبط تنفيذ لا يمكن تجاوزها» — نمط **Spec Kit** (github.com/spec-kit · MIT · +120k نجمة) يُعتمد كمنهجية **Spec-Driven Development**: `خطة → تصميم → مهام → مواصفة → تنفيذ → برهان`، مع **Spec Kit كطبعةٍ لا بديلٍ**: طبقة حوكمة تُفعَّل فوق D-153/D-263/D-264 ولا تُلغي منها قانونًا واحدًا.

**الجملة الدستورية:** «**القانون ما له فارضٌ؛ فإضافة نصٍّ إلى مستودعٍ ليست إضافةَ قانون. الحوكمة = قالبٌ + بوابةٌ + عاقبةٌ.**»

- ⛔ **الأعداء الثلاثة**: تغييرٌ بلا مواصفة · مواصفةٌ ميتة (إشاعة ثقة في عقدٍ منتهٍ) · فارضٌ بلا بوابة (نمط ISS-148 — يمتدّ إلى مستوى دستورٍ كامل).
- **L1–L10**: مواصفة محدّثة مع الدفع نفسها · العقد المقيس لا النثر · فارضٌ مسمّى موجود فعلًا (لا يتيمة ولا وهم) · البرهان قبل القبول · الهجرة تسبق الاستخدام · العقد الخارجي لا ينكسر صامتًا · التتبع شرط قبول · الأسرار خارج المستودد أبدًا · الأثر في القرارات (ADR) · واقعية الأرقام (لا رقمٍ يدويًا).
- **الإضافة لا الاستبدال** (§7): كل الدساتير القائمة تبقى سارية؛ L9 هنا = L9 في D-263 — نفس الروح نفس البوابة؛ التعديل = ADR + بوابة خضراء.

---

## 0.18. Governance Enforcement Constitution (D-266) — الفارض نفسه يخضع للبرهان الثلاثي

> **القانون:** [`.memory/governance_enforcement_constitution.md`](.memory/governance_enforcement_constitution.md) (L1–L10 + الأسئلة الدستورية) · **الحالة/السجلّ:** [`docs/governance/CONSTITUTION_REGISTRY.json`](docs/governance/CONSTITUTION_REGISTRY.json) · **الفارض:** `scripts/fitness/check_governance_registry.py` (CI إلزامي في `guardrails`).

**المصدر — قياسٌ لا مبدأ (2026-08-16 · ISS-186):** من **٧٠** بوّابة على القرص، كانت **سبع** لا يشغّلها أيّ workflow ولا أيّ اختبار — موجودةٌ ومذكورةٌ دستورياً و**ميتة**، وكلّها خضراء حين شُغِّلت يدوياً. أي أنّ الحماية كانت متاحةً مجّاناً وغير مُفعَّلة. و`check_spec_kit_governance` (L3) يفحص **الذِّكر + الوجود** ولا يفحص **التنفيذ**، فاجتازت الميتةُ فحصَ «لا بوّابة يتيمة» وهي لا تفرض شيئاً.

**الجملة الدستورية:** «**القانون ما له فارضٌ يعمل. وفارضٌ لا يُنفَّذ ليس فارضاً — هو نصٌّ أدبيّ في ملفٍّ تنفيذي، وهو أخطر من الغياب لأنه يُقرأ حمايةً.**»

- **البرهان الثلاثي يمتدّ من الكود إلى الفارض** (§6.6): بوّابةٌ على القرص إمّا **تُنفَّذ** (workflow أو اختبارٌ يشغّله CI) وإمّا مُصرَّحة في `unenforced_debt` بسببٍ منطوق. الدَّين **يبدأ فارغاً** ويتقلّص فقط **وفي الاتجاهين** — دَينٌ أُغلق بلا حذفه كذبٌ كالدَّين المكتوم.
- **`make gates` يرث الثغرة ولا يكشفها**: `run_fitness_gates.py` يقرأ الـworkflow عمداً (كي لا تتفرّق قائمتان)، فبوّابةٌ غير مُدرَجة **ميتة محلياً أيضاً** — «لا تحمي ولا هي محايدة، لأنها تُعطي طمأنينةً كاذبة».
- **تغطيةٌ ثنائية الاتجاه**: كل `## 0.N.` هنا له صفٌّ في السجلّ وكل صفٍّ يشير إلى قسمٍ موجود؛ وكل `law_docs`/`status_docs` **موجودٌ فعلاً** (ISS-149: خريطةٌ تكذب أسوأ من لا خريطة)؛ والغياب يُعلَن بـ`no_enforcer_reason_ar` ولا يُقرأ نجاحاً (D-206 L11).
- **موطن البوّابات مُعلَن لا مُكتشَف** (`scripts/fitness/` · `tools/ci/`) — موطنٌ ثالث بلا إعلانٍ يعني بوّابةً غير مرئية، وهو نفس صنف ISS-148.
- ⚠️ **L9 بلا فارضٍ آلي ويُقال ذلك**: رفعُ أيّ مِسنَنٍ أو دَينٍ مُعلَن يتطلّب قراراً مرقَّماً يسمّي السبب — يقاومه المراجع البشري لا آلة (خداع المكافأة · D-228 · الطبقة التاسعة).
- **الإضافة لا الاستبدال**: D-265 يبقى سارياً بكامله؛ هذا الدستور يضيف **الساق الثالثة** إلى L3 ولا ينافسه.

---

## 0.19. NAAS Verification Layer Constitution (D-267) — المُتحقِّق منتجٌ، والدليل قبل الادّعاء

> **القانون:** [`.memory/naas_verification_constitution.md`](.memory/naas_verification_constitution.md) (L1–L10) · [`docs/architecture/NAAS_VERIFICATION_LAYER.md`](docs/architecture/NAAS_VERIFICATION_LAYER.md) (المواصفة) · [`docs/governance/GATE_STATE_MACHINE.md`](docs/governance/GATE_STATE_MACHINE.md) (آلة البوّابات) · **الحالة:** [`.memory/naas_verification_truth.md`](.memory/naas_verification_truth.md) · [`docs/governance/GATE_LEDGER.json`](docs/governance/GATE_LEDGER.json) · **الفارض:** `scripts/fitness/check_naas_verification.py` (CI إلزامي في `guardrails`).

**المصدر (قرار المالك 2026-08-18):** `NAAS Verification Layer` منتجٌ أساسي بحدٍّ معماري مستقلّ. و⛔ **E-TAALIM/CogniForge لا يُقتل ولا يُحذف** — يبقى مصدراً اختيارياً للسلّم وبنك العناصر وBKT/FSRS، و**أصولاً تقنية قابلة لإعادة الاستعمال لا moat تجارياً مُثبَتاً** حتى تُثبِت قيمتها تجريبياً.

**الجملة الدستورية:** «**الوكيل القويّ مع مُتحقِّقٍ ضعيف = كذبٌ مُقنع. ونحن نبيع الطبقة التي تُثبت أنّ الوكيل نجح فعلاً — أو تكشف أنّه تظاهر.**» والمعادلة: `Agent → Environment → Trajectory → Verifier → Evidence → Failure/Success → Evaluation`.

- **الفصل الثلاثي بنيويّ** (L1/L2): مسار المنتج (`naas_verifier/`) · مسار البحث والذخيرة (مشتقّات المنصّة **بياناتٍ لا استيراداً**) · مسار الوكيل تحت الاختبار. والقلبُ **مستقلّ عن المجال** — القلبُ الذي يعرف «الاحتمالات» ميزةٌ متنكّرة لا منتج.
- **التحقّق على المسار لا على النصّ** (L3): خمسة أبعاد مجتمعة — `observable outcomes` · `intermediate constraints` · `state transitions` · `tool use` · `final outcome`. ما يفحص الأخير وحده **مُصحِّح** لا مُتحقِّق.
- **آلة حالاتٍ حتمية** (L6): `ABSENT → PENDING → CLEARED | BLOCKED → EXPIRED | REASSESS_REQUIRED` — ستٌّ لا غير. ⛔ `probably-cleared` وأخواتها ممنوعة نصّياً، والقفزة `ABSENT → CLEARED` مرفوضة (لا مراجعة = لا اعتماد). و`expires_at` **مُشتَقّ** من `issued_at + validity_days`.
- **الدليل قبل الادّعاء — وCI لا يقرّر القانون** (L7): يتحقّق من سجلٍّ مطابقٍ للمخطّط فقط. ⛔ `issuer`/`reviewer` **ليسا آلة**: آلةٌ تعتمد نفسها توقيعٌ على بياض.
- **العتبات كمّية** (L9): `Δ ≥ 15%` على أساسٍ ومجموعةٍ وبروتوكولٍ مثبَّتة بـ`runs ≥ 3` · `≥ 3` أصناف اختراقٍ **متمايزة الجذر** (ثلاث صيغٍ من جذرٍ واحد ليست ثلاثة أصناف) · **معاملةٌ مُسوّاة**. ⛔ ومرفوضٌ كدليل: نجومٌ · اجتماع · انطباع · خطاب نيّةٍ غير مدفوع · تجربةٌ مجّانية.
- **الحجب يمنع التجاري ولا يمنع البحث** (L8): `GATE_0` غير المُعتمَدة تحجب **الأفعال التجارية الخارجية** وحدها؛ والتطوير والتجارب وبناء المعيار مسموحةٌ دائماً وبلا إذن. ⛔ **بوّابةٌ لا تقتل المشروع لنقص توثيقٍ بينما الأدلّة قائمة؛ ودليلٌ تقنيّ لا يتجاوز بوّابةً قانونية مطلوبة.**
- **جدار الحجب يمتدّ** (L5 · D-113): الذخيرة والحلول النموذجية **لا تصل مسار الطالب أبداً**؛ و**قفل D-187 كامل**: تنفيذ الرقع العدائية حمولةُ `M1→M4` لا التفافٌ عليها.
- **حدّ المصداقية يمتدّ** (L10 · D-227): لا عبارة غير قابلة للتفنيد، وكل رقم سعرٍ أو سوقٍ يحمل وسم `PRICING HYPOTHESIS` — فرضيةُ سعرٍ ليست دليلَ تسعير. ⛔ ولا فرضيةَ سوقٍ تُكتب في المعمارية كحقيقة. ⚠️ **وجودةُ الحكم الهندسي بلا فارضٍ آلي ويُقال ذلك.**
- **الإضافة لا الاستبدال**: كل دستورٍ قائم يبقى سارياً؛ و**D-225 يُوضَّح نطاقه ولا يُنسَخ** (§0.11): يحكم المنتج التعليمي ومنهاجه، ولا يحكم هذا المنتج B2B المستقلّ — ⛔ **ولا يستعير أحدهما دليلَ الآخر.**

---

## 0.20. Secret Capture Constitution (D-268) — السرّ يُلتقط عند كل باب، أو لا يُقال إنه ملتقَط

> **القانون:** [`.memory/secret_capture_constitution.md`](.memory/secret_capture_constitution.md) · **الحالة:** [`.memory/secret_capture_truth.md`](.memory/secret_capture_truth.md) · **المصدر الواحد:** [`config/secret_catalog.json`](config/secret_catalog.json) · **الفارض:** `scripts/fitness/check_secret_capture_parity.py` (إلزامي في `guardrails`).

**المصدر — قياسٌ لا مبدأ (2026-08-19 · ISS-191):** طُلب التقاط `HONCHO_API_KEY` «آلياً 100% مثل Supabase وOpenRouter»، فتبيّن أنّ «مثل OpenRouter» **ليست شيئاً واحداً**: السرّ يعبر **عشرة أبواب** والأبواب لا تتّفق. `SUPABASE_EDGE_FUNCTION_URL/KEY` يُحقَنان في `supervisor.sh` ويُوثَّقان في `secrets.env.example` **ويغيبان عن `devcontainer.json:remoteEnv`** — فضبطُهما كسرَّي Codespaces **لا يصل الحاوية أبداً**. و`TAVILY_API_KEY` يعبر ستّة أبوابٍ **بلا حقلٍ في `AppSettings`** فكان يُقرأ بـ`os.environ` في موضعين داخل `app/`، خرقاً لقاعدة §6 التي كانت **نثراً بلا فارض** (صنف D-188). و`FIRECRAWL_API_KEY` يُقرأ في `app/` و**لا بابَ يلتقطه** فيقرأ `None` دائماً.

**الجملة الدستورية:** «**السرّ يُلتقط عند كلّ بابٍ مُعلَن، أو لا يُقال إنه ملتقَط. وبابٌ منسيّ يعني سرّاً حاضراً في الحساب وغائباً عن العملية — وهو أسوأ من غيابه، لأنه يُقرأ حضوراً.**»

- **الكتالوج مصدرٌ واحد، والأبواب مُعلَنة لا مُكتشَفة** (L1/L2 · نمط D-186/D-193/D-202 و`GATE_HOMES` في D-266): ⛔ قائمةٌ ثانية ممنوعة، وبابٌ حادي عشر يُضاف صراحةً. ⚠️ وأخطرُ بابٍ كاد يُنسى `docker-compose.codespaces.yml` — لأنّه **يشغّل المونوليث نفسه** خلافاً لـ`docker-compose.yml` الذي يستبعده عمداً (D-205).
- **التغطية كاملة وثنائية الاتجاه** (L3/L4): كلّ خانةٍ (سرّ × باب) مطلوبةٌ أو **غير منطبقةٍ بسببٍ منطوق** (⛔ الفراغ يُقرأ نجاحاً — D-206 L11)؛ ومفتاحٌ خارجي عند بابٍ بلا صفٍّ في الكتالوج ⇒ CI أحمر. سرٌّ خفيٌّ أسوأ من ناقص: الناقص يُلاحَظ.
- **قارئٌ قانوني واحد** (L5): ⛔ لا `os.environ` لسرٍّ مُكتلَج في `app/` (§6)، والدَّين المُجمَّد **فارغ** ويتقلّص في الاتجاهين. **الاستثناء الوحيد المنطوق** حزمة `app/core/settings/` — هي القارئ بالتعريف، وقراءتها وقت الاستيراد قانونٌ مكتوب في §0 لا سهو.
- **الأنماط مُشتقّة، والبوّابة تشهد بما قرأت فقط** (L6/L10 · يمدّد D-192 وD-208): `check_no_committed_secrets` تقرأ أشكال المفاتيح من الكتالوج — قبل ذلك كانت تعرف شكل مفتاح OpenRouter وتجهل ما يُضاف بعده، فمفتاح Honcho يمرّ بلا اعتراض. وملفٌّ يتعذّر تحليله يُبلَّغ عنه انتهاكاً (⛔ لا `except SyntaxError: return []`).
- **الإضافة لا الاستبدال**: يمدّد D-188 · D-192 · D-206 L11 · D-265 L8 · D-266، وهو **الفارض الأوّل** لقاعدة §6.

---

## 0.21. Ambient Cognitive Identity Constitution (D-269) — الطبقة الخامسة تُقرأ ولا تحكم

> **القانون:** [`.memory/ambient_identity_constitution.md`](.memory/ambient_identity_constitution.md) · **المواصفة:** [`docs/architecture/AMBIENT_COGNITIVE_IDENTITY.md`](docs/architecture/AMBIENT_COGNITIVE_IDENTITY.md) · **الحالة:** [`.memory/ambient_identity_truth.md`](.memory/ambient_identity_truth.md) · **الفارض:** `scripts/fitness/check_ambient_identity.py` (إلزامي في `guardrails`).

**المصدر (قرار المالك 2026-08-19 · ISS-192/ISS-193):** مفتاح `Honcho` — طبقةُ نمذجةِ مستخدمٍ لطرفٍ ثالث (`workspace` · `peer` · `session` · `dialectic`) — دخل المستودع، وهو يلامس §0.12 و§0.14 في **صميمهما**، على منصّةٍ تخدم قاصرين. **المُثبَت حيّاً:** `POST https://api.honcho.dev/v3/workspaces/list` ⇒ **200** (مساحة العمل `ETAALIM`)، و`v2`/`v1` ⇒ **404** — فالإصدار بيانٌ مقيس لا تخمين. **والخطر ليس توصيلاً خاطئاً بل تدريجياً**: سطرٌ يرسل مُعرَّفاً، ثمّ مقتطفاً «للسياق»، ثمّ تعبر محادثات الطلبة — وهو شكلُ ISS-146 (٢٨ صفّاً قبل أن يلاحظ أحد) وISS-145 (تدهورٌ من ٣٦٫٦٪ إلى ٣٫٤٪ بلا قرار).

**الجملة الدستورية:** «**الطالب يُنمذَج داخل المنصّة أوّلاً. وأيّ نمذجةٍ خارجها طبقةٌ خامسة بمالكٍ واحد — تُقرأ ولا تحكم، وتُثبَت بمسبارٍ حيّ لا بمفتاحٍ موجود.**»

- **مالكٌ واحد لكلّ طبقة** (L1 · D-229): Honcho **طبقةٌ خامسة متمايزة**، لا مالكٌ ثانٍ لأيٍّ من الأربع. ⛔ `customer_messages` كاتبُها المونوليث وحده (§6.5). والسبب مقيس: طبقةٌ بمالكَين أنتجت **٢٦ انفجار كتابةٍ مزدوجة في ٥٢ صفّاً** (يونيو 2026).
- ⛔ **الحجب بنيويٌّ لا مُرشِّح، والطبقة تُقرأ ولا تحكم** (L2/L3 · يمدّد D-113/D-196): لا يعبر هذا المسار **حرفٌ واحد** من نصّ المحادثة، والمنعُ **بالنوع** — عقد الطبقة لا يحمل حقلاً يمكن أن يحمل محتوى (مُرشِّحٌ يُعدَّل بسطر، ونوعٌ بلا حقلٍ يُراجَع). ومخرَجُها لا يقرّر نيّةً ولا مستوى دعمٍ ولا محتوى ردّ: الحقيقة من المحرّكات الرمزية (§0.5)، والذاكرة التربوية من `TutorState`/BKT.
- **العزل والبرهان الثلاثي على الطرف الثالث** (L4/L5 · D-074 · D-245): كلّ نداءٍ معزولٌ بمهلةٍ صريحة وفشلُه يُبتلَع — ⛔ لا يكسر دور طالبٍ أبداً. ومفتاحٌ في البيئة **ليس قدرة**: المسبار الحيّ هو الساق الثالثة، يظهر في `/api/security/health` ويُشغَّل في `live-e2e`.
- **الحالات قائمةٌ مغلقة** (L6): `reachable` · `unauthorized` · `unreachable` · `not_configured`. ⛔ لا عبارة ضبابية (نمط D-267 L6)، و⛔ `not_configured` **ليست صحّة** — هي «لا نعرف» (D-215).
- **`SEAM` تُفحَص في الاتجاهين** (L7 · قاعدة D-210): مسارُ الكتابة `SEAM` **بصفر كود**، ووحدةٌ مُصنَّفة كذلك ولها كود ⇒ CI أحمر. وشرطُ فتحه **ثلاثةٌ معاً**: موافقةُ الوليّ بنيويّاً (نمط D-195) · تحديث `DATA_POLICY.md`/`SAFEGUARDING.md` · بوّابةٌ تُثبت أنّ المُرسَل مُشتقٌّ ومجهول.
- **صفر تبعيةٍ جديدة وحدّ المصداقية** (L8/L10 · D-189 · D-227 · قفل D-263): ⛔ لا `honcho-ai` — النداء عبر `shared/http_client.correlated_client`، وSDK يبني عميلَه فيقطع سلسلة الأثر ويوسّع سطح الهجوم على منصّةٍ تخدم قاصرين. و⛔ لا يُقال إنّ المنصّة «تتذكّر الطالب عبر Honcho» (لا يُكتب فيها شيء)، ولا يُنسَب إليها أثرٌ تعليمي.
- **مقعد `deepseek-harness`** ([`ADR-010`](docs/adr/ADR-010-deepseek-harness-adoption.md) · [`EXTENSION_SEAMS.md`](docs/architecture/EXTENSION_SEAMS.md) §10): `SEAM` **بصفر كود**. ⛔ **قفل D-187 يُعاد تأكيده لا يُخفَّف** — لا توصيل مُخطِّطٍ أو نموذجٍ بالأدوات قبل `M1→M4`؛ والصندوق يشغّل `python`/`pip`/`git`/`npm` والمستخدمون قاصرون. و⛔ **لا سُلَّم ثالث**: حلقتُه لا تنافس §0.13 ولا الطبقات التسع (D-228)، ودرسُ Kagent (D-173) ينطبق حرفياً.
- **الإضافة لا الاستبدال**: يمدّد D-229 · D-226 · D-113/D-196 · D-074 · D-245 · D-189 · D-227/D-263 · D-187 — ولا يلغي منها قانوناً واحداً.

---

## 0.22. Delivery Standards Constitution (D-270) — الدليل قبل الدمج

> **القانون:** [`docs/architecture/DELIVERY_STANDARDS.md`](docs/architecture/DELIVERY_STANDARDS.md) ·
> **الحالة:** [`.memory/delivery_standards_truth.md`](.memory/delivery_standards_truth.md) ·
> **السجلّات:** `docs/governance/{SUPPLY_CHAIN,CREDIBILITY_LIMIT,NEGATIVE_PROOFS,MAGIC_STRINGS}.json` ·
> **الفوارض:** `check_supply_chain` · `check_config_credibility` · `check_gate_negative_proof` ·
> `check_no_magic_strings` · `check_governance_registry` · `validate_pr_description` ·
> `validate_issue_readiness`. مؤشِّر فقط — العقد لا الموسوعة.

**المصدر (قرار المالك 2026-08-19 · ISS-194):** معايير `Houssam-lab/openhands` — **إضافةً
لا حذفاً**. والقياس أظهر أنّ الفجوة ليست في الهندسة بل في **العملية**: كل بوّابةٍ على
القرص مُنفَّذة (D-266)، وما يحكم **دخول** التغيير غائبٌ أو ميّت (صفر فارضٍ لوصف الدفعة
في ١٢ workflow · فارضٌ محلّي يناقض CI في ٧٩١٧ سطراً · إعدادُ تبعياتٍ يصف نظاماً آخر).

**الجملة الدستورية:** «**المستودع يفرض على الكود برهاناً ثلاثياً ولا يفرض شيئاً على ما
يدخله. وبابٌ بلا حارسٍ يُبطل كلّ حراسةٍ خلفه.**»

- **L1** الدليل قبل الدمج — أمرٌ ومخرَجه («اختبارات الوحدة لا تكفي») ودليل إعادة إنتاجٍ
  لكل إصلاح عطب (رفعُ D-186 من الاختبار إلى الدفعة). ⛔ **قسم `HUMAN:` ملك الإنسان**.
- **L2** البلاغ يُولَد جاهزاً أو لا يُطوَّر — `ready-for-dev` **تديره الآلة** (ISS-145
  أُغلقت على معيارٍ خطأ لأنّ شرط النجاح لم يُكتب مُسبَقاً).
- **L3** عنوان الدفع عقد — Conventional Commits بقائمةٍ مغلقة، بلا تبعيةٍ خارجية.
- **L4** البوّابة تُثبِت أنّها **تحجب** — ⛔ اختبارٌ يتوقّع نجاحها يُثبِت أنّها تعمل
  لا أنّها تحجب. ISS-148 مُحوَّلةً من حادثةٍ إلى صنف.
- **L5** الحرفية السحرية ممنوعة — موطنٌ واحد لكلّ مُعرِّف؛ تعميمُ D-185/186/191/193.
- **L6** سلسلة التوريد تُبرَّد وتَصِف الموجود — لا مجلّدٍ وهمي ولا منظومةٍ بلا تغطية.
- **L7** الفارض المحلّي مطابقٌ لـCI أو مُعلَنٌ ميتاً — ⛔ المخالفة **أسوأ من الغياب**:
  الغياب يُلاحَظ، والمخالفة مصيدة تُحمِّر دفعة من يتّبع الوثائق.
- **L8** حدّ المصداقية يمتدّ إلى ما يُشحَن (تمديد D-227)، والمصدر **واحد** لا رابع.
- **الإضافة لا الاستبدال**: كل دستورٍ قائم يبقى سارياً بكامله.

---

## 0.23. Open Agent Standards Constitution (D-271) — المهارة تُقاس، والتقنية تدخل بقرار

> **القانون:** [`docs/architecture/OPEN_AGENT_STANDARDS.md`](docs/architecture/OPEN_AGENT_STANDARDS.md) ·
> **الحالة:** [`.memory/agent_standards_truth.md`](.memory/agent_standards_truth.md) ·
> **السجلّات:** `docs/governance/{AGENT_SKILLS,EXTERNAL_STANDARDS_REGISTRY}.json` ·
> **الفوارض:** `check_agent_skills_spec` · `check_external_standards`.

**المصدر (قرار المالك 2026-08-19 · ISS-195):** عشرة مستودعاتٍ من الشركات التي تقف وراء
أشهر النماذج. وجودُ كلٍّ منها **مُتحقَّقٌ بـ`git ls-remote`** لا نقلاً عن منشور؛ وأكثرها
**كتبُ أمثلةٍ لا معايير مستودع**، واثنان يحملان مواصفةً قابلة للفرض.

**الجملة الدستورية:** «**المهارة وحدةٌ قابلة للقياس لا مجلّدٌ لطيف. والتقنية تدخل
بقرارٍ مكتوب لا بإعجاب.**»

- **L9** المعيار المفتوح (`agentskills.io`) لكلّ ما تحت `.claude/skills/`؛ ووصفٌ بلا
  شرط تشغيلٍ = مهارةٌ لا تُستدعى.
- **L10** «مهارة» كلمةٌ بمعنيين مُعلَنين: `BaseSkill` (D-179 · مسار الطالب) و
  `Agent Skill` (توجيه وكيلٍ لغوي). ⛔ لا سُلَّم ثانٍ خفيّ (D-209 — أنتج ISS-139).
- **L11** **الساق السادسة**: تقييمٌ مُصرَّح (`verified_on` + `evidence`) أو
  `unevaluated` بسببٍ منطوق. ⛔ لا تقييم LLM في مسار الطالب (§0.5) ولا ادّعاء أثرٍ
  تعليمي (قفل D-263).
- **L12** التبنّي بقرارٍ مكتوب — **ما رُفض ولماذا** حقلٌ إلزامي كـ«ما اُستُعير»، والفحص
  في الاتجاهين: `ABSENT`/`SEAM` وله كودٌ ⇒ CI أحمر. وُلد من **ISS-193** حرفياً.
- ⛔ **قفل D-187 يُعاد تأكيده**: `deepseek-harness` و`grok-build` وكيلا تنفيذ أدوات —
  لا توصيل قبل `M1→M4`؛ والمستخدمون قاصرون.
- **الإضافة لا الاستبدال**: D-270 وكلّ ما سبقه يبقى سارياً.

---

## 0.24. Agentic Design Principles Constitution (D-272) — التنسيق يُختار لمطابقة بنية المهمة، لا لجماله

> **القانون:** [`docs/architecture/AGENTIC_DESIGN_PRINCIPLES.md`](docs/architecture/AGENTIC_DESIGN_PRINCIPLES.md) ·
> **الحالة:** [`.memory/agentic_design_principles_truth.md`](.memory/agentic_design_principles_truth.md) ·
> **الفارض:** `check_agentic_design_principles` (سلكه `guardrails` في `ci.yml`).

**الجملة الدستورية:** «**التنسيق يُختار لمطابقة بنية المهمة — لا لجماله. والوكيل الواحد هو
النقطة المرجعية التي تُقاس عندها كل بنيةٍ أخرى، والأداء يُقاس بأقل تعقيدٍ وتكلفةٍ ممكنة.**»

- **L1** الوكيل الواحد أولًا، ودائمًا كخط أساسٍ مُثبتٍ (**`single_agent_baseline`**) على نفس
  المعيار الحيّ قبل أي تعددٍ. ⛔ لا بنيةٌ متعددةٌ بلا رقم خط أساس = CI أحمر.
- **L2** **عتبة 45%**: فوقها التعدد تحسينٌ غير مثبتٍ يحتاج `justification_ar` مقاسًا؛ تحتها البنية
  الأولى المسموحة **مركزيٌّ بمرجِّعٍ واحد**.
- **L3** تصنيفٌ إجباري لكل مهمةٍ: `decomposable` · `sequential` · `tool_count` — تسلسليةٌ شديدةُ
  الاعتمادية تحظر البنيةَ المتعددة مبدئيًا (القياس: −39% إلى −70% لكل البنى على PlanCraft).
- **L4** الأنظمة المستقلة لا تقرأ وكلاؤها مسودات بعضهم؛ أي مساراتٍ مستقلةٍ تمرّ عبر
  `central_verifier` قبل الدمج.
- **L5** إعادة معايرةٍ (`last_recalibration`) بعد كل ترقيةٍ جوهريةٍ للنموذج — تحسينُ الأساس
  قد يجعل التعددَ أقل جدوى. ⛔ ترقيةٌ بلا إعادة قياسٍ = دفعةٌ مخالفةٌ.
- **L6** النتيجة أفضلُ بأقل تعقيدٍ وتكلفةٍ: `tokens_per_task_ratio` إلزاميٌّ، وحدٌّ أقصى
  **3–4 وكلاءٍ** عند ضيق الميزانية.
- **L7** البنية لا تُنسَخ بين النطاقات (`domain_measured`) — الأفضل في المالية (مركزيّ، +80.8%)
  هو عينُه الذي تراجعت به المستقلةُ في التخطيط.
- **الإضافة لا الاستبدال**: D-271 وكلّ ما سبقه يبقى سارياً. تعديل هذا الدستور = ADR + بوّابةٌ خضراء.

---

## 1. What This Project Does

CogniForge is an educational AI platform for Algerian high-school students preparing for the Baccalaureate exam. Students chat in Arabic, French, or Darija and receive tutoring in math, physics, and sciences. The backend is a FastAPI monolith.

**Supported runtime environments**: the project is environment-agnostic and runs on both:

| Environment | Frontend port | How it picks the port |
|---|---|---|
| **GitHub Codespaces** (primary) | **5000** | `supervisor.sh` sets `FRONTEND_PORT=5000` (default). `server.js` reads `PORT \|\| FRONTEND_PORT \|\| 3000`. `devcontainer.json` sets `onAutoForward: openBrowser` for port 5000 — browser tab opens automatically. |
| **Replit** | **5000** | `frontend/package.json` script `"dev": "next dev --hostname 0.0.0.0 --port 5000"` is used directly |

في الحالتين الواجهةُ الخلفية على **8000**. أمّا الخدمات المصغّرة فلها **مساران حقيقيان**:
`.devcontainer/supervisor.sh` يُقلعها كعمليات uvicorn (STEP 4D→4L) عند توفّر الأسرار،
و`docker compose -f docker-compose.yml up -d` يصف **28 خدمة**. ⚠️ **مسار uvicorn هو
المُثبَت باستمرار** (الخدمات تُقلَع فيه، واختبارات العقود تبني تطبيقاتها الحقيقية في كل
PR)؛ أمّا Docker فآخر تشغيلٍ كامل له كان **2026-07-19 بخمس خدمات مستثناة** (D-172)،
ولا يُقلِع CI حاويةً إلّا في وظيفة `event-stack-live` (D-204 — Redpanda وTemporal فقط).
الثماني خدمات التطبيقية **غير مُقلَعة في CI** — لا تُقرأ الطوبولوجيا (ب) كأنّها محروسة.

**البنية التحتية المصاحبة:** Grafana :3001 · Prometheus :9090 · Redis :6379 (العملية تعمل
لكن التطبيق يستعمل `InMemoryCache` ما لم يُضبَط `REDIS_URL`) · PostgreSQL عبر Supabase
(PgBouncer :6543 / مباشر :5432 — asyncpg يستعمل :5432).

**سجلّ الكوارث المُصلَحة ليس هنا.** كل «Known fix applied» مؤرَّخ (ISS-036 → ISS-093 ·
D-WS-\*) يعيش في [`.memory/issues.md`](.memory/issues.md) مع الجذر والدليل الحيّ، وكل قرار
معماري في [`.memory/decisions.md`](.memory/decisions.md). اللقطة المؤرَّخة التي كانت هنا:
`docs/archive/constitution-history/CLAUDE-SECTIONS-1-3-6.6-FULL.md §أ`.

> **قاعدة D-188:** الدستور يحمل **القوانين الدائمة** فقط. أي فقرة تبدأ بـ«Known fix applied
> <تاريخ>» أو «Step N applied <تاريخ>» تخصّ `.memory/`، لا هذا الملف — سردٌ مؤرَّخ في عقدٍ
> دائم يتحوّل حتماً إلى كذبٍ بمرور الوقت (هذا بالضبط ما حدث بين 2026-05-09 و2026-07-29).

---

## 2) خريطة التنفيذ (Execution Topology)

```bash
# Frontend
# - Codespaces: supervisor.sh launches the Next.js dev server on FRONTEND_PORT=5000
# - Replit:     cd frontend && npm run dev   (port 5000 from package.json)
# - Manual:     cd frontend && npm run dev -- --port <PORT>
cd frontend && npm run dev

# Health check
curl -s http://localhost:8000/health | python -m json.tool
```

---

## 3. Architecture at a Glance

```text
Runtime topology — **طوبولوجيتان حقيقيتان، لا واحدة** (وثِّق أيّهما تقصد):

  (أ) Codespaces / uvicorn (`.devcontainer/supervisor.sh` — الافتراضي في التطوير)
      frontend :5000 · monolith :8000 · user :8001 · planning :8002 · conversation :8003
      orchestrator :8006 · research :8007 · reasoning :8008 · content-retrieval :8009
      foundations :8010 · notation :8011 · Prometheus :9090 · Grafana :3001

  (ب) Docker Compose (`docker-compose.yml` — **وجهةُ** الهجرة لا ما يخدم؛ **28 خدمة**،
      حزمة الأحداث وحدها محروسة حياً — D-204؛ وكل الصور مبنيّة ومُثبَتة الاستيراد — D-205)
      api-gateway :8000 · planning :8001 · memory :8002 · user :8003 · observability :8005
      orchestrator :8006 · research :8007 · reasoning :8008 · auditor :8009
      conversation :8010 · notation :8011 · frontend :3000 · Postgres مستقلّة لكل خدمة

  ⚠️ المنافذ تختلف بين (أ) و(ب) لخمس خدمات (planning · memory · user · conversation ·
     auditor). المصدر القانوني للمنافذ المحكومة ببوّابة:
     `docs/architecture/PORTS_SOURCE_OF_TRUTH.json` + `config/microservice_catalog.json`.
  ⛔ **المونوليث غائبٌ عن (ب) عن قصد** (Strangler المرحلة 3 — D-205): `api-gateway`
     بروكسي بلا مسارٍ إليه، وثلاث بوّابات تمنع إضافته، وبيته `legacy.yml:8004`. وطرح
     بديله **0%** فما يخدم اليوم هو (أ). **البناء ليس تشغيلاً**: لا حاوية تطبيقية في CI.

مسار دور الطالب (كلتا الطوبولوجيتين):

  Browser → Next.js → /api/* → FastAPI monolith :8000
    └── /api/chat/ws  (WebSocket — المفتاح `question`)
          └── OrchestratorClient.chat_with_agent()
                ├── preempts حتمية (تحية · رموز · احتمالات — بلا LLM)
                ├── orchestrator-service :8006  ← القلب الإلزامي للتوليد (D-112)
                └── سلسلة سقوط محلية (تُقاس، لا تُخفى)

العقود: 15 عقد OpenAPI في `docs/contracts/openapi/` تحرسها `check_openapi_parity` (15/15 — يشمل المونوليث، D-231).
التفصيل الحيّ: `.memory/architecture.md` · `.memory/runtime_truth.md`.
الطوبولوجيا المؤرَّخة 2026-05-11: `docs/archive/constitution-history/CLAUDE-SECTIONS-1-3-6.6-FULL.md §ب`.
```

1. `app/*` = بوابة التركيب والتنسيق العام (Control Plane).
2. `microservices/*` = وحدات أعمال مستقلة (Execution Plane).
3. `docs/architecture/*` = الدستور المعماري وقرارات التصميم.
4. `.memory/*` = ذاكرة تشغيلية مختصرة يجب أن تعكس الواقع التنفيذي الفعلي.

---

## 4) مخاطر معمارية حالية

أربعة مخاطر دائمة لكلٍّ فارضٌ آلي اليوم — التفصيل في
[`ENGINEERING_DOCTRINE.md`](docs/architecture/ENGINEERING_DOCTRINE.md): انحراف الوثائق ·
الاقتران الخفي بنماذج بدل عقود · تسرّب منطق الأعمال إلى الـrouters · تباين جاهزية الخدمات.

---

## 5. Safe Areas to Modify

```
app/services/chat/local_graph.py    — add LangGraph nodes/edges
app/api/routers/content.py          — content endpoints
app/core/prompts.py                 — system prompts
app/services/system/                — system utilities
frontend/app/components/ChatInterface.jsx
frontend/app/components/AgentTimeline.jsx
tests/                              — add tests freely
scripts/                            — helper scripts
docs/                               — documentation
```

---

## 6. Common Pitfalls

### NEVER use `os.environ` directly in app code
```python
# ❌ Wrong
import os
db_url = os.environ["DATABASE_URL"]

# ✅ Correct
from app.core.config import get_settings
db_url = get_settings().DATABASE_URL
```

### NEVER use synchronous SQLAlchemy
```python
# ❌ Wrong — blocks the event loop
user = db.query(User).filter_by(email=email).first()

# ✅ Correct
from sqlalchemy import select
result = await db.execute(select(User).where(User.email == email))
user = result.scalar_one_or_none()
```

### NEVER omit Codespaces origins from `allowedDevOrigins`
```javascript
// ❌ Wrong — Next.js 15+ blocks Codespaces proxy with ERR_HTTP_RESPONSE_CODE_FAILURE
allowedDevOrigins: ['*.replit.dev']

// ✅ Correct — include all hosting environments
allowedDevOrigins: [
    '*.replit.dev', '*.replit.app',
    '*.app.github.dev', '*.preview.app.github.dev',  // GitHub Codespaces
    '*.gitpod.io',                                    // Gitpod / Ona
]
```

### NEVER assume microservices are reachable
```python
# In Codespaces (default devcontainer), ALL of these fail with ConnectError:
# http://orchestrator-service:8006  → Docker DNS — not running
# http://user-service:8000          → not running
# http://research-agent:8007        → not running

# Only the `web` container runs by default (see .devcontainer/docker-compose.host.yml).
# LangGraph (local_graph.py) is the REAL handler — always falls through to it.
# To wake the microservices: `docker compose -f docker-compose.yml up -d` (separate stack).
```

### NEVER change the auth_persistence.py RETURNING pattern
```python
# ❌ Wrong — lastrowid doesn't work reliably with asyncpg/PostgreSQL
cursor = await conn.execute(insert_query)
user_id = cursor.lastrowid

# ✅ Correct — what's already there
result = await conn.execute(
    text("INSERT INTO users (...) VALUES (...) RETURNING id")
)
user_id = result.scalar()
```

### Port quirk
```python
# settings auto-converts PgBouncer port 6543 → 5432
# Don't override this behavior in database.py
```

### NEVER call `cognitive_engine.memorize()` without a None guard

```python
# ❌ Wrong — a test / DI seam may inject cognitive_engine=None.
self.cognitive_engine.memorize(prompt, context_hash, chunks)

# ✅ Correct — defensive null guard (simple_client.py)
if last_message.get("role") == "user" and self.cognitive_engine is not None:
    self.cognitive_engine.memorize(prompt, context_hash, chunks)
```

**Rule (corrected D-180 — the old "stub returns None" claim was false):**
`get_cognitive_engine()` returns a **real Arabic-aware `CognitiveResonanceEngine`
singleton** (`cognitive_cache.py`), not `None`. The None-guard stays as **defensive
code** (a test or DI seam may inject `None`) — do not remove it. The engine is now
ACTIVE: `memorize()` stores every successful user turn and `recall()` is wired as a
resilience fallback in the gateway (see the D-180 cache rule in §6.7).

### NEVER pass `postgresql://` to `create_async_engine` — use `postgresql+asyncpg://`

```python
# ❌ Wrong — SQLAlchemy maps postgresql:// to psycopg2 (sync driver)
# Raises: InvalidRequestError: The asyncio extension requires an async driver
create_async_engine("postgresql://user:pass@host/db")

# ✅ Correct — explicit asyncpg driver + strip sslmode (asyncpg uses connect_args for SSL)
create_async_engine("postgresql+asyncpg://user:pass@host/db")
```

**In supervisor.sh / automations.yaml** — convert at launch time:
```bash
_url="${DATABASE_URL/postgresql:\/\//postgresql+asyncpg://}"
_url=$(echo "$_url" | sed 's/[?&]sslmode=[^&]*//')
```

This affects `orchestrator-service` and `planning-agent`. The monolith uses `aiosqlite`/`asyncpg` correctly via `app/core/database.py`. The microservices receive `DATABASE_URL` from the environment which always has the bare `postgresql://` scheme from Supabase.

### NEVER omit `TAVILY_API_KEY` from `docker-compose.yml` services that use web search

```yaml
# ❌ Wrong — WebSearchFallbackNode silently skips search; SuperSearchOrchestrator raises ImportError
environment:
  - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}

# ✅ Correct — safe default (empty string) prevents docker compose failure when key absent
environment:
  - OPENROUTER_API_KEY=${OPENROUTER_API_KEY}
  - TAVILY_API_KEY=${TAVILY_API_KEY:-}
```

**Affected services**: `orchestrator-service` (port 8006) and `research-agent` (port 8007). Key format must start with `tvly-`. MCP URL format (`https://mcp.tavily.com/mcp/?tavilyApiKey=tvly-...`) is auto-sanitized in `readiness.py` and `super_search.py`.

### NEVER share a CollectorRegistry between microservices

```python
# ❌ Wrong — يُسبب تعارضاً إذا عملت الخدمتان في نفس الـ process (اختبارات)
from prometheus_client import Counter
requests = Counter("cogniforge_user_requests_total", "...")  # يستخدم REGISTRY الافتراضي

# ✅ Correct — registry مستقل لكل خدمة (نمط prom_metrics.py)
from prometheus_client import CollectorRegistry, Counter
_REGISTRY = CollectorRegistry()
requests = Counter("cogniforge_user_requests_total", "...", registry=_REGISTRY)
```

**Rule**: كل microservice يجب أن يستخدم `CollectorRegistry()` مستقلاً. استخدام `REGISTRY` الافتراضي يُسبب `ValueError: Duplicated timeseries` عند تشغيل اختبارات متعددة في نفس الـ process.

### قواعد البيئة المرحلية — موطنها `.memory/`

ثلاث قواعد كانت هنا (`dependsOn` في أتمتة Ona · غياب Docker في devcontainer · علم
`OUTBOX_RELAY_ENABLED` بعد المرحلة 4) نُقلت حرفياً إلى
[`.memory/runtime-rules.md`](.memory/runtime-rules.md). سببُ النقل هو قاعدة D-188
نفسها: قاعدةٌ تبدأ بـ«after Step N» أو تصف بيئةً بعينها ليست قانوناً دائماً — تتقادم
ثمّ تكذب على كل وكيل يقرأ العقد. الدستور يحمل ما لا يتقادم.

### NEVER use flat keyword matching for exercise retrieval intent detection

```python
# ❌ Wrong — ISS-038: triggers retrieval for ANY question containing "تمرين"
# regardless of context. "اشرح الجزء أ من هذا التمرين" → returns probability exercise.
retrieval_hints = ("تمرين", "تمارين", "درس", "احتمالات", "بكالوريا", ...)
recognized = any(hint in normalized for hint in retrieval_hints)

# ✅ Correct — two-phase intent classifier in exercise_retrieval.py:
# Phase 1: explanation/help intent → cancel retrieval (highest priority)
# Phase 2: explicit retrieval patterns (BAC, numbered, year+exercise) → trigger
# Default: no retrieval → fall through to LangGraph
from app.services.capabilities.exercise_retrieval import detect_exercise_retrieval, ExerciseRetrievalRequest
decision = detect_exercise_retrieval(ExerciseRetrievalRequest(question=question))
# decision.recognized is True ONLY for explicit retrieval requests
# decision.reason explains why: "explanation_intent_detected" | "retrieval_intent_detected" | "no_clear_retrieval_intent"
```

**Rule**: When adding new retrieval trigger keywords, always add corresponding explanation-intent negation patterns. The explanation-intent list takes priority. When in doubt, do NOT trigger retrieval — LangGraph handles ambiguous questions better than a static knowledge base lookup.

---

## 6.5 Architecture Truth and Persistence Rules

**Single writer. Single terminal frame. No silent failure.** These are operational laws, not aspirations.

### Persistence authority (D-006)
- **Monolith owns `customer_messages` and `admin_messages`.** The Orchestrator microservice MUST NOT write unless the Monolith explicitly delegates via `compatibility_facade=True` and the Orchestrator signals back `persisted: true` on its terminal event.
- **User message** is always written by the Monolith at the WS entry point (`app/api/routers/customer_chat.py:save_message(USER)` / `app/api/routers/admin.py`). One write, no exceptions.
- **Assistant message** write is conditional:
  - `orchestrator_persisted == True` → Monolith **SKIPS** the local write and treats the turn as persisted.
  - `orchestrator_persisted == False` (signal absent or explicitly false) → Monolith does a **fail-safe write** with up to 2 retries. Absence of signal = failure.
  - If the fail-safe write also fails after retries → log `[CRITICAL_DATA_LOSS]` and surface a single terminal `error` to the client. Never claim success.

### How `persisted` is interpreted
- Source of truth: `app/infrastructure/clients/orchestrator_client.py:_normalize_stream_event` preserves `event["persisted"]` through the envelope so the Monolith router can read it on the terminal event (`complete` or `assistant_final`).
- Detection point: `app/api/routers/customer_chat.py` and `app/api/routers/admin.py` check `normalized_event.get("persisted") is True` while trapping the terminal event into `pending_terminal_event`.

### Terminal event guarantee (ISS-016 / ISS-017)
- Each turn emits **exactly one** terminal frame: either `assistant_final` (success) or `error` (failure). The helper `_emit_terminal_frames()` in both routers is the single emitter.
- `persisted` event is emitted **only after** a successful save (orchestrator-side or Monolith fail-safe).
- `shared/chat_protocol/event_protocol.py:normalize_streaming_event` passes `complete`, `persisted`, and `conversation_init` through unchanged. Do not add type coercion for these — it breaks terminal-event detection.

### Fallback path (`OrchestratorClient.chat_with_agent`)
- The fallback chain in `app/infrastructure/clients/orchestrator_client.py` (file-intelligence → exercise-retrieval → LangGraph → general-chat) **does not persist**. It returns content; the Monolith router persists.
- Each fallback emits `assistant_delta` followed by `assistant_final`. None of them set `persisted: true` — that flag is reserved for the real Orchestrator microservice after a confirmed `INSERT … COMMIT`.
- A failed fallback returns `None`; the chain advances. The terminal `error` is emitted once, by `_emit_terminal_frames` in the router, never silently.

### Things that MUST NOT change without an ADR
- The user message is written by the Monolith at the WS entry. Do not move this write into a service or into the Orchestrator.
- The `compatibility_facade=True` context flag is the handshake. Removing it re-enables Orchestrator user-message writes → dual-write.
- `_emit_terminal_frames()` is the only place that emits `assistant_final`/`error` and `persisted`. Do not duplicate this logic inline.
- The `persisted` key on terminal events is the single source of truth for write coordination. Do not rename, type-cast, or normalize it away.

### What to test before any merge that touches chat persistence
1. Normal path: orchestrator persists → Monolith skips → exactly one terminal `assistant_final` + one `persisted` event reach the client.
2. Fallback path: orchestrator unreachable → fallback runs → Monolith fail-safe writes → exactly one terminal frame + one `persisted` event.
3. Dual-write protection: with orchestrator awake AND `persisted=True`, only one row exists in `customer_messages` for that turn.
4. Terminal event guarantee: any failure path (DB error, empty response, stream interruption) ends with a single `error` frame — never a hang.
5. No silent failure: fail-safe write failure produces `[CRITICAL_DATA_LOSS]` log AND a terminal `error` to the client.

---

## 6.6 Architecture Truth and Runtime Rules (Truth Table)

> **The golden rule:** code presence ≠ runtime usage. A capability is real ONLY when proven by **import + call chain + runtime evidence**. Anything missing one of those three is treated as DORMANT or ZOMBIE until proven otherwise.
> **الحالات لا تُكتب هنا.** الجدول المرجعي الوحيد هو `.memory/runtime_truth.md` — يُحدَّث
> مع كل تغيير قدرة في نفس الـ PR (`python scripts/runtime_truth.py --update`).

### Status legend
- **ACTIVE** — import + call chain + runtime evidence all present.
- **ACTIVE (no-op without ENV_VAR)** — import + call chain present; runtime effect absent without a specific env var.
- **PARTIAL** — on a live chain but only via fallback, conditional, or non-default branch.
- **DORMANT** — code real, gated behind an external service not started by default.
- **ZOMBIE** — no live call chain from any production entrypoint. · **UNKNOWN** — insufficient evidence.

### طوبولوجيا الحقيقة الجارية — **المصدر الوحيد: `.memory/runtime_truth.md`**

> ⚠️ **قاعدة D-188 (2026-07-29):** كان هنا جدول حقيقة مؤرَّخ بـ**2026-05-09** بقي مُجمَّداً
> بينما تحرّك النظام شهرين ونصف — فصار **يكذب** على كل وكيل يقرأ الدستور (نموذج PRIMARY
> محظور أمنياً، Kagent المحذوف يُذكر كمكوّن حيّ، رسم الأوركستريتور يُوصَف DORMANT وهو
> ACTIVE افتراضياً منذ D-163). **لا يُعاد جدولُ حالاتٍ إلى هذا الملف أبداً.**
>
> **الجدول الحيّ:** [`.memory/runtime_truth.md`](.memory/runtime_truth.md) — تحرسه بوّابة
> `doc-integrity` (تماسك المراجع) وبوّابة `runtime-truth`
> (`scripts/runtime_truth.py --check` مقابل `.runtime/truth_table.lock.json`).
> **اللقطة المؤرَّخة 2026-05-09:** `docs/archive/constitution-history/CLAUDE-SECTIONS-1-3-6.6-FULL.md §ج`.

### الثوابت التي لا تتقادم (تبقى هنا لأنها عقد لا حالة)

**بروتوكول WebSocket (ISS-052 — قانون دائم)** — المحادثة تعمل عبر WebSocket **حصراً**:
لا وجود لـ`POST /api/chat/messages` (يُرجع 404). المفتاح `question` (لا `content` ولا
`message`؛ الخطأ ⇒ `"Question is required."`)؛ المصادقة `subprotocols=['jwt', TOKEN]`
(ترويسة `Authorization` ⇒ `NegotiationError`)؛ التدفّق
`conversation_init → assistant_delta* → assistant_final`؛ **إطار نهائي واحد لكل دور**
(`_emit_terminal_frames` — §6.5).

**سلسلة السقوط في `OrchestratorClient`** — `file_intelligence → exercise_retrieval(2.0) →
exercise_explanation_with_context(2.5) → LangGraph(3.0) → general_chat(4.0)`. لا طبقة منها
تكتب في قاعدة البيانات (§6.5: الكاتب واحد).

### First-check protocol before any change to the chat / agent stack

1. Open `.memory/runtime_truth.md` (authoritative — read its own header for the last verification date; never trust a date pasted anywhere else).
2. Ask: is the component I'm touching ACTIVE, PARTIAL, DORMANT, or ZOMBIE?
3. If **DORMANT/ZOMBIE** → editing dead code unless also wiring it into a live path.
4. If **ACTIVE/PARTIAL** → confirm call chain still holds after change.
5. Status updates require: file:line evidence + import path + call-chain trace.

---

*Closing rule:* **Any component without all three of `import` + `call chain` + `runtime evidence` from `app/main.py` is DORMANT or ZOMBIE. "Loaded but never invoked" is PARTIAL, not ACTIVE.**

---

## 6.7 Consolidated Permanent Rules (D-173 — full §6.x narrative archived)

> **جراحة التوثيق (D-173 Stage 6):** الأقسام §6.7 → §6.144 (السرد التفصيلي الكامل لكل قرار
> D-006 → D-172، ~11,250 سطراً) نُقلت حرفياً إلى
> **`docs/archive/constitution-history/CLAUDE-SECTIONS-6x-FULL.md`** (لقطة مُجمَّدة، تُقرأ
> للتاريخ لا تُحدَّث). هذا القسم يوحّدها في **قواعد دائمة مصنّفة بالمجال** — العقد لا الموسوعة
> (DOC-DEBT-001). كل قاعدة تحمل رقم قرارها للرجوع إلى الأرشيف. تعليقات الكود التي تستشهد بـ§6.xx
> تظل صالحة (لا إعادة ترقيم — الأرشيف يحفظها).

### أ) قانون التفكيك والمانيفستات (D-163→D-172)
- **كل نقل verbatim** (سلوك مطابق بالبايت)؛ **كل استخراج = سطر واحد** في المانيفست المناسب،
  والبوّابات/الاختبارات تقرأ **المصدر المُركَّب** عبر قارئ المانيفست. المانيفستات الستة:
  `TUTOR_SOURCE_FILES` · `BRAIN_SOURCE_FILES` · `API_SOURCE_FILES` · `DOCTRINE_SOURCE_FILES` ·
  `CUSTOMER_CHAT_SOURCE_FILES` · `GRAPH_SOURCE_FILES` (+ `BRAIN ⊆ TUTOR` مفروض CI).
- **ممنوع إعادة أي دالة/مرحلة مُستخرَجة** إلى ملفها الأصلي (عودة الـ God-file). العقل وحدة واحدة
- **قانون تفكيك بنية الاختبارات (D-258)**: `conftest.py` قشرة تسجيلٍ وتفويضٍ فقط (أسماء fixtures/hooks كما كانت — late-binding يحرس كل اختبار قائم) ومنطقها في حزمة `conftest_support/` شرائح نقية + مانيفست `_sources.py` — **pytest لا يفعّل autouse لfixtures معرَّفة في وحداتٍ مستوردة** (`_arg2fixturedefs` لا تُفعَّل) — هذا اكتشافٌ معمَّمٌ لا استثناء محلي: fixtures المسجّلة تبقى في الconftest، والمنطق في الشرائح، ومانيفستها مركّب يُقرأ قبل أي تغيير اختباري.
  (`probability_tutor_brain.py` جذر تركيب + 5 mixins)؛ الملفات المُفكَّكة لا تستورد أصلها أبداً؛
  إعادة التصدير بـ `# noqa: F401`.
- الفحوص **السلبية** (حظر وجود نصّ) تقرأ المصدر المُركَّب أيضاً — الفحص السلبي على ملف تقلّص محتواه
  يمرّ زوراً.

### ب) قانون الإقامة + late-binding (D-168)
- **قواعد إقامة FastAPI**: الـ `@router` handlers بمسارات literal تبقى في ملفها (بوّابة AST تقرأه
  وحده) — `routes.py` + `customer_chat.py:chat_stream_ws` لا تُستخرَج.
- **قاعدة late-binding**: رقِّع الوحدة التي **يعيش فيها المستدعي** — دالة مُنقولة تقرأ globals وحدتها
  الجديدة لا وحدة إعادة التصدير. أي monkeypatch على اسم مُعاد تصديره يستهدف وحدة موقع النداء.

### ج) قاعدة المرآة D-013 + فلتر D-102
- **D-013 (المرآة الثنائية)**: `_GREETING_PATTERNS`/`_EDUCATIONAL_PATTERNS` مُكرَّرة في
  `local_graph.py` **و** `path_observer.py`؛ أي تعديل يُطبَّق في النسختين في نفس الـ PR.
- **D-013 لسلسلة النماذج (D-174 — مصدر واحد + بوّابة حتمية)**: المصدر القانوني الوحيد للسلسلة هو
  `shared/ai_models/model_chain.py` (dep-free، مشترك بين العقلين). الحرفيات المُثبَّتة أمنياً تبقى
  في `app/core/ai_config.py` + `microservices/orchestrator_service/src/core/ai_config.py`
  (دفاع عميق ISS-079)، وبوّابة `scripts/fitness/check_model_chain_parity.py` (AST، تُشغَّل في
  guardrails) تُثبت أن العقلين == السلسلة القانونية — تكافؤ محروس آلياً بدل «حرّر النسختين يدوياً».
- **D-013 لسياسة الحجب (D-203 — مصدر واحد محروس)**: قاعدة D-113 يفرضها **عقلان** بنسختين (`answer_redaction_skill` · `overmind/response_sanitizer`)؛ انحرافُ نمطٍ واحد يعني مساراً يحجب الجواب ومساراً **يسرّبه**، والطالب لا يعرف أيّ عقلٍ أجابه. تحرسه `check_redaction_parity` (AST، ٦ حرفيات سياسة) — تكافؤ **المعنى** لا الشكل، بتجربة سلبية مُثبَتة.
- **D-102 (فلتر التاريخ)**: أي كاشف يقرأ `history` يُرشِّح `role in (user, assistant)` — رسالة
  system (برومبت النظام) ليست دليلاً من المحادثة أبداً (وإلا تسمّم التوجيه).

### د) قانون العقل التربوي (D-006 → D-160 — النظام ليس مُجيباً بل معلّماً)
- **الخدمات المصغرة + LangGraph + Skills = القلب الإلزامي للتوليد** (D-112): تعذّرها ⇒ `ORCHESTRATOR_REQUIRED`
  صريح، صفر سقوط صامت للتوليد المحلي (`REQUIRE_ORCHESTRATOR=1` افتراضي، `=0` rollback).
- **صفر LLM في مسار الأرقام**: كل الأرقام/الصحّة الاحتمالية من المحرك الرمزي الحتمي حصراً
  (`probability_skill` + `probability_tutor_brain`) — الـ LLM يُنتج **الفهم** (السرد السقراطي) لا **الحقيقة**.
- **طبقة الأسس النظرية (D-175)**: `app/core/foundations/` (dep-free، stdlib فقط) هي الركيزة الحسابية
  المُتحقَّقة — combinatorics · number_theory · logic · probability · information_theory · algorithms.
  كل بدائية ترفع `FoundationsError` عند خرق المجال (لا `0` مضلِّل). المصدر الموحّد للأعداد المُتحقَّقة
  (بدل `math.comb` المبعثر)؛ مكتبة خارج `skills/` جاهزة للاستهلاك — تُرقّى ACTIVE بالتوصيل الحيّ + البرهان الثلاثي.
- **القاعدة الذهبية السقراطية (D-113→D-155)**: لا تكشف نتيجةً أو خطوةً يستطيع الطالب توليدها؛ الشرح
  يستقبل **أسئلة-فقط** (`display_content`)؛ الإجابة النموذجية لوضع التحقق حصراً؛ كل مخرَج نهائي يمرّ
  عبر `sanitize_final_text`/`redact_final_answers`. «لم أفهم» = تشخيص + أدنى تلميح، لا إعادة اشتقاق.
- **الاعتراف والتقدّم (D-155/D-158/D-162)**: إجابة الطالب الصحيحة تُحكَم بالمحرك الرمزي وتُعترَف
  (`probability_tutor_brain.py` جذر تركيب + 5 mixins)؛ الملفات المُفكَّكة لا تستورد أصلها أبداً؛
 إعادة التصدير بـ `# noqa: F401` — **D-260** (2026-08-15 · `kernel.py` 272 سطرًا · churn=9): النمط
 نفسه على النواة نفسها — `kernel.py` قشرة تفويض (`RealityKernel` كل واجهاتها القديمة أعيد تصديرها بالاسم)
 + حزمة `app/core/kernel_support/` (`_sources.py` مانيفست مركّب · `lifecycle.py` · `contracts.py` ·
 `otel.py` · `compose.py` شرائح نقية) — radon A · ruff نظيف · E2E D-259 أخضر قبل/بعد (صفر تراجع).
 **D-261** (2026-08-16 · `app/core/database.py` hotspot 9/10 · `create_db_engine` 86 LOC · C(12) · churn=8):
 النمط نفسه على المصنع الكنسي لقاعدة البيانات — قشرة تفويض (31 سطرًا · A(3)) + حزمة `app/core/database_support/`
 (`_url.py` · `_ssl.py` · `_pools.py` · `_sources.py` مانيفست مركّب) — radon C(12)→A(3) في كل دالة · 686/686 أخضر.
 **القانون المعمّم من السلسلة:** أي ملفٍ يعاد تفكيكه: قشرة تفويض تعيد تصدير كل الأسماء القديمة بالاسم، شرائح نقية بلا حالة،
 مانيفست مركّب، اختبارات مطابقة حرفية للأصل، حراس نصية تتغذى من المانيفست — صفر تغيير سلوكي، صفر ZOMBIE.- **صفر تكرار حرفي** (`_recently_emitted` + مرساة `last_step_emitted`)؛ **لا تسرّب تفكير النظام**
  للطالب (D-117: ممنوع prepend «[توجيه تربوي]»، العمق يصل عبر `support_level`)؛ **فجوة الوهم**
  (assisted − durable) هي مقياس النجاح الوحيد (D-126/D-157).
- **النظام يعرّف كل رمز يطبعه (D-185 — 2026-07-28 · ISS-138)**: طالب سأل «ماذا نقصد بحرف C» عن
  رمزٍ طبعه المعلّم نفسه، فتُجوهِل سؤاله وأُعيد عليه الاشتقاق مع تسريب `14`/`165` — لأن كل نقاط
  المطابقة كانت مفتاحها **اسم المفهوم** لا **الرمز** (دائرة مغلقة: من لا يعرف الاسم لا يسأل).
  المصدر القانوني للرموز هو `shared/notation/registry.py` (dep-free)، مكشوفاً كخدمة **API-first**
  `notation-service :8011` وكمهارة `NotationSkill` بتدهور رشيق (الدور التعليمي يستعمل الفرع
  الحتمي المحلّي — بلا شبكة). **القواعد الدائمة:** (1) رمز يُبَثّ بلا إدخال في السجلّ ⇒ CI أحمر
  (`check_notation_definable`)؛ (2) **التعريف ليس إجابة** — أمثلة السجلّ محايدة وممنوع أن تحمل
  أرقام التمرين الجاري؛ (3) **الرمز قبل الكاشفات** — أي مسار شرح احتمالي يفحص طبقة الرموز أولاً،
  والتباس «الحرف C» بـ«الحادثة C» تسريبٌ كارثي؛ (4) حارس التكرار **متماثل** (القسمة على الأصغر)
  فـ«تكرار + إضافة» تكرارٌ حقاً؛ (5) نسخة الخدمة مُوَرَّدة ومحروسة بـ`check_notation_parity`
  (مصدر واحد + مرآة، لا نسخة ثالثة).
- **البصري الحتمي للاحتمالات** (D-116): كل مكوّنات الاحتمالات `terminate_pipeline=True` (صفر سرد LLM)؛
  الكيانات من `parsed_entities` لا نثر الحل (ISS-120)؛ ممنوع `C_n^k=0` مضلِّل (رسالة تربوية بدله).
- **البؤرة لاصقة، والتغطية كاملة، ولا بؤرة معلّقة (D-184 — 2026-07-28)**: «لم أفهم» تعني «لم أفهم ما
  شرحتَه للتوّ» ⇒ `_recover_recent_focus` يسترجع بؤرة الحوار **قبل** أي سقوط افتراضي؛ إعادة الضبط
  القسرية إلى `same_color_event` (التي جعلت المعلّم يقفز للألوان مهما سأل الطالب) **ممنوعة** كسلوك أوّل.
  وكل مُعرَّف تُرجعه `_detect_focus_step` **يجب** أن يقابل `step_id` حقيقياً في القصّة المُولَّدة
  (بوّابة في `tests/services/test_d184_full_exercise_coverage.py` — تمنع البؤر المعلّقة كصنف).
  ومتغيّر عشوائي يُعرّفه التمرين بتكافؤ الأرقام لا يجوز نمذجته على اللون (كان يعرض توزيعاً لمتغيّر
  آخر). الخطوات المعتمدة على الأرقام تُنبَعث فقط حين تُرجِع `number_parity_*` قيمةً — التعميم محفوظ (D-076).
- **الموضوع لا يُختطَف، و«التكرار» يعني تكراراً (D-190 · ISS-140)**: «اشرح لي قانون أوم» كان
  يتلقّى **قائمة تشخيص الاحتمالات** (مُبرهَن حياً، ومتكرّر على «أرخميدس»). **القواعد الدائمة:**
  (1) **الفعل العامّ لا يملك المادة** — `full_solution` يحتاج سياق موضوع (`_is_prob_context`)
  وإلّا حُيِّد إلى `unknown`؛ والحرس **عند نقطة الاستخدام** لا عند التشخيص. (2) **كل عدّاد يقرأ
  `question` و`history` يتجاوز نسخة الدور الحاضر** — المونوليث يحفظ الرسالة قبل بناء الدور
  (§6.5)، فبلا ذلك يُعَدّ سؤالٌ واحد **2** ويجتاز «الحيرة المتكررة» في أوّل رسالة. (3) **التدوين
  ليس نيّة** — `f(x)` تُحتسَب مع قرينة استرجاع فقط، و«احسب/أوجد/برهن» تُلغي جلب تمرين مخزَّن
  (ISS-038 بمفتاح جديد). (4) **بطارية لا تفحص الصلة تُصادق على كارثة** — البنيوية أعطت 8/8
  كاذبة حيث الصلة 7/9.
- **نيّة الطالب مصدرٌ واحد، والتعريف قبل المثال (D-186 — 2026-07-29 · ISS-139)**: ثلاث كوارث متتالية
  (ISS-128 · ISS-138 · ISS-139) جذرها **واحد**: كاشفات متعدّدة لنفس النيّة تتفرّق. في ISS-139 كانت
  ثلاث قوائم للنيّة التعريفية (23·13·27 علامة) لا تتّفق أيّ اثنتين، فسؤال «ماذا يقصد بالحرف C»
  صُنِّف `unknown` وأُجيب الطالب بمثالٍ عارٍ، ثم «لم أفهم» صفّرت الموضوع إلى سؤال الألوان.
  **القواعد الدائمة:** (1) **المصدر الوحيد لعلامات النيّة هو `shared/intent/registry.py`** —
  أي قائمة أخرى تُفشِل `check_intent_single_source` (AST، ضمن guardrails)، والدَّين المُجمَّد في
  `_FROZEN_DEBT` **يتقلّص فقط** (سابقة D-105؛ `tests/` مُستثنى لأن تعداد الصيغ فيه حارسٌ لا نسخة).
  (2) **سؤال نيّته `definition` لا يُجاب أبداً بنصٍّ يخلو من التعريف**، وإعادةُ السؤال إشارةُ
  «لم يصل» لا «تقدَّم» ⇒ التعريف + الرُّتبة التالية غير المُسلَّمة (صفر تكرار حرفي). (3) **ما سُلِّم
  لا يُعاد**: `_render` لا ينزل إلى رُتبة مُسلَّمة — التنزّل الأعمى كان يُفجّر حارس التكرار فيستبدل
  الردّ بـ«الحل الكامل» (تسريب 165·14). (4) **حقلا التعريف والمثال منفصلان** — حشو أحدهما في الآخر
  يُسمّم كشف الرُّتب المُسلَّمة. (5) **الحيرة المجرّدة + مفهوم نشط ⇒ مصفوفة التصعيد** لا probe
  الافتتاح (تمديد D-184). (6) **لا يُغلَق بلاغ كارثة بلا عقد ترانسكريبت** في `tests/transcripts/`
  يُعيد التمثيل على **مراحل الدور الحقيقية**، ويجب إثبات أنه **أحمر قبل الإصلاح**.

### هـ) قانون WebSocket (D-WS-* — من التأرجح إلى الاستقرار)
- **الاتصال خالٍ من قاعدة البيانات** (D-WS-CONN-001): الهوية من الـ JWT (`WsActor` +
  `decode_token_payload`)؛ عمل الـ DB لكل-دور في جلسته. دور الإدمن من `roles` ضمن الـ JWT (D-WS-CONN-002).
- **الرفض عند الاتصال 4401/4403 فقط**؛ الفشل العابر ⇒ `1013` (WS) / retry (HTTP `/me`)، لا طرد
  (D-WS-KICK-001/002). `/me` (401/403) هو الحَكَم الوحيد للطرد.
- **قفل إرسال متزامن** (`_locked_send_json` + `send_lock`) على كل `send_json` مشترك (D-096)؛
  **heartbeat/keepalive** أثناء الدور + liveness على أي رسالة واردة (D-WS-FLAP-002/005)؛ الواجهة
  honest-debounce (≤15s) لا كذب طويل (D-WS-FLAP-004).
- **البروكسي**: `server.js` يُمرِّر WS بمكتبة `ws` + طابور رسائل مبكرة + مستمع `upgrade` وحيد
  (يمنع 101 مزدوج من Next HMR — D-WS-PROXY-001/004). كل الأطر النهائية تُنهي الرسالة (D-WS-FINAL-001).

### و) قانون CI (الأخضر الإلزامي)
- **قوائم deselect تتقلّص فقط** (D-105): مواءمة الاختبارات لا تعطيلها؛ أي إدخال جديد يتطلّب إثبات
  «أحمر على main» + تعليق الجذر. **`required-ci` يَعُدّ skipped نجاحاً** (D-141#4) — لا تكسره.
- **نظافة الاختبارات** (D-105): ممنوع كتابة `sys.modules`/`os.environ` وقت الجمع (بوّابة
  `check_test_hygiene`)؛ `testpaths` صريح؛ subprocess يستخدم `sys.executable`.
- **صفر warning** (D-141): لا gitlink بلا `.gitmodules`؛ كل إجراء GitHub Actions على node24
  (`upload-artifact@v6+`)؛ `push:` مُقيَّد على `[main]` للفروع الميزة.
- **صدق runtime (§6.6)**: لا تُعلَن قدرة ACTIVE قبل البرهان الثلاثي (import + call chain + runtime
  evidence)؛ حتى ذلك FLAGGED/DORMANT. `runtime_truth.py --update` بعد أي تغيير قدرة.
- **التجريد الصادق المفروض (D-176)**: كل port سداسي (`integration_kernel/contracts.py`) إمّا ACTIVE
  (driver مُسجَّل في `mcp/integrations.py`) أو ضمن `KNOWN_DORMANT` المُجمَّدة — تفرضه بوّابة
  `check_abstraction_consumed.py` (port جديد بلا مستهلك ⇒ فشل CI). حدود الخدمات مفروضة آلياً في
  guardrails (`check_no_cross_service_imports` · `check_ports_consistency` ·
  `check_single_brain_control_plane` · `check_core_kernel_acl`). الخريطة الصادقة: `.memory/architecture.md §10`.
- **تنفيذ الأوامر بـ`argv` لا بصدفة (D-187 · M0)**: كان `agent_tools` ينفّذ
  `subprocess.run(..., shell=True)` في ثلاثة مواضع خلف **قائمة منع**، بينما `ALLOWED_COMMANDS`
  مُعرَّفة **ولا يُشير إليها شيء** — قائمة سماح ميتة. مسبار حيّ أثبت مرور الثمانية، و`echo
  $(id -u)` **أعاد `0`**. **القواعد الدائمة:** (1) كل تنفيذ عملية فرعية في `app/`·
  `microservices/`·`shared/` يمرّ من `agent_tools/sandbox.run_sandboxed(argv, …)` — تفرضه
  بوّابة `check_no_shell_true` (دَينها المُجمَّد **فارغ**، ويتقلّص فقط). (2) **قائمة سماح
  مفروضة لا مُعلَنة**: قائمة المنع ناقصة دائماً بطبيعتها؛ الأمان بأن يكون الحقن **غير
  مُمثَّل** (`shell=False`) لا مُرشَّحاً. (3) **بلا شبكة افتراضاً** — `curl`/`wget` خارج
  القائمة؛ الشبكة قدرة تُمنَح صراحةً. (4) **سجن مسارات بـ`resolve()`** (يتبع الروابط) على
  `cwd` **ووسائط المسارات**. (5) **محتوى حرّ مشروع** (رسالة commit) يُمرَّر وسيطاً حرفياً
  (`args_list`) لا يُحشى في سلسلة. (6) **ممنوع توصيل أي مُخطِّط/LLM بالأدوات** قبل استكمال
  M1→M4 — القدرة ≠ الأمان.
- **الأثر الصادر يُمَدّ لا يُخترَع (D-189 · D4)**: كان **31** بناءً مباشراً لـ
  `httpx.AsyncClient(` مقابل **21** حقناً لـ`X-Correlation-ID` في **9** ملفّات — أي أن أكثر
  من ثلثي النداءات تعبر حدود الخدمات بلا هوية تتبّع. والأسوأ أن مواضع الحقن «الصحيحة» كانت
  تُولِّد `uuid4()` **جديداً** لكل نداء (`notation_skill.resolve_via_service`) فتقطع السلسلة
  بدل مدّها — ترويسةٌ موجودة وبلا قيمة. **القواعد الدائمة:** (1) كل نداء صادر يمرّ من
  `shared/http_client.correlated_client` (أو نسخة مُوَرَّدة محروسة بتكافؤ داخل الخدمة — نمط
  D-185)؛ تفرضه بوّابة `check_correlated_http` بـ**AST** لا grep، ودَينها المُجمَّد يتقلّص فقط
  في **الاتجاهين** (بناءٌ جديد أحمر، ودَينٌ أُغلق بلا تحديث الرقم أحمر أيضاً). (2) **المُعرَّف
  يُمَدّ**: الصريح ⇒ المحيط ⇒ التوليد **ملاذاً أخيراً**؛ وترويسة واردة لا تُطمس. (3) **الوجود
  ليس صحّة** — بوّابة تبحث عن نصّ الترويسة لا تكفي، لأن المُعرَّف المُخترَع يجتازها.
  (4) **مهلة صريحة دائماً**: `timeout=None` تعني الافتراضي لا انتظاراً مفتوحاً — الانتظار
  المفتوح على حدّ خدمة يحوّل البطء إلى تعليق. (5) `shared/` **لا يستورد `app`** ولا خدمةً
  شقيقة: المُعرَّف المحيط يُقرأ عبر **مُزوِّد مُسجَّل** (المونوليث يُسجِّل `ContextVar` القائم
  في `app/core/logging.py` — بلا مصدر سادس)، ومُزوِّد يفشل لا يُسقط النداء.

### ز) جسر قاعدة البيانات + الأسرار + compose (D-DB-BRIDGE-001 · D-172)
- **جسر Supabase** (`scripts/db_bridge.py`): SQL عبر HTTPS:443 حين تُحجَب منافذ Postgres (5432/6543).
  للقراءة/التشخيص/DDL اليدوي فقط — لا كتابة مزدوجة (D-006). الأسرار من البيئة حصراً (git-ignored).
- **Docker full-stack قابل لإعادة الإنتاج** (D-172): الشبكة compose-managed؛ جسر أسرار تلقائي
  (`compose_env_from_secrets.sh`)؛ **الصحة لا تكذب** — خدمة على sqlite/mock تحت الإنتاج تُبلِّغ
  `degraded`؛ checkpointer=postgres مُثبَت (`verify_full_stack_docker.py`).
- **K-ROOT — استمرارية مفتاح التوقيع (D-241 · D-242 — 2026-08-12 · Supabase · PR #11)**: كان
  `dev_secret_key` من `SECRET_KEY` في البيئة فحسب — قرصٌ متقلب يعيد إنتاج «Login failed» عند
  كل Codespace جديدة (ISS-152/158 من زاوية أخرى). الحل: `app/core/settings/helpers.py` طبقة
  `app_state` في Supabase — الأسبقية **env → جدول الإنتاج → توليد آمن + حفظ**، لا ملف قرص،
  ولا إعادة ضبط كلمة مرور الأدمن إلا بـ`ADMIN_FORCE_PASSWORD_SYNC=1`. البينات: monolith بلا
  `SECRET_KEY` يستعيد مفتاح 86 حرفًا من `app_state`؛ E2E حيّ على Supabase (24/24 — login 200 ·
  كلمة خاطئة 401 · orchestrator chat 200 · `POST /agent/chat` 200 بعد إصلاح band
  `turn.identity` · `POST /missions` بمُبدأ JWT — كان initiator=1 مفتوحًا · user_client URLs
  صحيحة + `X-Service-Token` · ports user:8003/planning:8001/memory:8002 — الحالة
  `.memory/auth_runtime_truth.md`.

### ح) قانون التوليد الآمن (النماذج + الحُرّاس)
- **سلسلة النماذج** (D-067/D-167 · **D-288**): PRIMARY = `google/gemma-4-31b-it:free`، والسلسلةُ مصدرٌ واحد `shared/ai_models/model_chain.py` ينعكس حرفيّاً في الدماغين تحت `check_model_chain_parity.py`؛ نموذجٌ أزاله OpenRouter من الطبقة المجانية (404 / `"endpoints": []`) يُنزَل من PRIMARY فوراً ويُترَك بذيل السلسلة (تعافٍ آلي). **القدرةُ لا تُطعِم طالباً**: سجلُّ القدرات وحده لا يكفي، والكتالوجُ الحيّ يُسأل (مسبارٌ + بوّابة). **والفشلُ القابلُ للتداري يُدارى**: 402/404/406/408/409/413/425/429/5xx ⇒ دورانٌ إلى التالي · 401/403 ⇒ فشلٌ فوريّ (مفتاحٌ ميتٌ لا يُداوَى بنموذجٍ آخر) · `max_retries=0` لأنّ الآليةَ هي السلسلة · أوّلُ رمزٍ مصادق عليه يُلغي الدوران · `content_chunks==0` فشلٌ لا إجابة (`provider_down` تُعلَن ولا تُلَفَّق «لا سياق»). نماذج reasoning-only (content=None) محظورة كـ PRIMARY. system prompts < 1500 حرف؛ box-drawing ممنوع.
- **حُرّاسُ المخرَج — حمايةٌ لا إتلاف (D-289/ISS-201)**: `content_integrity` يحذف هذيانَ اللاتيني (تسريبُ تفكير D-067) ويحمي **بنيتَه** — رابطٌ/مسارٌ/مُعرِّفٌ/شيفرةٌ مُضمَّنة/رموز SI — فـ`https://…`→`://./` كان إتلافاً للإجابة لا تنقيحاً؛ التوسعةُ قائمةٌ بيضاء وبندٌ مرقَّمٌ في دستور الطبقة (`CONTENT_INTEGRITY_DOCTRINE_VERSION`)، لا تليينُ عتبةٍ ولا إطالةُ نافذة.
- **حُرّاس المخرَج**: `arabic_stream_guard` (عربي فقط على البثّ)؛ `content_integrity`/`response_sanitizer`
  (حذف garbage لاتيني/CJK/⟦⟧/تعليمات مُسرَّبة، مع حماية البنية — انظر الدفعة أعلاه)؛ `output_firewall`+`topic_lock` (V46) — كلها fail-open.
- **صمود الـ rate-limit — «يجيب على كل سؤال» (D-177 — 2026-07-22)**: عند 429 من الطبقة المجانية،
  `SimpleAIClient.stream_chat` لا يسقط فوراً إلى `safety_net`. البوّابة تُصنِّف 429 كـ `AIRateLimitError`
  (مع `retry_after`)، وتُشغِّل **مروراً ثانياً محدوداً** على النماذج المحدودة فقط بعد backoff قصير
  (`RATE_LIMIT_BACKOFF_MAX=5s`) — فالحدّ اللحظي العام يتعافى قبل الاستسلام. حارس **زمن أول محتوى**
  (`FIRST_TOKEN_TIMEOUT=30s`) يتخلّى عن نموذج بطيء/فارغ (قِيس `nemotron-nano-9b` 62s بمحتوى=0) بدل
  تجميد الدور. `cognitive_engine.memorize` محروس بـ None (بند CLAUDE.md). السلسلة المُثبَّتة أمنياً
  **لا تتغيّر** (ISS-107 يُبقي `nemotron-3-super-120b` محظوراً — تسرّب إنجليزي). جاهزية مفتاح مدفوع:
  `OPENROUTER_EXTRA_MODELS` (CSV) يُلحِق نماذج إضافية بذيل السلسلة runtime بلا مسّ الحرفيات المحروسة
  بالتكافؤ. مُتحقَّق حياً E2E (postgres محلي + WS): سؤال رياضي يفشل فيه PRIMARY (reasoning-only) ثم
  يجيب gemma بعربي+LaTeX سليم، والرسالة تُحفَظ. الحارس مشترك عبر `get_ai_client()` فيفيد **كل** وكيل ومهارة.
- **الكاش المعرفي عربيّ-أولاً + استرجاع الصمود (D-180 — 2026-07-22 · ISS-133)**: `CognitiveResonanceEngine`
  (`app/core/cognitive_cache.py`) هو كاش دلالي ضبابي. `_normalize` **يجب** أن يبقى مُدرِكاً لليونيكود
  (تجريد التشكيل + التطويل، توحيد الألف/التاء المربوطة/الألف المقصورة، `\w`) — النسخة القديمة
  `[^a-z0-9\s]` كانت تمسح **كل** حرف عربي فتُحوِّل recall/memorize إلى لا-عملية صامتة لكل مستخدمي
  المنصّة (ممنوع الرجوع إليها). `get_cognitive_engine()` يُعيد نسخة حقيقية (لا `None`). `recall()`
  مُفعَّل كطبقة **صمود** عند نقطة استنفاد سلسلة النماذج فقط في `simple_client.stream_chat` (قبل
  `SafetyNetService`): إجابة سابقة عالية الرنين بنفس `context_hash` أفضل من «لا يجيب» — يخدم
  «يجيب على كل سؤال» بلا التفاف على المسار العادي ولا على المحرك الرمزي. مقيَّد بعلم
  `COGNITIVE_CACHE_RESILIENCE_ENABLED` (افتراض on، رجوع فوري `=0`). مقاييس Prometheus:
  `cogniforge_cognitive_cache_{recall_total{result},memorize_total,resonance_score,size}` (بلا labels
  عالية الكاردينالية). ملاحظة: `SemanticCache` (`app/caching/semantic.py`، تطابق-hash عربيّ-آمن،
  ACTIVE في `ChatOrchestrator`) و`CognitiveResonanceEngine` (ضبابي، صمود gateway) دوران متمايزان.

### ط) API-first + المهارات (D-100 · D-173 Stage 4/5 · D-174)
- **كل خدمة لها عقد OpenAPI** يغطّي مساراتها الفعلية، مفروض ببوّابة **دلالية**
  (`check_openapi_parity` — endpoints لا bytes، robust عبر إصدارات pydantic). المولِّد
  `scripts/contracts/export_openapi.py` هو SSOT. **العدد مُشتَقّ** من
  `docs/contracts/openapi/*-openapi.json` — كان مكتوباً هنا يدوياً «11/11» بينما §3 يقول
  «13/13»، فناقض الدستورُ نفسه حتى 2026-07-31 (D-192).
- **منصّة Skills موحَّدة** (D-100): registry + `compose_text_refinement` + `/api/v1/skills`؛
  كل مهارة `import + call chain + runtime evidence` أو FLAGGED؛ لا ZOMBIE (بوّابة).
- **Kagent محذوف** (D-173 Stage 5): كان ZOMBIE محظوراً أمنياً — القدرة بلا مستهلك حي تُحذَف لا تُترَك stub.

### ي) Observability and Runtime Governance (الرصد وحوكمة التشغيل)
> **المصدر الحيّ الكامل:** `.memory/observability-topology.md` (طوبولوجيا الرصد + العقود الدلالية).
> بوّابة CI `observability-validation` تفرض بقاء هذا القسم + ذاك الملف (documentation lock).
- **Grafana Observability Stack** (منفذ 3001) + Prometheus (9090) هما لوحة الرصد؛ لكن **الأجهزة قبل
  التصوير** (Instrumentation before visualization): كل مقياس له عقد دلالي ومُصدِر مُتحقَّق في المصدر
  (D-016)، لا لوحات zombie تعرض صفراً دائماً. **الرصد للتشخيص لا الزينة**.
- **صدق runtime فوق اليقين الاصطناعي** (§6.6): لا قدرة تُعلَن ACTIVE قبل البرهان الثلاثي
  (import + call chain + runtime evidence)؛ حتى ذلك DORMANT/FLAGGED. `runtime_truth.py --check` بوّابة.
- **Degraded ≠ Dead**: خدمة تمرّ `/health` لكن warmup الرسم فشل = DEGRADED؛ يجب أن يكشفه `startup_state`.
  الأثر والمقاييس تخصّصان منفصلان؛ labels عالية الكاردينالية ممنوعة؛ الكتابة المزدوجة للـ DB ممنوعة.

---

## 6.8 الرؤية الثورية — القواعد الدائمة

> **المصدر الحيّ:** `.memory/roadmap.md` (ملخّص §0.6) · مقاعد التوسّع:
> `docs/architecture/EXTENSION_SEAMS.md`. أهداف الجلسات المؤرَّخة (D-173 وما بعدها) تعيش في
> `.memory/decisions.md` — لا في العقد (قاعدة D-188).

- النظام **مختبر معرفي / محرّك تفكير** لا مُجيب — يُنمذج تفكير الطالب ويشخّصه ويحسّنه.
- **API-first**: حدّ الخدمة هو **العقد لا اللغة**؛ كل خدمة لها عقد OpenAPI مفروض ببوّابة تكافؤ دلالية.
- **قتل التعقيد** (SOLID/KISS/DRY/YAGNI): لا God-files؛ الاستخراج سطرٌ واحد في مانيفست، والنقل verbatim.
- **إضافة أي تقنية عبر مقعد موجود** بشرط تبنٍّ صريح وبلا كود ميت (EXTENSION_SEAMS.md).
- **مقياس النجاح الوحيد**: فجوة الوهم (المدعوم − غير المدعوم المؤجَّل). **ممنوع** التحسين على
  مدة الجلسة/عدد الرسائل/الرضا اللحظي.

**قاعدة الإغلاق:** أي قدرة تُضاف تُثبَّت بالبرهان الثلاثي (import + call chain + runtime evidence)
قبل ACTIVE؛ حتى ذلك FLAGGED أو موثّقة كمقعد — لا ZOMBIE أبداً.

---

## 6.9 خريطة الإحالة إلى الأرشيف (§6.x → التاريخ الكامل)
كل قرار D-XXX له سرده الحرفي الكامل (النطاق، الأدلة، الملفات، التحقق الحي) في
**`docs/archive/constitution-history/CLAUDE-SECTIONS-6x-FULL.md`** (لقطة CLAUDE.md قبل جراحة D-173)
**و`.memory/decisions.md`** (سجل القرارات الحيّ — **المصدر الأول لأي D-XXX جديد**) · وخريطة السلطة
الكاملة: `docs/DOCUMENTATION_INDEX.md`.

### سلسلة تفكيك التعقيد — CodeScene X-Ray (D-252 → D-262) + سلسلة الدساتير (D-263 → D-265)
نمط واحد قاطع للكل: **قشرة معمارية تفوِّض + حزمة شرائح نقية + مانيفست مركّب `_sources.py`** تتغذى
منه الحراس النصية — **صفر تغيير سلوكي** في كل قرار (مطابقة كاملة قبل/بعد أو بوابات AST تحرس الأثر).

| القرار | الملف الساخن | التفكيك |
|---|---|---|
| **D-252** | `chat_stream_ws` 669 سطرًا F(69) churn=53 | قشرة استقبال ~60 سطرًا C(13) + `customer_chat_support/turn_lifecycle.py` [`handle_turn` C(12) · `_stream_and_wait` B(8) · `_close_turn` D(23)] — Stage 3 من جراحة D-173، حراس تتغذى من المانيفست |
| **D-253** | `agents/orchestrator.py` 552 سطرًا · خمس دوال B/C | قشرة استقبال + حزمة `orchestrator_support/` خمس شرائح نقية · مانيفست مركّب · رُفِع تجميد `PLR0912` |
| **D-254** | `api_gateway/main.py` 586 سطرًا · ازدواج 4 · تردد 10 | **سجل توجيه تصريحي** `ROUTE_REGISTRY` — 27 مسارًا تبني المعالجات آليًا · حارس `check_gateway_routes_parity` endpoints لا bytes |
| **D-255 + D-259** | `tools/content.py` 173 سطرًا · `search_content` C(14) churn=40 | قشرة استقبال + حزمة `content_support/` [`search.py` + `branch.py` مستقلة مصدرٌ واحد للشعبة + كشف الأخطاء جدولُ تحويلٍ واحد إلى ثلاث شرائح] · B(8) بدل C(14) · Bumpy Road مغلق نهائيًا · ruff 0.14.0 + radon A(5) |
| **D-256** | `orchestrator_client.py` 238 سطرًا · ازدواج `get_mission*` · churn=2 | قشرة تفويض حرفية + حزمة `orchestrator_client_support/` [`missions.py` قلب موحد + `ServiceJwtPayload` · `preempts.py` قرار Supabase معزول] · 11 اختبارًا جديدًا، حراس legacy_invariants وskills_doctrine الموسّعان |
| **D-258** | `tests/conftest.py` 416 سطرًا · `db_lifecycle` 63 LOC churn=12 Bumpy Road | قشرة تسجيلٍ وتفويضٍ + حزمة `conftest_support/` (helpers/registry/schema/lifecycle/auth_shards/policy/_sources) — اكتُشف: pytest لا يفعّل autouse لfixtures مستوردة فبقيت قشور التسجيل |
| **D-260** (الآن) | `app/kernel.py` 272 سطرًا · `_validate_contract_alignment` churn=2 + `_handle_lifespan_events` churn=9 · Complex Method/Bumpy Road | قشرة تفويض نقية + حزمة `app/core/kernel_support/` [`_sources.py` مانيفست مركّب · `lifecycle.py` دورة حياة مفككة · `contracts.py` مطابقة OpenAPI/AsyncAPI نقية · `otel.py` bootstrap · `compose.py` combinators] · **أسماء الواجهة القديمة كلها أعيد تصديرها** (لا كاسر لأي مستورد) · radon B(8)/B(7)→A · ruff نظيف · E2E D-259 أخضر قبل/بعد |
| **D-262** (2026-08-16 · CodeScene X-Ray job 72) | `services/overmind/graph/main.py` hotspot 10/10 · `create_unified_graph` 85 LOC · churn=14 (أعلى الملف مطلقًا) · `route_intent` churn=5 · التعقيد موزّع (3-6) — الرسم الموحد بأكمله في وحدةٍ واحدةٍ يعيد تدفئة الكل مع كل تعديلٍ على أي عقدة | قشرة تفويضٍ نقية (24 LOC · A(2)) + حزمة `graph/graph_support/` [`_graph.py` تسجيل العقد + الأسلاك + الـcompile · `_conditions.py` شرائط الشروط الحتمية: route_intent/check_results/check_quality — DEADLOCK FIX: النيات المجهولة تُقفل إلى `educational` بدل "unknown branch" · `_search_shards.py` شرائح البحث الخمس + `_PassthroughNode` · `_sources.py` مانيفست `GRAPH_SOURCE_FILES` المركّب] · **كل أسماء الواجهة القديمة أعيد تصديرها** (لا كاسر لأي مستورد/monkeypatch — قانون late-binding من D-252) · radon A في كل الشرائح ≤ A(3) · **25 اختبارًا جديدًا** (`tests/unit/services/chat/test_graph_shards_d262.py`) يُثبتون مطابقةً حرفية: كل شريحةٍ منفردة + الرسم المجمَّع عقدةً عقدة وحافةً حافة (14 عقدة · كل ورقة تخرج عبر `validator` الوحيد إلى `__end__`) · `tests/microservices/test_overmind_entrypoint.py` و`test_orchestrator_chat_stategraph.py` أخضر · بوابتا الحراسة خضراء · ruff نظيف |
| **D-261** (2026-08-16 · ISS-172) | `app/core/database.py` hotspot 9/10 · `create_db_engine` 86 LOC · F(11) · C(12) · churn=8 · Complex Method · `get_db` churn=12 (تناقض يفضح مصدرًا خارجيًا) | قشرة تفويض نقية (31 سطرًا · A(3)) + حزمة `app/core/database_support/` [`_url.py` تحويلات URL الأربع · `_ssl.py` سياق SSL لكل نمط · `_pools.py` profiles الثلاثة + `connect_args` الحتمي بـ `statement_cache_size=0` · `_sources.py` مانيفست مركّب] · **أسماء الواجهة القديمة كلها أعيد تصديرها** · alias وحيد موثّق `get_db_session = get_db` (المسار التربوي الزومبي: `local_graph.py` يستورد اسمًا لم يُعرَّف قط داخل `suppress` — صار اعتمادًا متاحًا لا فشلًا صامتًا) · radon C(12)→A(3) في كل دالة · بوابتا الحراسة خضراء · 686/686 · ruff 0.14.0 أخضر |

### بقية المجالات (السرد الحيّ في `.memory/decisions.md` + الأرشيف)
| المجال | القرارات |
|---|---|
| الاستمرارية والبثّ | D-006 · D-047 · D-048 · **D-198** · **D-199** · ISS-016/017 |
| العقل التربوي السقراطي | D-074 · D-104 · D-113 → D-160 |
| الاحتمالات الحتمية | D-075 → D-085 · D-116 · D-152/153 · **D-182** · **D-184** |
| WebSocket | D-WS-001 → D-WS-PROXY-004 · D-096 · ISS-092→101 |
| الواجهة/الثيم | D-049 → D-059 |
| كوارث التسليم الحيّ | **D-257** (E2E حيّ 2026-08-14 · ISS-169: `Mission` غير مستورد ⇒ استيراد حرفي + مرجع كائني — رسالة id=4915 حُفظت فعليًا · Supabase أخضر) |
| النماذج | D-060 · D-067 · D-088 · D-167 · D-177 · D-178 |
| الكاش (Cache) | D-180 |
| Skills / OOP / الاستدلال | §0.5 · D-069 · D-100 · **D-179** · **D-181** · **D-183** |
| الرموز والنيّة واللغات | **D-185** · **D-186** · **ADR-006** |
| التوثيق/CI | D-105 · D-141 · D-156 · **D-173** · **D-179** · **D-182** · **D-184** · **D-192** |
| دستور المحرك التربوي | **D-263** (2026-08-16 · قرار المالك: بنية ليست ميزة — العقل التربوي هو الـmoat — `.memory/pedagogy_engine_constitution.md` · L1–L10 · `check_pedagogy_engine.py` · ISS-174→177 · يمتدّ D-153/D-144/D-208 دون إلغاء) |
| مخطط الدراسة التكيفي | **D-264** (2026-08-16 · قرار المالك: الورق مجرد واجهة لفكرة أكبر — Adaptive AI Study Planner: أهدافٌ → تشخيصٌ → تقسيمٌ → متابعةٌ → إعادة ضبط — `.memory/adaptive_study_planner_constitution.md` · L1–L10 · `check_adaptive_study_planner.py` · ISS-178→181 · يستند إلى D-263 دون إلغاء) |
| حوكمة Spec Kit | **D-265** (2026-08-16 · قرار المالك: طبقة ضبط تنفيذ لا تتجاوز — Spec-Driven: خطة → تصميم → مهام → مواصفة → تنفيذ → برهان — `.memory/spec_kit_governance_constitution.md` · L1–L10 · `check_spec_kit_governance.py` · ISS-182→185 · طبقةٌ فوق الدساتير لا بديلٌ عنها) |
| طبقة التحقّق (NAAS) | **D-267** (2026-08-18 · قرار المالك: المُتحقِّق منتجٌ بحدٍّ مستقلّ وأصول المنصّة `reusable technical assets` لا moat — `.memory/naas_verification_constitution.md` + `docs/governance/GATE_STATE_MACHINE.md` · L1–L10 · `check_naas_verification.py` · ISS-187→190 · يوضّح نطاق D-225 ولا ينسخه) |
| K-ROOT · استمرارية المفاتيح + تحصين الأوركستريتور | **D-241 · D-242** (`app/core/settings/helpers.py` طبقة `app_state` · `bootstrap.py` · `user_client.py` · orchestrator `security.py`/`routes.py` — تحرسها `doc-integrity` · 24/24 E2E حي 2026-08-12) · **D-244** (برهان D-241 + أصول العطب الثلاثة) · **D-245** (مجسّات حيّة صادقة: DB probe · إعلان المزوّدين · /health صادق) |
| البنية التحتية (Docker/Observability) | §6.10 → §6.18 · D-172 · **D-182** |
| الأثر · الذاكرة · الموضوع · التمرين | **D-188** · **D-189** · **D-190** · **D-191** |
| صدق الفوارض · الحيرة لا تُهنَّأ | **D-208** (ISS-149 — الأسبقية · الفعل الكلامي على المؤشّرات · بوّابة لا تشهد بما لم تقرأ) |
| التنسيق · الطبقات التسع | **D-209** (`AGENTIC_ORCHESTRATION_DOCTRINE.md` + `.memory/agentic_runtime_doctrine.md`) |
| القيمة والإيراد (§0.10) | **D-210 → D-223** (`docs/VALUE_DOCTRINE.md` · `docs/REVENUE_ENGINE_SPEC.md` · `.memory/revenue_engine_truth.md` — تحرسها `check_revenue_doctrine`) |


## 0.25. Deep Tech & Hard-Currency Constitution (D-273) — المجّاني الاستهلاكي محظور، والعملة الصعبة هي الهدف
> **القانون:** [`docs/DEEP_TECH_CONSTITUTION.md`](docs/DEEP_TECH_CONSTITUTION.md) ·
> **الحالة:** [`.memory/deep_tech_constitution_truth.md`](.memory/deep_tech_constitution_truth.md) ·
> **الفارض:** `check_deep_tech_constitution` (سلكه `guardrails` في `ci.yml`).
**الجملة الدستورية:** «**المجّاني الاستهلاكي يحظَر. لا عتبةَ دخولٍ تقنيةً عالية = لا مشروع. والإيرادُ
العملةُ الصعبةُ من عميلٍ مؤسّسيٍّ خارج الجزائر — وكل ما عداه استثناءٌ مصرَّحٌ به كتابيّاً.**»
- **L1** ⛔ تطبيقٌ استهلاكيٌّ سطحيٌّ بلا عمقٍ رياضيٍّ أو أمنيٍّ أو تنظيميٍّ. · **L2** ⛔ لا خدماتٍ عامةً
  (تعليق/ترجمة/شات عام) — Micro-Niche هو النمط الوحيد المسموح. · **L3** ✅ مزيجٌ لغويٌّ نادر
  (عربيةٌ + فرنسيةٌ) في أمان/بيانات يجهلها العالم الإنجليزي. · **L4** ✅ حلول On-Premise/Offline
  لقطاعاتٍ ترفض السحابة (نفط · غاز · تعدين) — السرية هي المنتج. · **L5** كل ميزةٍ تسمّي الفرضَ
  المستوفى (L1–L12) — بلا فارضٍ = رفض. · **L6** الإيراد دولار/يورو من عميلٍ مؤسّسيٍّ — لا دينارٌ
  كهدفٍ استراتيجيٍّ جديد؛ يُبنى فوق دستور القيمة (D-210 → D-223) لا مكانه. · **L7** التكلفة جزائريةٌ
  والقيمة مبيعةٌ غربيةٌ/خليجيةٌ. · **L8** ⛔ لا عرضٌ دون إثبات ندرةٍ موثَّقةٍ قبل البيع. · **L9** سبعة
  خطوطٍ مصرَّحةٍ حصراً (§03): AI Red Teaming بالعربية/الفرنسية (25K$–200K$) · Niche RLHF
  (فقه/قانون/طبي فرنسي) · On-Premise AI خليجي · PINNs صناعي (−60%→−80% R&D) · Formal Verification
  لكود الذكاء الاصطناعي · EU AI Act B2B SaaS (40K€–90K€) · High-RPM AI Affiliation غربي —
  خطٌّ ثامنٌ = ADR + قرار مالكٍ مكتوب. · **L10** المحرّمات التسعة (§04) — أيٌّ منها في PR ⇒ مرفوض،
  وإن دُمج ⇒ يُزال فوراً. · **L11** اختبار الإضافة (§05): «لو حُذفت الفكرة، هل فقدنا خطّاً أو محرّماً؟
  لا؟ ⇒ لا تُضاف». · **L12** مقياس النجاح الوحيد (§08): إيرادٌ سنويٌّ بالعملة الصعبة من خطٍّ واحدٍ على
  الأقل موثَّقٌ في وثيقة الحالة قبل نهاية السنة المالية — كل مؤشرٍ آخر ضجيجٌ.
⚠️ لا يُعلَن خطٌّ `ACTIVE` دون دليلٍ حيٍّ (عقد/دفعة) في وثيقة الحالة — الحالة صادقةٌ لا تزيينيةٌ
(D-267 L6). الإضافة لا الاستبدال: D-273 لا يلغي D-210→D-223 ولا الدستور المعماري —
يضيف خطّ إيرادٍ مؤسسياً فوقهما، والأصول الهندسية (تحقّق · وكالة · بيانات) تُستثمر في خطّين.
- **الإضافة لا الاستبدال**: D-273 وكلّ ما سبقه يبقى سارياً. تعديل هذا الدستور = ADR + بوابةٌ خضراء.
---

## 0.26. Reference Backbone Constitution (D-274) — كل مرجعٍ مثبتٌ ومفهومٌ ومربوطٌ بفارض
> **القانون:** [`docs/architecture/REFERENCE_BACKBONE_CONSTITUTION.md`](docs/architecture/REFERENCE_BACKBONE_CONSTITUTION.md) · **الحالة:** [`.memory/reference_backbone_truth.md`](.memory/reference_backbone_truth.md) · **الفارض:** `check_reference_backbone.py`.
> **الجملة:** المراجع الـ15 الإلزامية لا تُحذف ولا تُستبدل بصمت؛ لكل مصدر commit ودور واستعارة وحدود ودليل، ولا يتحول إلى تبعية تشغيلية بلا ADR وأمن.

## 0.27. Unified Agent Context Constitution (D-275) — لا وكيل يعمل من ذاكرةٍ خاصة
> **القانون:** [`docs/architecture/AGENT_CONTEXT_CONSTITUTION.md`](docs/architecture/AGENT_CONTEXT_CONSTITUTION.md) · **الحالة:** [`.memory/agent_context_truth.md`](.memory/agent_context_truth.md) · **الفارض:** `check_agent_context.py`.
> **الجملة:** كل وكيل يحمّل سجل السلطة، boot sequence، مصفوفة المصادر، الأدلة، الحقيقة التشغيلية، والأثر التجاري قبل أي تغيير؛ الادعاء بلا مصدر أو تجاوز الترتيب = رفض.

## 0.28. Code Acceptance Constitution (D-277) — لا سطر كود بلا حزمة إثبات
> **القانون:** [`docs/architecture/CODE_ACCEPTANCE_CONSTITUTION.md`](docs/architecture/CODE_ACCEPTANCE_CONSTITUTION.md) · **الحالة:** [`docs/changes/CURRENT_CODE_ACCEPTANCE_PACKET.json`](docs/changes/CURRENT_CODE_ACCEPTANCE_PACKET.json) · **الفارض:** `check_code_acceptance.py`.
> **الجملة:** كل إضافة تمر بالمعايير والمقررات والأبحاث، تطبيق محلي، أمن، عقود، اختبارات، إنتاج، أثر تجاري، وفحص حذف صفري؛ لا يستطيع الوكيل تعطيل البوابة التي تحكم تغييره.
