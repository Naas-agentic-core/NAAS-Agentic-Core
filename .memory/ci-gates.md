# CI Gates — Pre-merge Required Checks
> **ISS-148 note:** this table used to name **five workflow files that no longer
> exist** (`microservices-step6…step12`) while omitting five that do, and listed 8
> of the checks the `guardrails` job actually runs. A gate inventory that lies
> is worse than none: it is read precisely by the people trying to be careful.
> **The source of truth is `.github/workflows/ci.yml` itself** — run
> `make gates` (`scripts/run_fitness_gates.py`) to execute the real set locally;
> it reads the workflow, so it cannot drift from it.
>
> **D-266 note (ISS-186):** the count below is a *derived* marker, not prose. It
> used to read "~31 fitness gates" — a hand-typed number in the very document
> whose whole purpose is to stop inventories from lying. Worse, the sentence
> above ("it reads the workflow, so it cannot drift") was true of `make gates`
> and false of the repo: seven gates existed on disk that **no workflow and no
> test ran**, so `make gates` could not drift from a set that never contained
> them. All seven are wired now and `check_governance_registry.py` makes an
> eighth impossible. Total gates on disk (derived, verified in CI):
>
> <!-- derived:gates_total=93 -->
> **92** — in `scripts/fitness/` and `tools/ci/`, every one of them executed.

## Required jobs (must be green)

`required-ci` in `ci.yml` aggregates **twelve** jobs; its `needs:` list is the truth
(and is now derived by `check_constitution_reality` — the count said *nine* for as long
as the list said ten, in the very file that names `needs:` as the arbiter).

