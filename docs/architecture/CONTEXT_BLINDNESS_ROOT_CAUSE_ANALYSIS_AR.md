# التشخيص الفائق لــ «كارثة عمى السياق»
## CogniForge / Overmind — تقرير جنائي هندسي مستوى Incident Commander (IC-L5)

> هذا المستند ليس مقالًا وصفيًا.  
> هذا **ملف تحقيق هندسي** يصلح لإدارة حادثة إنتاجية في نظام موزع عالي التعقيد، ويحوّل المشكلة إلى أسباب قابلة للقياس، قابلة للاختبار، وقابلة للإغلاق (Closure Criteria).

---

## 0) البيان التنفيذي الحاسم

المشكلة ليست "النموذج لا يفهم".  
المشكلة هي **انهيار عقدة الاستمرارية السياقية** عبر سلسلة موزعة:

`Client State -> WS Contract -> Conversation Identity -> Hydration -> Graph Window -> Reference Recovery`

أي خلل في هذه السلسلة ينتج مخرجات تبدو "منطقية لغويًا" لكنها "خاطئة سياقيًا".

### الحكم الجنائي النهائي

**Root Cause Thesis:** لا يوجد **عقد سياق قابل للتحقق (Verifiable Context Contract)** مفروض end-to-end مع آليات فشل صريحة.  
النتيجة: كل طبقة تشتغل "أفضل جهد"، فتتراكم الانحرافات حتى تنهار الإحالة المرجعية.

---

## 1) تعريف الحادثة كما تُدار في أنظمة Mission-Critical

### 1.1 اسم الحادثة
**AFM (Ambiguous Follow-up Misbinding Incident)**

### 1.2 تعريف رسمي
حادثة يحصل فيها Follow-up إحالي (ضميري/مرجعي) بينما النموذج يعمل على سياق لا يحتوي المرساة المرجعية الصحيحة.

### 1.3 أعراض الإنتاج
1. طلب توضيح غير لازم بعد turn واضح سابقًا.
2. إجابة صحيحة لكن لكيان خاطئ (semantic misbinding).
3. تفاوت السلوك بين نفس المحادثة على أجهزة/قنوات مختلفة.
4. إعادة سؤال أساسي وكأن session جديدة.

### 1.4 شدة الحادثة
- **P1** إذا كان الخطأ يتكرر على أسئلة إحالية أساسية (>5% من follow-up traffic).
- **P2** إذا كان متقطعًا لكن قابلًا لإعادة الإنتاج على mobile/reconnect.
- **P3** إذا كان نادرًا ومحصورًا في legacy path.

---

## 2) نموذج الثقة (Trust Model) ومن أين يُفترض أن يأتي السياق

السياق ليس حقلًا واحدًا؛ هو 5 طبقات حالة:

1. **Client Visual State**: ما يراه المستخدم على الشاشة.
2. **Client Sent Context**: ما يرسله العميل فعليًا (`client_context_messages`).
3. **Server Persisted History**: ما هو محفوظ في DB.
4. **Hydrated Runtime Context**: الدمج بعد الفلاتر والقص.
5. **Model Effective Context**: ما دخل فعليًا للـ graph/LLM.

### قاعدة ذهبية
إذا لم نثبت تطابقًا مقبولًا بين (1) و(5)، فالنظام غير موثوق سياقيًا مهما كانت جودة النموذج.

---

## 3) سجل الأدلة الجنائي (Evidence Ledger)

> الهدف هنا: كل ادعاء له نقطة ملاحظة تقنية.

### E-01 — العميل يقص السياق قبل الإرسال
- `buildClientContextMessages` يحصر آخر 30 رسالة.
- هذا قرار فقد معلومات مبكر (upstream truncation).

### E-02 — سياق الهوية مرهون بالحالة اللحظية
- `conversation_id` لا يُرسل إلا إذا كان متاحًا لحظة الإرسال.
- عند race/reconnect قد يخرج follow-up بلا هوية مثبتة.

### E-03 — مسار legacy بسلوك socket مغاير جذريًا
- legacy يغلق socket الحالي ثم يفتح socket جديد لكل إرسال.
- هذا يكسر فرضية session continuity تحت jitter.

### E-04 — الخادم يعيد بناء التاريخ بحدود قص داخلية
- حدود قص متعددة (`MAX_HISTORY_MESSAGES` وغيرها).
- الرسائل الأقدم تتحول إلى digest مضغوط.

### E-05 — fallback بارد عند غياب checkpointer/history
- المسار يكمل بالرسالة الحالية فقط (cold-start semantic).
- لا يوجد protocol-level incident event إلزامي للمستخدم/العميل.

### E-06 — استرجاع الكيان المرجعي heuristic
- يعتمد على token filters، حساس لتشوه history.
- لا توجد "ذاكرة مرساة" صريحة مستقلة عن history الخام.

### E-07 — خطر انجراف المسارات
- وجود hydration logic في أكثر من مسار (facade/orchestrator) يزيد drift risk.

---

## 4) تحليل أنماط الفشل (FMEA الممتد)

