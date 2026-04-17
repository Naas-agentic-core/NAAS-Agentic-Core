# التقرير الجنائي الفائق: كارثة «عمى السياق» في CogniForge / Overmind
## نسخة Enterprise Forensics v4 — موجهة للأنظمة العملاقة شديدة التعقيد

> هذا التقرير مكتوب بصيغة تشغيلية تنفيذية (Engineering + SRE + Incident Command).  
> الهدف ليس الوصف، بل **تشخيص جذري قابل للإثبات** + **خطة إغلاق فني** بقياسات نجاح واضحة.

---

> **مرفق إثبات آلي:** راجع التقرير المولد تلقائيًا: `docs/architecture/CONTEXT_BLINDNESS_DEEP_TRACE_REPORT_AR.md` للحصول على سجل أدلة بسطور وملفات محددة.
> **حزمة جنائية آلية (JSON):** `docs/architecture/CONTEXT_BLINDNESS_FORENSIC_PACK_AR.json` للاستهلاك الآلي في الحوكمة ولوحات المراقبة.

## 1) ملخص تنفيذي حاسم (Executive Verdict)

### الحكم النهائي
**كارثة عمى السياق ليست خطأ ذكاء اصطناعي مستقل.**  
هي **فشل موثوقية سياق متعدد الطبقات** (Multi-Layer Context Reliability Failure) بسبب غياب عقد استمرارية مُلزِم end-to-end.

### السبب الأعلى (Root Cause of Root Causes)
غياب **Verifiable Context Continuity Contract** يثبت، لكل turn، أن:
1. الهوية (`conversation_id` + `thread_id`) متماسكة.
2. المرساة المرجعية (Anchor) موجودة وقابلة للاستخدام.
3. نافذة السياق الفعالة لم تسقط تحت حد السلامة.
4. failure mode عند غياب أي شرط يكون **صريحًا** وليس صامتًا.

### نتيجة هذا الغياب
أي طبقة تعمل بسياسة "أفضل جهد"، فتتراكم انحرافات صغيرة إلى انهيار سياقي كبير (catastrophic contextual misbinding).

---

## 2) تعريف الحادثة بصيغة SRE

## 2.1 اسم الحادثة
**AFM — Ambiguous Follow-up Misbinding**

## 2.2 تعريف دقيق
حادثة تحصل عندما يكون follow-up إحالي (مثل: "ما هي عاصمتها؟") لكن السياق الفعلي الذي يصل إلى النموذج لا يحتوي الكيان المرجعي الصحيح، رغم أن المستخدم يرى تاريخًا كافيًا في الواجهة.

## 2.3 مؤشرات العرض
- Clarification غير مبرر بعد سؤال سابق واضح.
- إجابة دقيقة لكن لكيان خاطئ.
- سلوك يختلف حسب القناة/الجهاز/التوقيت.
- ارتفاع أخطاء "clarify" بعد reconnect أو burst traffic.

## 2.4 الشدة (Severity)
- **P1:** AFM > 5% من follow-up traffic لمدة 10 دقائق.
- **P2:** AFM بين 1% و5% أو مرتبط بحالات reconnect فقط.
- **P3:** AFM نادر (<1%) وغير قابل لإعادة الإنتاج بسهولة.

---

## 3) النموذج الفني: أين يعيش السياق فعليًا؟

السياق ليس كائنًا واحدًا. هو خمس نسخ متزامنة:

1. **Visual Context (UI):** ما يراه المستخدم.
2. **Sent Context (Client Payload):** ما أُرسل عبر WS فعليًا.
3. **Persisted Context (DB):** تاريخ المحادثة المخزن.
4. **Hydrated Context (Server Runtime):** ناتج الدمج والتنقية.
5. **Effective Model Context (LLM Input):** النافذة النهائية بعد القص والتطبيع.