| Workflow | Job | What it enforces |
|---|---|---|
| `ci.yml` | `lint` | `ruff check .` + `ruff format --check .` + `mypy` |
| `ci.yml` | `contracts` | gateway/provider parity + `tests/contracts/` |
| `ci.yml` | `guardrails` | fitness gates — enumerated in the workflow, run locally with `make gates` (count derived above, never typed) |
| `ci.yml` | `test-monolith` | `tests` + `scripts/ci` minus microservices, `--cov-fail-under=73` |
| `ci.yml` | `test-microservices` | `tests/microservices` + `microservices/*/tests` + OpenAPI parity |
| `ci.yml` | `frontend-tests` | node tests + lockfile sync + generated TS types + `npm run typecheck` + bundle budget |
| `ci.yml` | `skills-structural` | skills registry/structure assertions |
| `ci.yml` | `event-stack-live` | **D-204** — boots Redpanda + Temporal, proves delivery/skip/DLQ |
| `ci.yml` | `images-plan` + `images-build` | **D-205** — every buildable image declared and built |
| `ci.yml` | `required-ci` | aggregator over the twelve above (skipped counts as success — D-141#4) |

### Workflows with no aggregator (blocking depends on branch protection)

| Workflow | Job | What it enforces |
|---|---|---|
| `doc_integrity.yml` | `doc-integrity` | `check_documentation_contract` + `check_memory_coherence` + `check_constitution_reality` + **`check_authority_links`** + CLAUDE.md anchors + no dated diagnostics outside `docs/archive/` |
| `runtime_truth.yml` | `runtime-truth-drift-check` | `scripts/runtime_truth.py --check` vs `.runtime/truth_table.lock.json` |
| `skills-doctrine-gate.yml` | `doctrine-drift` · `doctrine-invariants` | `check_skills_doctrine.py` + `check_pedagogical_os.py` |
| `skills-architecture-gate.yml` | 7 jobs + `skills-gate-required` | API contracts · metrics inventory · skill isolation · health · dashboards · targets · pipeline |
| `structure-validation.yml` | `validate-structure` · `validate-integration` | `scripts/validate_structure.py` + E2E chat check |
| `frontend-theme-ci.yml` | 6 jobs + summary | theme contracts · anti-flash · build · lint · regression |
| `observability_validation.yml` | `static-validation` | compose config · telemetry wiring · documentation lock |
| `docker-fullstack-gate.yml` | `compose-validate` | compose config validation only — **does not run `up`** |

## D-185 — the two notation gates (added 2026-07-28)

| Gate | What it enforces | Why it exists |
|---|---|---|
| `check_notation_definable.py` | Every math symbol the probability brain emits (scanned through the `BRAIN_SOURCE_FILES` manifest) has an entry in `shared/notation/registry.py`; every entry is complete; **every example is neutral** (must not contain `14`/`165`/`56`) | ISS-138: a student asked what a symbol the tutor itself printed meant, and the system could not define it. An emitted-but-undefinable symbol is a knowledge debt that becomes a catastrophe on first contact. The neutrality check stops "definition" from becoming a back door that leaks the exercise answer (D-113). |
| `check_no_shell_true.py` | No `shell=True`, `os.system`/`os.popen`, or `asyncio.create_subprocess_shell` anywhere in `app/`, `microservices/` or `shared/`. The `_FROZEN_DEBT` map is **shrink-only** and is currently **empty**. | M0: the agent shell tool ran `subprocess.run(..., shell=True)` behind a denylist, while its `ALLOWED_COMMANDS` allowlist was defined and never referenced. A live probe showed all eight attacks succeeding — `echo $(id -u)` returned `0`, `awk` ran despite being absent from the allowlist, `cat ../../../../etc/hostname` read outside the project, and `curl` reached the internet. A denylist cannot enumerate every dangerous form; argv + shell=False makes injection unrepresentable rather than filtered. |
| `check_intent_single_source.py` | Student-intent marker lists live **only** in `shared/intent/registry.py`. Any module-level tuple/list holding two or more canonical intent phrases fails CI, the vendored `shared/notation` markers must stay a subset of the canonical ones, and the `_FROZEN_DEBT` map is **shrink-only** (a new entry fails; an entry that became clean also fails until it is deleted). `tests/` is excluded on purpose. | ISS-139: three consecutive live catastrophes shared one root — several detectors for the same student intent drifting apart. Three separate lists for the definitional intent (23, 13 and 27 markers) agreed on nothing, so «ماذا يقصد بالحرف C» was classified `unknown` and the student got a bare example. Each previous fix added the missing word to the list that erred, which cured the symptom and left the class. This gate makes a sixth list impossible rather than merely discouraged. |
| `check_notation_parity.py` | `shared/notation/registry.py` and the vendored `microservices/notation_service/src/notation/registry.py` are byte-identical, and **no third copy** defines `NOTATION_REGISTRY` | Constitution rules 97/98 forbid a shared business-logic library, so the service vendors the registry. Duplication without a guard is silent drift — the same class of defect ISS-138 came from. Mirrors `check_model_chain_parity.py` (D-174). |

## D-188 / D-189 — memory coherence + outbound trace (added 2026-07-29)

| Gate | What it enforces | Why it exists |
|------|------------------|----------------|
| `check_memory_coherence.py` | The sovereign index row in `.memory/README.md` names the newest `D-###`/`ISS-###`; the 20-entry recent window of `decisions.md`/`issues.md` is strictly newest-first; `CLAUDE.md` stays under a **shrink-only** line ceiling; `.runtime/truth_table.lock.json` is not older than the newest decision. The historical out-of-order tail is frozen and shrink-only (D-105 precedent). | D-188: `doc-integrity` checked *existence*, not *coherence*. For two months the index declared D-184/ISS-137 while the logs had reached D-187/ISS-139, D-185 sat below D-180, CLAUDE.md §6.6 carried a 2026-05-09 truth table advertising a security-banned PRIMARY model and a deleted Kagent as live, and the truth lock was generated on a stale branch. Every one of those is a lie an agent would act on, and nothing could fail. |
| `check_correlated_http.py` | `httpx.AsyncClient` is constructed **only** in three declared factories; everything else goes through `shared.http_client.correlated_client`. AST-based (a mention in a comment is not a violation; `from httpx import AsyncClient` is). The frozen debt is **shrink-only in both directions** — a new construction fails, and a debt that was closed without lowering the number also fails. | D-189 (roadmap §6.5.د D4): 31 direct constructions against 21 header injections in 9 files, so two thirds of cross-service calls crossed a boundary untraceable. Worse, some injection sites minted a *fresh* `uuid4()` per call, cutting the trace chain instead of extending it — the header was present and worthless. Existence is not correctness, so a gate that greps for the header name cannot work. |

Both are proven by a negative test: injecting drift / removing a symbol turns CI red.

## What the runtime-truth gate catches
- A new importer of a `ZOMBIE` / `DORMANT` module from a live anchor (`app/api/`, `app/main.py`, `app/kernel.py`, `app/middleware/`) without an accompanying lock-file update.
- Removing a tracked capability without removing it from `CATALOG`.
- Changing an `expected_status` without regenerating the lock.

## What CI still does NOT catch (tracked as ISS-025, partial mitigation only)
1. WS frame tracing per-frame (still ISS-005). The `path_observer` covers the per-turn span; per-frame WS spans are out of scope here.
2. Persistence authority round-trip with the orchestrator awake (cannot run in CI; requires `docker compose up`).
3. Frontend Next.js build — covered by `frontend-tests`; the remaining gap is live browser journey coverage outside the dedicated live-E2E workflow.

## Updating the gate intentionally
```
python scripts/runtime_truth.py --update   # rewrites .runtime/truth_table.lock.json
git add .runtime/truth_table.lock.json scripts/runtime_truth.py
git commit -m "runtime-truth: <reason>"
```

## بوّابات D-191/D-192 (2026-07-31)

| البوّابة | الوظيفة | الدَّين المُجمَّد |
|----------|---------|------------------|
| `check_exercise_context_single_source.py` | التمرين قيد النقاش مصدره واحد؛ الاستخراج لا يرى نثر الحلّ؛ الوعد البصري يتبع حمولةً مُسلَّمة | **فارغ** |
| `check_constitution_reality.py` (doc-integrity) | الأرقام مشتقّة لا مكتوبة؛ لا تناقض ذاتي في CLAUDE.md؛ ادّعاءات الرموز تُختبَر على المصدر | — |
| `check_no_committed_secrets.py` | مسح أنماط الأسرار على الشجرة المُتتبَّعة (ISS-141 البند 4) | **فارغ** |
| `check_no_new_any.py` | صفر `Any` على `app/integration/`؛ الباقي يتقلّص فقط | 141 |
| `check_router_domain_logic.py` | منطق النطاق لا ينمو في `app/api/routers/` | 13 |
| `check_docs_runtime_parity.py` | **وُصِلت أخيراً** — كانت بوّابةً لا تحرس شيئاً (غير مُشغَّلة في أيّ workflow) | — |


## D-201/D-202 — البوّابتان الجديدتان (2026-08-01)

| البوّابة | ما تفرضه | لماذا |
|---------|----------|-------|
| `check_topic_contract_parity.py` | سجلّ المواضيع (`shared/messaging/topics.py`) == قنوات عقد AsyncAPI == المواضيع المُنشأة في `docker-compose.yml`. الاتجاهان محروسان. | ثلاث نسخٍ من حقيقةٍ واحدة تتباعد حتماً (D-192). موضوعٌ في الكود بلا قناة لا يعرفه مستهلكٌ خارجي؛ وقناةٌ بلا موضوع عقدٌ يعِد بما لا يُنشَر. وموضوعٌ غير مُنشأ صراحةً يعتمد على `auto.create.topics` — حيث يُنشئ خطأٌ مطبعي واحد موضوعاً بلا مستهلك يبتلع الرسائل بصمتٍ حتى ينتهي الاحتفاظ. |
| `check_redaction_parity.py` | الحرفيات التي تُعرِّف «الجواب النهائي» متطابقة بين عقل المونوليث وعقل الأوركستريتور. | D-113 يفرضه عقلان بنسختين. انحرافُ تعبيرٍ نمطي واحد يعني مساراً يحجب ومساراً **يسرّب**، والطالب لا يعرف أيّ عقلٍ أجابه. قاعدة D-013 النثرية مُثبَتُ الخرق — لذلك أُتمِتت في D-174 لسلسلة النماذج، وهنا للحجب (D-203). |
| `check_model_registry.py` | كل نموذج في `MODEL_CHAIN` مُسجَّل بقدراتٍ ودليلٍ مؤرَّخ؛ لا نموذج محظورٍ كلّياً في السلسلة؛ الصدارة تستوفي `REQUIRED_FOR_PRIMARY`. | قاعدة «لا نموذج تفكير-فقط في الصدارة» كانت تعليقاً في رأس ملفّ. التعليق لم يمنع ISS-079: نموذجٌ يُرجِع `content=None` تصدّر السلسلة، فقرأ طالبٌ حقيقي «pepepe aaaa». |


## D-204 — أوّل وظيفة CI تُقلع حاوية فعلاً (2026-08-01)

| الوظيفة/البوّابة | ما تفرضه | لماذا |
|-----------------|----------|-------|
| `event-stack-live` (`ci.yml`، ضمن `required-ci`) | تُقلع Redpanda + bootstrap المواضيع + Temporal + قاعدته بـ`docker compose up`، ثمّ تُشغِّل `scripts/verify_event_stack_docker.py`: صحّة العنقود · شكل المواضيع مقابل السجلّ · رحلة نشر/استهلاك حقيقية · تخطّي إعادة التسليم · وصول الرسالة المسمومة إلى DLQ. | `docker-fullstack-gate.yml` يقول في ترويسته إنّه **لا** يُشغِّل `up`؛ فكان اسمه «full-stack gate» وعمله فحص YAML. النتيجة أنّ Redpanda وTemporal شُحِنا في compose ولم يُقلَعا قطّ. الصور كلّها جاهزة (بلا بناء) فالكلفة دقائق. |
| `check_topic_contract_parity` (مُوسَّعة) | تقارن الآن **الأقسام والاحتفاظ** لا الأسماء فقط. | موضوعٌ باسمٍ صحيح وعدد أقسامٍ خاطئ يكسر ترتيب أحداث الطالب الواحد بصمت — والاسم وحده لا يكشفه. |

**ما أخرجته هذه الوظيفة في أوّل تشغيل** (كلّها أعطاب حقيقية لا يراها فحصٌ ساكن):
مستهلك Kafka كان **غائباً** كلّياً · `rpk topic create … || true` تبتلع كلّ فشل ·
Redpanda يُعلن `redpanda:9092` فقط فيتعلّق أيّ عميل على المضيف · وقراءة صحّة العنقود
بشريحة ثابتة (`[:20]`) بينما `rpk` يُبطِّن أعرض — فانتظر عنقودٌ **صحيح** مهلته كاملةً.

## D-205 — كلّ صورة تُبنى، والتطبيق داخلها يستورد (2026-08-01)

| الوظيفة/البوّابة | ما تفرضه | لماذا |
|-----------------|----------|-------|
| `images-plan` + `images-build` (`ci.yml`، كلاهما في `required-ci`) | تبني **١٥ صورة** (١١ خدمة في compose + الواجهة + المونوليث + خدمتان خارج compose) بمصفوفة runner لكلّ صورة وكاش GHA، ثمّ تُشغِّل داخل الصورة `python -c "import <module>"`. | لم يكن CI يُشغِّل `docker build` **أبداً**. البناء ليس استيراداً: تبعيةٌ ناقصة في `requirements.txt` تُبنى بلا شكوى وتنهار عند أوّل استيراد — أي أمام طالب. الوظيفتان معاً في `required-ci` لأنّ `images-build` تُتخطّى إن فشلت `images-plan`، والمتخطّاة تُحتسَب نجاحاً. |
| `check_image_matrix_parity.py` (في `guardrails`) | كلّ سياق بناء في `docker-compose.yml` وكلّ `microservices/*/Dockerfile` له إدخال في `config/image_build_matrix.json`، وكلّ إدخال يشير إلى ملفّ موجود، ولا إعفاء من فحص الاستيراد بلا سببٍ منطوق. | بوّابة بناءٍ لا تغطّي إلّا ما تعرفه؛ خدمةٌ تُضاف غداً بلا إدخال تسقط من التغطية بصمت — نفس صنف العطب الذي وُلِدت له `check_topic_contract_parity`. |
| `check_legacy_traffic_zero_window.py` (مُصحَّحة) | تميّز **القياس** من **النائب**: `verified_by` نائباً أو `status: not_measured` ⇒ `NOT MEASURED` ورفضُ المرحلة 5، لا «✅ مُتحقَّق». | كانت تقرأ ملفّاً يقول عن نفسه `ops-placeholder` وتطبع «صفر حركة legacy مُتحقَّق لـ30 يوماً» — بينما المونوليث يخدم 100% من الطلبة. صفرٌ لم يُقَس ليس صفراً (§0). |

**ملاحظة صدق:** الوظيفة تُثبت أنّ الصور **تُبنى وتُستورَد** فقط. الخدمات التطبيقية الثماني
ما زالت غير مُقلَعة في CI، و`Dockerfile.prod` **لم تُشغَّل قطّ** — البناء ليس تشغيلاً.

## بوّابات D-208 (ISS-149 — 2026-08-03)

| البوّابة | ما تفرضه | لماذا وُجدت |
|----------|----------|-------------|
| `check_understanding_evidence.py` | كل `evidence_marker` **عبارة** (≥ كلمتين) تصف آلية، ولا تتقاطع مع علامات النيّة في `shared/intent`؛ ومسارُ القرار (`_has_understanding_evidence`) يقرأ رسالة الحاضر ويُبطِل البرهان على الحيرة والسؤال. الدَّين **فارغ**. | `favorable_cases` أعلن أنّ مؤشّر فهمه هو الاسم المفرد «البسط»، فطابق **سؤال الطالب** «كيف نفرق بين البسط و المقام؟» فحُسِب برهانَ إتقان — ومن يسأل عن شيءٍ يذكر اسمه بالضرورة. البوّابة كشفت حالتين أخريين لم يرهما المسح اليدوي: «مكررة» و`c(11` (رمزٌ يطبعه المعلّم نفسه). |
| `check_gate_parse_honesty.py` | لا `except SyntaxError` حول **تحليل ملفّ** يُرجِع فراغاً أو يتخطّى بلا تسجيل. الدَّين **فارغ**. | **١٣** بوّابة كانت تُبلِّغ «صفر انتهاكات» عن ملفٍّ لم تقرأه — منها حارسُ حقن الصدفة (دَينه صفر · D-187) ومصدرُ النيّة الواحد (D-186) وأثرُ التتبّع (D-189). الدليل حيّ: على 3.11 أبلغت `check_no_new_any` أن `base.py` صار `0× Any` والدَّين ١٢، لأنها عجزت عن قراءته. هذا «الثمن الثالث» داخل الفوارض نفسها. |
| `check_authority_links.py` | كل رابط محلّي في `DOCUMENTATION_INDEX.md` · `.memory/README.md` · `CLAUDE.md` يُشير إلى مسارٍ موجود. الدَّين **فارغ**. | ثلاثة من ٤٧ رابطاً في «خريطة السلطة الكاملة» كانت مكسورة — منها **ADR-006 نفسه**. كشفه سؤالٌ من المالك، لا بوّابة. خريطةٌ تكذب تُقرأ بدقّة ممّن يحاول أن يكون دقيقاً. |
| `check_confusion_never_an_answer` (**مرمىً موسَّع**) | «الحيرة ليست إجابة» على **أربعة** عقول لا اثنين: + `pedagogical_escalation_skill` + `understanding_state_skill`. | البوّابة كانت خضراء بينما الطالب يُهنَّأ على حيرته — لأن العقل الذي أطلق الكارثة كان خارج مرماها. *فارضٌ بلا مرمى*، نفس صنف ISS-148. |
| `check_probability_brain_parity` (**موسَّع**) | علامات الحيرة في الخدمة المصغّرة == القانونية في `shared/intent` (تكافؤ قيمة، بعد التطبيع القانوني). | كانت **٧ مقابل ٢٧** بلا بوّابة، وهي تحكم دخولَ الدور المسارَ التربوي. مسبارٌ تفاضلي: **٤ انحرافات من ٥** صيغ حيرة واقعية، منها الدارجة والفرنسية. |
| `check_intent_single_source` (**موسَّع**) | كل إعفاء «توريد مقصود» يُسمّي بوّابة تكافؤه **الموجودة**، أو يُصرّح «بلا بوّابة تكافؤ» بسببٍ منطوق. | الاستثناء المنطوق كان يصير إعفاءً دائماً: التوريد مشروع دستورياً، لكنّ نسختين بلا حراسة تنحرفان. |
| `run_fitness_gates::_check_interpreter` | يرفض التشغيل على مفسّرٍ أقدم من `target-version` في `pyproject.toml` (**مُشتَقّ** لا رقمٌ ثانٍ — D-192). | على 3.11 تسقط أربع بوّابات بخطأ غامض وتمرّ ثلاث عشرة **خضراءَ كاذبة**. |

كلّها مُثبَتة بتجربة سلبية: إعادةُ «البسط»، ورفعُ الفيتو، وزرعُ ملفٍّ لا يُحلَّل، وحذفُ
علامةٍ من المرآة، وحذفُ اسم الفارض، ورابطٌ إلى العدم — كلٌّ منها حمّر CI ثمّ استُعيد.

## بوّابة القيمة والإيراد (D-210 → D-223 · 2026-08-04)

| البوّابة | ما تفرضه | لماذا وُجدت |
|----------|----------|-------------|
| `check_revenue_doctrine.py` (في `guardrails`) | فصلُ القانون عن الحالة بين `docs/VALUE_DOCTRINE.md` + `docs/REVENUE_ENGINE_SPEC.md` (بلا حالات) و`.memory/revenue_engine_truth.md` (وحدها). سبعة بنود: دليلٌ ملفّي موجود · سُلَّم §6.6 وحده · لا خانة فجوةٍ فارغة · لا حذف صامت (12 طبقة · 14 وحدة · 4 خطوط) · كل بوّابةٍ مذكورة موجودة أو مُعلَنة في `_PLANNED_GATES` · ⛔ لا خانة حالةٍ في وثيقة قانون · وادّعاءات الرموز **في الاتجاهين**. الدَّين المُجمَّد **فارغ**. | وثيقة إيرادٍ تُقرأ من **خارج** الفريق، فادّعاءُ «مبنيّ» وهو غير مبنيّ ليس دَيناً توثيقياً بل ادّعاءً أمام طرفٍ يبني عليه قراراً. وبندان لا يوجدان في أيّ بوّابةٍ أخرى: **(1)** وحدةٌ `ABSENT` **ولها كود** ⇒ أحمر — كل البوّابات تحرس «ادُّعي موجوداً وهو غائب»، والعكس يعني كوداً حيّاً بلا حارسٍ ولا اختبار. **(2)** `_PLANNED_GATES` ثنائية الاتجاه: اسمٌ فيها **موجودٌ فعلاً** ⇒ أحمر، فوثيقةٌ تقول «مستقبلية» عن حارسٍ يعمل تُقلّل من حراستها. |
| `check_revenue_doctrine::_check_maturity_guard` | مسحُ AST على `shared/illusion`: كل دالّةٍ تبني `ConceptIllusion` تفحص `MIN_OBS` في جسمها. | سابقة ISS-148: `delivered` معاملٌ نساه **سبعةٌ من ثمانية** مُنادين، فصار «صمّام الأمان» عطباً موزّعاً على مواضع النداء. تصنيفٌ بملاحظتين هو تقريرٌ كاذب يُعرَض على وليّ. |

مُثبَتة بـ**إحدى عشرة** تجربة سلبية (`tests/architecture/test_revenue_doctrine_gate.py`)،
وفيها **خطُّ أساسٍ أخضر** لولاه لكانت كلّها «حمراء لسببٍ آخر». ⚠️ ودرسٌ مُقاس: `scripts/`
في المرآة يجب أن يكون مجلَّداً حقيقياً لا رابطاً رمزياً — البوّابة تشتقّ الجذر بـ
`Path(__file__).resolve()`، و`resolve()` تتبع الروابط فتعود إلى المستودع الحقيقي وتصير
كلّ الحالات بلا أثر.

## بوّابة محرّك التنفيذ المعرفي (D-224/D-225 · 2026-08-04)

| البوّابة | ما تفرضه | لماذا وُجدت |
|----------|----------|-------------|
| `check_cognitive_execution.py` (في `guardrails`) | فصلُ القانون عن الحالة بين `docs/architecture/COGNITIVE_EXECUTION_ENGINE.md` و`.memory/cognitive_execution_truth.md`؛ ١٣ طبقة + ٤ آفاق سوق بدليلٍ ملفّي موجود وفجوةٍ مكتوبة وحالةٍ من سُلَّم §6.6؛ لا حذف صامت؛ كل بوّابةٍ مذكورة موجودة أو مُعلَنة في `_PLANNED_GATES` (ثنائية الاتجاه). | وثيقةٌ تصف «محرّك تعلّمٍ قابل للتحقّق» تتحوّل إلى كذبٍ مهذَّب إن لم يحرسها شيء — وقد حدث ذلك مرّتين (D-188 · D-209). |
| `check_cognitive_execution::_check_llm_sandbox_interlock` | ⛔ **قفل D-187 بـAST**: أيّ وحدة في `app`·`microservices`·`shared`·`scripts` تستورد مُنفِّذ الصندوق **و** عميل نموذجٍ لغوي معاً ⇒ CI أحمر. الإعفاء يُصرَّح بسببه (فراغ ⇒ أحمر) ويُحذَف حين يبطل (بائت ⇒ أحمر). الدَّين **فارغ**. | الصندوق مبنيٌّ ويشغّل `python`/`pip`/`git`/`npm`، والمستخدمون قاصرون. والمسافة بين «قدرة» و«حادثة أمنية» سطرُ استيرادٍ واحد يكتبه وكيلٌ متحمّس بعد أشهر. وكلّ قانونٍ نثري في هذا المستودع خُرِق مرّةً على الأقلّ (D-013 هو المثال المُوثَّق) — فالقفل بنيةٌ لا نصّ. |

مُثبَتة بـ**أربع عشرة** تجربة سلبية (`tests/architecture/test_cognitive_execution_gate.py`)،
منها خمسٌ للقفل وحده: الجمع يُمنَع · الصندوق وحده يمرّ · النموذج وحده يمرّ (فالقفل يمنع
**الجمع** لا القدرة) · إعفاءٌ بلا سبب أحمر · إعفاءٌ بائت أحمر.

## D-267 — the verification-layer gate (added 2026-08-18)

| Gate | What it enforces | Why it exists |
|---|---|---|
| `check_naas_verification.py` | The six-state gate machine (`ABSENT → PENDING → CLEARED \| BLOCKED → EXPIRED \| REASSESS_REQUIRED`) with **no vague token** and **no `ABSENT → CLEARED` jump**; evidence-schema conformance where `expires_at` is **derived** from `issued_at + validity_days`; quantitative thresholds (`Δ ≥ 15%` over a pinned baseline with `runs ≥ 3`; `≥ 3` exploit classes with **distinct root causes**; a **settled transaction** — never stars, meetings or an unpaid LOI); the credibility limit (no unfalsifiable claim, no price without a `PRICING HYPOTHESIS` tag); the three-path import boundary (product ⇸ student path, no domain inside the core); and the **bounded** commercial block. | The investment decision that founded D-267 named its own weakest link honestly: **NOT FOUND — an independent paid audit contract**. The chain breaks at REAL PAYMENT, not at the problem or the budget, so the danger is not failure but *unfalsifiable success*: a price hypothesis read as pricing evidence, three variants of one exploit read as three classes, a bounty read as a customer. Two structural rules carry the most weight: **CI verifies evidence and never decides law** (a machine as `issuer` is a blank-cheque signature), and the legal gate blocks **external commercial actions only** — local development, synthetic/open-data experiments and benchmark building stay green, because governance exists to stop us deceiving ourselves, not to stop the work. |

Proven by **27 negative cases** plus a pristine baseline
(`tests/architecture/test_naas_verification_gate.py`) — including the one that
proves the block is bounded: R&D work stays green while the legal gate is `ABSENT`.

## D-275 / D-277 / ADR-016 — سياق الوكيل وقبول التغيير والتوثيق

| Gate | What it enforces | Why it exists |
|---|---|---|
| `check_agent_context.py` | Agent authority order, boot sequence, required sources, and commercial/evidence trace resolve to existing paths. | يمنع الوكيل من العمل بذاكرة خاصة أو مصدر غير مصنّف. |
| `check_code_acceptance.py` | Current change packet has standards, evidence, local application, production trace, curriculum consideration, zero deletions, and a fresh content fingerprint. | يمنع إعلان قبول تغيير لم تُثبت حزمته أو تغيّر بعد تسجيل بصمته. |
| `check_documentation_contract.py` | Live-document manifest, local links, executable command truth, stale operational references, CI wiring, and mandatory agent/contributor references. | يمنع رجوع الأوامر القديمة والروابط المكسورة ويجعل التوثيق جزءًا من required-ci. |
| `check_dual_track_alignment.py` | Engineering capability and production/commercial evidence remain aligned. | يمنع تحويل التصميم أو البحث إلى ادعاء قيمة أو إيراد بلا دليل. |
| `check_reference_backbone.py` | Pinned reference backbone remains additive, non-runtime, and represented by the declared source files. | يمنع استبدال مصدر مرجعي أو إدخاله إلى runtime بصمت. |
| `check_source_adoption_matrix.py` | Every discovered source has status, purpose, local application, enforcer, and owner. | يمنع استخدام مصدر خارجي كسلطة غير معلنة أو تبعية غير مراجعة. |

`check_documentation_contract.py` is deliberately executed in both `.github/workflows/doc_integrity.yml` and the `guardrails` job in `.github/workflows/ci.yml`; a documentation-only PR therefore cannot bypass the required path.

## ISS-199 — التأجيل يُصرَّح، ولا يُعمَّر بعد بلاغه (2026-08-30)

| Gate | What it enforces | Why it exists |
|---|---|---|
| `check_e2e_deferred_findings.py` | كل مُعرَّفٍ في `scripts/e2e/deferred_findings.py` له عنوانٌ في `.memory/issues.md` **وحالةٌ مفتوحة مُصرَّحة** (🔴/🟡)؛ وسببُ التأجيل منطوقٌ لا مقتضب؛ و`FROZEN_DEFERRED_COUNT` يطابق السجلّ **في الاتجاهين**؛ ولا سكربت e2e يبني مخالفةً موسومةً ببلاغ دون قراءة السجلّ الواحد؛ وملفٌّ يتعذّر تحليله يُبلَّغ عنه انتهاكاً لا يُبتلَع. | الدفعة `3176fe6` وصلت `live-e2e` بـ`required-ci` ولم تلمس رأس `live-e2e.yml` القائل «**ليس** في `required-ci`» (`diff`ها يبدأ عند `@@ -25`) — فصارت بوّابةٌ **حاجبة** مُوجَّهةً إلى **ISS-150** وهو 🔴 مفتوحٌ بقرارٍ مكتوبٍ بتأجيله. النتيجة: خمسة تشغيلاتٍ حمراء متتالية على `main` في المستودعين، وامتناعُ الأخضر بالبناء لا بالمصادفة. والتأجيل بلا حارس يتحوّل إلى إسكاتٍ دائم — فهذه البوّابة تجعل بلاغاً أُغلق وبقي مؤجَّلاً يُحمِّر CI (D-188)، وقائمةً ثانية للنيّة نفسها مستحيلة (D-186). |