## FM-01 — Conversation Identity Drift
- **Trigger:** follow-up مرسل قبل تثبيت/استعادة conversation identity.
- **Failure Mechanism:** `_ensure_conversation` قد يبدأ سلسلة/تحميل تاريخ غير مطابق.
- **Detection Today:** ضعيف.
- **Containment Needed:** hard precondition + protocol error.

## FM-02 — Transport Race Under Reconnect
- **Trigger:** reconnect/jitter/message burst.
- **Mechanism:** out-of-order perception بين `conversation_init` وturn التالي.
- **Effect:** misbinding للسياق.

## FM-03 — Behavioral Split (Modern vs Legacy)
- **Trigger:** اختلاف channel/runtime.
- **Mechanism:** socket lifecycle متعارض.
- **Effect:** non-deterministic reproducibility.

## FM-04 — Multi-Stage Truncation Collapse
- **Trigger:** محادثات أطول من النافذة.
- **Mechanism:** قص متسلسل + ضغط digest.
- **Effect:** anchor dropout.

## FM-05 — Silent Cold-Start Degradation
- **Trigger:** checkpointer unavailable + history absent.
- **Mechanism:** graceful continuation بلا hard fail.
- **Effect:** false-success ops signal.

## FM-06 — Anchor Recovery Fragility
- **Trigger:** pronoun-heavy follow-up.
- **Mechanism:** heuristic extraction دون canonical anchor state.
- **Effect:** clarify loop أو mis-answer.

## FM-07 — Hydration Drift Across Paths
- **Trigger:** تعديل جزئي في أحد المسارات.
- **Mechanism:** duplicated logic divergence.
- **Effect:** endpoint inconsistency.

## FM-08 — Missing Context SLOs
- **Trigger:** لا مقاييس متخصصة.
- **Mechanism:** حادثة تُكتشف من الشكاوى لا telemetry.
- **Effect:** slow MTTR + recurrence.

## FM-09 — No Incident Taxonomy for Context
- **Mechanism:** لا مستويات incident context.
- **Effect:** ad-hoc mitigation.

## FM-10 — UX/Model Reality Mismatch
- **Mechanism:** المستخدم يرى history كامل، النموذج لا.
- **Effect:** perceived catastrophic trust breach.

## FM-11 — Incomplete Chaos Validation
- **Mechanism:** اختبارات لا تغطي reconnect/rapid follow-up بصورة منهجية.
- **Effect:** production-first discovery.

## FM-12 — Contractual Ambiguity of Follow-up
- **Mechanism:** follow-up لا يحمل proof أنه continuation مع checksum.
- **Effect:** cannot prove continuity at protocol level.

---

## 5) شجرة العطب السببية (Fault Tree)

### Top Event
**AFM = Follow-up understood without required anchor**

### Minimal Cut Sets (أمثلة)
- {Identity drift, no hard fail}
- {History truncated, no anchor memory}
- {Reconnect race, out-of-order state}
- {Cold-start fallback, ambiguous query}

### النتيجة
إذا لم نغلق minimal cut sets عبر controls صريحة، الحادثة ستبقى recurring by design.

---

## 6) التحليل التفاضلي (Differential Diagnosis)

### فرضية H1: المشكلة من LLM فقط
**مرفوضة جزئيًا** — لأن نفس النموذج قد يعمل جيدًا حين يصل anchor صحيح.

### فرضية H2: المشكلة DB فقط
**مرفوضة جزئيًا** — لأن الفقد يحدث قبل DB أيضًا (client truncation / transport race).

### فرضية H3: المشكلة UI فقط
**مرفوضة جزئيًا** — لأن fallback server-side يمرر cold-start دون incident signal.

### الاستنتاج
السبب **Systemic Cross-Layer Coupling Failure** وليس سببًا أحاديًا.

---

## 7) تحليل 5-Why الحقيقي

1. لماذا فشل follow-up؟  
   لأن anchor لم يكن فعالًا في model input.
2. لماذا anchor غير فعال؟  
   لأن history الفعال كان ناقصًا/مبتورًا/غير متزامن.
3. لماذا history ناقص؟  
   بسبب truncation cascade + identity/transport race.
4. لماذا لم يُحتوَ الفشل؟  
   لأن fallback صامت وليس explicit failure.
5. لماذا يتكرر؟  
   لغياب contract قابل للتحقق + غياب SLO/alerts متخصصة.

**السبب الجذري الأعلى:** غياب Context Reliability Architecture وليس خطأ prompt فقط.

---

## 8) هندسة الاحتواء الفوري (0–72 ساعة)

## C-1: Stop Silent Fail
- إدخال event إلزامي `context_missing` عند ambiguous + no anchor.
- منع تمرير الطلب للـ LLM قبل محاولة recovery policy.

## C-2: Enforce Identity Preconditions
- follow-up بعد init دون `conversation_id` => reject + re-sync handshake.
- لا إنشاء سلسلة جديدة صامتًا في هذا السيناريو.

## C-3: Freeze Legacy Path for Critical Environments
- إغلاق legacy في production الحساسة عبر feature flag.