### الملاحظة الحرجة
حين لا توجد آلية تحقق consistency بين (1) و(5)، يصبح AFM حتميًا إحصائيًا مع نمو الحمل وتعقّد المحادثات.

---

## 4) سجل الأدلة التقنية (Evidence Matrix)

## E-01 — قص مبكر من جهة العميل
- العميل يبني `client_context_messages` ثم يطبق `slice(-30)`.
- هذا يعني فقد سياق قديم قبل دخول الشبكة أصلًا.
- الأثر: anchor قد يختفي حتى لو موجود بصريًا للمستخدم.

## E-02 — الاعتماد على توفر conversation_id لحظيًا
- `conversation_id` لا يدخل payload إلا إذا كان متاحًا لحظة الإرسال.
- أي race/reconnect قد ينتج follow-up بدون هوية ثابتة.

## E-03 — انقسام سلوكي بين modern وlegacy
- modern: قناة مستمرة مع إدارة أحداث.
- legacy: إغلاق socket وفتح جديد لكل إرسال.
- الأثر: non-deterministic context continuity.

## E-04 — دمج سياقي مع حدود متتالية
- extraction cap + merge cap + history cap + digest compression.
- الأثر: شلال قص (Truncation Cascade) يغيّر model-effective context جذريًا.

## E-05 — fallback بارد صامت
- عند غياب checkpointer/history، الاستمرار يتم برسالة current objective فقط.
- الأثر: false success في المراقبة، وفشل سياقي عند المستخدم.

## E-06 — Recovery إحالي heuristic
- استخراج الكيان المرجعي يعتمد على heuristics token-based.
- عند history مشوه، recovery يفشل دون مسار إجباري واضح.

## E-07 — خطر drift بين المسارات
- hydration logic موزع/مكرر في مسارات متوازية.
- أي تغيير غير متزامن يخلق تباينًا في السلوك.

## E-08 — غياب قياسات متخصصة
- لا يوجد SLI رسمي يقيس "سلامة السياق" بشكل مباشر.
- الاكتشاف غالبًا يأتي من feedback المستخدمين بدل alarms مبكرة.

---

## 5) FMEA موسعة (Failure Mode & Effects Analysis)

| ID | نمط الفشل | السبب المباشر | الأثر | قابلية الاكتشاف الحالية | RPN (نسبي) |
|----|-----------|---------------|-------|--------------------------|------------|
| FM-01 | Identity Drift | conversation_id غير ثابت | misbinding | منخفضة | حرج |
| FM-02 | Reconnect Race | out-of-order events | فقد استمرارية | منخفضة | حرج |
| FM-03 | Channel Split | modern/legacy mismatch | نتائج غير حتمية | متوسطة | عالٍ |
| FM-04 | Truncation Cascade | caps متعددة | anchor dropout | منخفضة | حرج |
| FM-05 | Silent Cold Start | fallback غير صريح | false-success | منخفضة | عالٍ |
| FM-06 | Weak Anchor Recovery | heuristic only | clarify loops | متوسطة | عالٍ |
| FM-07 | Hydration Drift | duplicated logic | endpoint divergence | منخفضة | عالٍ |
| FM-08 | No Context SLOs | قياس ناقص | slow MTTR | منخفضة | حرج |
| FM-09 | No Incident Taxonomy | حوكمة ناقصة | استجابة ad-hoc | متوسطة | متوسط-عالٍ |
| FM-10 | UX/Model Mismatch | فجوة إدراكية | فقد ثقة المستخدم | عالية | عالٍ |
| FM-11 | Chaos Gap | نقص اختبارات reconnect | اكتشاف متأخر | منخفضة | عالٍ |
| FM-12 | Contract Ambiguity | لا proof-of-continuation | تعذر الإثبات | منخفضة | حرج |

---

## 6) شجرة الإخفاق (Fault Tree) + Minimal Cut Sets

### Top Event
**AFM: Follow-up ambiguity handled without valid anchor.**