## C-4: Hot Telemetry
- Counters فورية:
  - `conversation_id_missing_followup_total`
  - `cold_start_followup_total`
  - `anchor_recovery_failed_total`

## C-5: Operator Runbook
- إذا ارتفع `cold_start_followup_total` فوق threshold لمدة 5 دقائق:
  1) force sticky identity mode
  2) disable legacy
  3) activate verbose context traces

---

## 9) برنامج التثبيت (2–4 أسابيع)

## S-1: Context Contract v2 (إلزامي)
حقول follow-up الإلزامية:
- `conversation_id`
- `thread_id`
- `turn_index`
- `continuation_of_turn`
- `context_checksum`

## S-2: Anchor Memory Primitive
- خزن آخر Entity Anchor مؤكد لكل conversation بشكل مستقل عن message window.
- استخدمه أولًا قبل heuristic extraction.

## S-3: Relevance Windowing Engine
- recency + anchor relevance + unresolved references.
- لا تعتمد solely على fixed slice.

## S-4: Contract Tests Between Paths
- نفس payload عبر façade/orchestrator يجب أن ينتج نفس hydrated context.

## S-5: Chaos Suite (Mandatory)
- reconnect منتصف stream.
- rapid follow-up (<500ms بعد init).
- out-of-order events.
- mobile jitter profile.

---

## 10) التحصين الاستراتيجي (1–2 Quarter)

1. **Context Reliability Budget** مثل error budget لكن للسياق.
2. **Central Context Service** (single source of truth) بدل منطق مبعثر.
3. **Context Event Sourcing** لتفسير سبب فقد anchor زمنيًا.
4. **Formal Context Incident Template** في كل postmortem.
5. **Release Gate** يمنع الإطلاق إذا فشلت اختبارات AFM الحرجة.

---

## 11) مؤشرات القياس والقبول (SLO/SLI/DoD)

## SLI المقترحة
- `FollowupWithoutAnchorRate`
- `ColdStartOnFollowupRate`
- `IdentityMismatchRate`
- `AnchorRecoverySuccessRate`
- `HydrationParityRate`

## أهداف SLO
- `ColdStartOnFollowupRate < 1%`
- `AnchorRecoverySuccessRate > 98%`
- `HydrationParityRate = 100%`
- `P1 AFM incidents = 0` خلال نافذة 30 يومًا

## Definition of Done
- نجاح suite AFM بالكامل.
- dashboard + alerts فعالة.
- runbook مجرب في تمرين محاكاة.
- لا clarify غير لازم في سيناريوهات pronoun القياسية.

---

## 12) بروتوكول إعادة الإنتاج المختبري (Repro Lab)

### سيناريو R1 — Rapid Follow-up Race
1. أرسل سؤال baseline يحدد كيانًا.
2. فور استقبال أول دلتا، أرسل follow-up إحالي.
3. راقب هل وصل `conversation_id` و`thread_id` فعليًا.
4. افحص model input snapshot.

### سيناريو R2 — Reconnect Mid-Conversation
1. اقطع WS بعد `conversation_init` مباشرة.
2. أعد الاتصال خلال نافذة jitter.
3. أرسل follow-up إحالي.
4. تحقق من sticky identity continuity.

### سيناريو R3 — Long Context Truncation
1. ابنِ محادثة أطول من حدود القص الحالية.
2. ضع anchor مبكرًا ثم follow-up لاحقًا.
3. افحص إن كان anchor survived إلى model-effective context.

---

## 13) اختبار صحة الفرضية (Hypothesis Verification)

لكي نثبت أن العلاج صحيح، يجب أن نرى:

1. انخفاض فوري في `conversation_id_missing_followup_total` بعد C-2.
2. انخفاض `cold_start_followup_total` بعد C-1.
3. ارتفاع `AnchorRecoverySuccessRate` بعد S-2.
4. اختفاء التباين channel-based بعد C-3/S-4.

إذا لم تتحسن هذه المؤشرات، فالعلاج غير كافٍ أو التشخيص ناقص.

---

## 14) قرارات تنفيذية لا تقبل التأجيل

- [ ] إعلان AFM كفئة incident رسمية.
- [ ] تطبيق Context Contract v2 كمتطلب release.
- [ ] تعطيل legacy path في البيئات الحرجة الآن.
- [ ] تفعيل 5 مقاييس سياقية خلال 72 ساعة.
- [ ] تشغيل Chaos Context Suite قبل أي نشر كبير.

---

## 15) الخلاصة التي يجب أن تعتمدها الإدارة الهندسية

هذه الحادثة ليست bug صغيرًا، ولا prompt tweak.  
هذه **قضية موثوقية سياق** (Context Reliability) في نظام موزع.  
من دون تحويلها إلى discipline رسمي (Contracts + Telemetry + Chaos + Gates)، ستتكرر بأشكال مختلفة مهما تغير النموذج أو الصياغة.

**القرار الصحيح:** اعتبر عمى السياق SRE-grade reliability domain، لا issue عابرة.