### Cut Sets حرجة
1. `{conversation_id missing} + {no hard reject}`
2. `{history truncated} + {no anchor memory}`
3. `{reconnect race} + {event ordering gap}`
4. `{cold-start fallback} + {ambiguous query}`

### النتيجة العملية
إذا لم تُغلق هذه cut sets عبر controls إلزامية، AFM سيبقى recurring **by architecture**.

---

## 7) التحليل التفاضلي (Differential Diagnosis)

### H1: المشكلة LLM-only
- غير كافية كتفسير: نفس النموذج ينجح عند ثبات السياق.

### H2: المشكلة DB-only
- غير كافية: الفقد قد يحدث قبل DB في client/transport.

### H3: المشكلة UX-only
- غير كافية: fallback server-side يمرر cold start بلا incident event.

### الاستنتاج
السبب مركّب: **Cross-Layer Reliability Failure**.

---

## 8) تحليل 5-Why الصارم

1. لماذا فشل follow-up؟
   - لأن anchor لم يكن حاضرًا في model input.
2. لماذا لم يكن anchor حاضرًا؟
   - لأن context الفعّال كان ناقصًا/غير متسق.
3. لماذا context ناقص؟
   - بسبب truncation + identity race + drift.
4. لماذا لم يوقف النظام الطلب؟
   - لأن fallback صامت لا يعتبر الحالة حادثة.
5. لماذا تتكرر؟
   - غياب contract + قياس + بوابات إطلاق.

---

## 9) بروتوكول إثبات استمرارية السياق (Context Continuity Contract v3)

## 9.1 حقول إلزامية لكل follow-up
- `conversation_id`
- `thread_id`
- `turn_index`
- `continuation_of_turn`
- `context_checksum`
- `anchor_hint` (اختياري لكن موصى به)

## 9.2 قواعد رفض إلزامية
- إذا follow-up ambiguous و`conversation_id` مفقود => `CONTEXT_IDENTITY_MISSING`.
- إذا checksum لا يطابق window policy => `CONTEXT_INTEGRITY_FAILED`.
- إذا لا anchor بعد recovery => `CONTEXT_ANCHOR_MISSING` + event للعميل.

## 9.3 مبدأ التصميم
**Fail closed for context-critical turns.**

---

## 10) خطة احتواء فورية (0–72h)

## C-1: إيقاف الفشل الصامت
- emit `context_missing` event عند ambiguous+no-anchor.
- لا تمرير مباشر للـLLM في هذه الحالة.

## C-2: تشديد الهوية
- رفض follow-up بلا identity بعد init.
- forced re-sync بدل new conversation silent.

## C-3: تجميد legacy في البيئات الحرجة
- feature flag kill-switch.

## C-4: Telemetry ساخنة
- `conversation_id_missing_followup_total`
- `cold_start_followup_total`
- `anchor_recovery_failed_total`
- `context_contract_violation_total`

## C-5: Runbook عمليات
- trigger: `cold_start_followup_total` يتجاوز threshold لـ 5 دقائق.
- action:
  1) Enable strict identity mode.
  2) Disable legacy path.
  3) Raise context logs to debug sampling 100%.
  4) Snapshot model-effective context for forensic packet.

---

## 11) خطة تثبيت متوسطة (2–4 أسابيع)

## S-1: Anchor Memory Primitive
- state مستقل لكل conversation يحفظ آخر كيان مرجعي مؤكد.
- precedence: anchor memory > heuristic extraction.

## S-2: Relevance-Aware Windowing
- score = recency + entity relevance + unresolved pronouns.
- no fixed-only slicing.

## S-3: Hydration Parity Tests
- نفس المدخلات عبر كل المسارات => نفس hydrated output.

## S-4: Chaos Context Suite
- reconnect mid-stream.
- rapid follow-up (<500ms).
- out-of-order events.
- mobile jitter profile.

## S-5: Incident Taxonomy
- AFM-P1 / AFM-P2 / AFM-P3 مع playbook إلزامي لكل مستوى.

---

## 12) تحصين استراتيجي (1–2 Quarter)

1. **Context Reliability Budget** ضمن SRE governance.
2. **Central Context Service** كمصدر حقيقة واحد.
3. **Context Event Sourcing** للتتبّع الزمني للانهيار.
4. **Release Gate**: منع النشر إذا فشل AFM suite.
5. **GameDay دوري** لحوادث السياق مثل game days للlatency.

---

## 13) مقاييس SLI/SLO الدقيقة

## SLI
- `FollowupWithoutAnchorRate`
- `ColdStartOnFollowupRate`
- `IdentityMismatchRate`
- `AnchorRecoverySuccessRate`
- `HydrationParityRate`
- `ContextContractViolationRate`

## SLO المستهدف
- `ColdStartOnFollowupRate < 0.5%`
- `AnchorRecoverySuccessRate > 99%`
- `HydrationParityRate = 100%`
- `ContextContractViolationRate < 0.1%`
- `P1 AFM = 0` خلال 30 يومًا متتالية

---

## 14) سيناريوهات إعادة الإنتاج (Forensic Repro Suite)

## R1 — Rapid Follow-up Race
1. baseline entity turn.
2. send follow-up عند أول delta.
3. تحقق من identity fields + checksum.
4. قارن visual context vs model-effective context.

## R2 — Reconnect Perturbation
1. قطع WS بعد init مباشرة.
2. reconnect مع jitter 100–800ms.
3. send ambiguous follow-up.
4. verify no silent cold start.

## R3 — Deep History Truncation
1. conversation طويلة تتجاوز كل caps.
2. anchor مبكر + follow-up متأخر.
3. verify anchor survival path.

## R4 — Channel Drift
1. نفس السيناريو عبر modern وlegacy.
2. compare hydrated/model-effective contexts.
3. أي فرق = release blocker.

---

## 15) Definition of Done الصارم

لا يعتبر الحادث مغلقًا إلا إذا تحقق:

- ✅ تمر جميع اختبارات AFM suite.
- ✅ تفعيل dashboards + alerts + runbook.
- ✅ انخفاض AFM الفعلي إلى أقل من العتبات المتفق عليها.
- ✅ إثبات parity بين المسارات.
- ✅ تنفيذ GameDay ناجح وتوثيق postmortem.

---

## 16) Backlog تنفيذي (جاهز للتحويل إلى Tickets)

| Priority | Work Item | Owner | Effort | Risk Reduction |
|----------|-----------|-------|--------|----------------|
| P0 | Strict Context Contract enforcement | Backend | M | Very High |
| P0 | context_missing protocol event | Backend/Frontend | S | High |
| P0 | Legacy kill-switch in prod | Platform | S | High |
| P1 | Anchor memory state | Orchestrator | M | Very High |
| P1 | Relevance windowing | Orchestrator | M/L | High |
| P1 | Hydration parity tests | QA/Backend | M | High |
| P1 | AFM dashboards/alerts | SRE | S | High |
| P2 | Context event sourcing | Platform | L | Medium-High |
| P2 | Quarterly Context GameDay | SRE/Eng Mgmt | S | Medium |

---

## 17) الخلاصة الإدارية الهندسية

التشخيص العميق يثبت أن "عمى السياق" نطاق موثوقية مستقل مثل latency وavailability.  
وأي محاولة علاج سطحية (prompt tweaks فقط) ستفشل على المدى المتوسط.

**القرار الصحيح للمشاريع العملاقة:**
- Context Reliability كبرنامج رسمي متعدد الفرق،
- بعقود صارمة، قياس حي، اختبارات فوضى، وبوابات إطلاق.

عندها فقط ينتقل النظام من "يبدو ذكيًا" إلى "موثوق إنتاجيًا".

