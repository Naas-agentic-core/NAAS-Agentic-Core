# التشخيص الجنائي العميق لظاهرة «عمى السياق»
## CogniForge / Overmind — إصدار تشخيصي فائق الدقة (L4 Forensic)

> هذا التقرير **تشخيص جذري هندسي** (Root-Cause Forensics) وليس توصيات سطحية.  
> الهدف: تفكيك الانهيار السياقي كمشكلة نظام معقّد (Complex System Failure)، عبر طبقات: الواجهة، النقل اللحظي، هوية المحادثة، إدارة التاريخ، منطق الإحالة اللغوية، وحوكمة التشغيل.

---

## 0) تعريف الكارثة بدقة (Problem Framing)

الحالة المرصودة: المستخدم يسأل سؤالًا مرجعيًا قصيرًا مثل «ما هي عاصمتها؟» بعد سؤال سابق يحدد الكيان (مثل «أين تقع الجزائر؟»)، فيُعامل السؤال وكأنه مستقل ويُطلب توضيح جديد.

هذه ليست "هفوة LLM" فقط. هذه **فجوة استمرارية سياق** ناتجة عن:

1. هشاشة ربط الهوية (`conversation_id`, `thread_id`) عبر الزمن.
2. تعدد قنوات سلوك عميل غير متطابقة (modern/legacy).
3. انكماش سياق متعدد المراحل قبل وصوله للنموذج.
4. fallback صامت يحول فشل السياق إلى إجابة طبيعية ظاهريًا.
5. غياب مؤشرات تشغيل متخصصة لاكتشاف الانهيار قبل أن يراه المستخدم.

---

## 1) حدود التشخيص ومنهجه (Scope & Method)

### 1.1 الطبقات التي شملها الفحص

- **Client Composition Layer**: بناء الرسالة والسياق في `useAgentSocket`.
- **Legacy Client Path**: مسار `legacy-app` وسلوك socket لكل رسالة.
- **Transport Contract Layer**: WebSocket event envelope / request gating.
- **Conversation Lifecycle Layer**: `_ensure_conversation` وتحميل التاريخ.
- **Context Hydration Layer**: merge بين DB history و client context.
- **Graph Input Layer**: بناء history الفعلي قبل دخول الرسم البياني.
- **Linguistic Reference Layer**: استخراج anchor وإعادة كتابة الأسئلة الإحالية.

### 1.2 المنهج التحليلي

- **Failure-Mode Decomposition**: تحويل المشكلة إلى أنماط فشل (FM-01..FM-12).
- **Causal Chain Mapping**: الربط السببي من كل طبقة إلى الأثر المرئي.
- **Barrier Analysis**: ما الحاجز المفترض؟ ولماذا لم يمنع الفشل؟
- **Control Gap Analysis**: ما الذي يجب قياسه ولم يُقَس؟

---

## 2) نموذج النظام: أين يُفترض أن يعيش السياق؟

السياق في هذا النظام ليس كيانًا واحدًا. بل أربع نسخ متزامنة:

1. **Client Ephemeral Context**: رسائل موجودة في state الواجهة.
2. **Persisted Context**: تاريخ محفوظ بقاعدة البيانات لكل conversation.
3. **Hydrated Context**: ناتج دمج (DB + client_context_messages).
4. **Model-Effective Context**: النافذة النهائية بعد القص/التطبيع قبل LLM.

**نقطة العطب المركزية:** النظام لا يضمن invariants صارمة تضمن تطابق النسخ الأربع، وبالتالي قد يعمل النموذج على نسخة مختلفة عما يتوقعه المستخدم.

---

## 3) التشخيص السببي العميق (Deep Causal Diagnosis)

## FM-01 — فقد/عدم استقرار هوية المحادثة (Identity Drift)

### الوصف
استمرارية السياق تعتمد أولًا على استمرارية `conversation_id`. أي تعثر في حمل هذا المعرف عبر الطلبات يؤدي لسلسلة جديدة أو hydration ناقص.

### كيف يحدث
- client يرسل `conversation_id` بشرط وجوده في state.
- عند سباق أحداث أو تبديل قناة أو إعادة اتصال غير متزامنة، قد تُرسل رسالة follow-up قبل تثبيت الهوية.

### الأثر
- history يُحمّل من محادثة خاطئة أو لا يُحمّل.
- الأسئلة الإحالية تصبح غامضة رغم أنها طبيعية للمستخدم.

### لماذا خطير
هو فشل "هوية" وليس فشل "فهم لغوي"؛ أي يتكرر بأي نموذج ذكاء مهما كان قويًا.

---

## FM-02 — تعدد مسارات العميل بخصائص متعارضة (Behavioral Split-Brain)

### الوصف
وجود مسارين عميل (حديث + legacy) مع سلوك socket مختلف جوهريًا.

### النتيجة
النظام يملك "شخصيتين" في الإنتاج:
- شخصية تتعامل بجلسة مستمرة.
- شخصية تفتح/تغلق socket لكل سؤال.

### الأثر
تباين reproducibility: الخطأ يظهر في بعض البيئات/الأجهزة أكثر من غيرها دون سبب ظاهر للفريق.

---

## FM-03 — شلال القص السياقي (Truncation Cascade)

### الوصف
السياق يُقص مرارًا عبر طبقات مختلفة بحدود مستقلة:
- client slice.
- extraction cap.
- merge cap.
- graph history cap.
- digest compression.

### النتيجة
المستخدم يرى "محادثة طويلة" بينما النموذج يرى "مقتطفًا مبتورًا".

### الأثر
فقدان الكيان المرجعي الأقدم ولو كان ما زال واضحًا بصريًا في واجهة المستخدم.

---

## FM-04 — fallback صامت (Silent Degradation)

### الوصف
عند غياب checkpointer/history، المسار لا يفشل Failure-Explicit بل يتابع كـ cold start.

### النتيجة
- استجابة تبدو صحيحة نحويًا لكن خاطئة سياقيًا.
- صعوبة اكتشاف الحادث تشغيليًا لأن الـ status غالبًا "نجاح".

### الأثر
تحويل "خطأ نظام" إلى "ارتباك مستخدم".

---

## FM-05 — منطق الإحالة heuristic غير محصّن بمستوى كافٍ

### الوصف
هناك منطق جيد لتعزيز السؤال الإحالي، لكنه يعتمد على توفر history مناسب ويستخدم token heuristics.

### النتيجة
في حالة history ناقص/مشوه، augment لا ينقذ السؤال.

### الأثر
الضحية هي exactly النوع الأكثر حساسية: short follow-up pronoun queries.

---

## FM-06 — ازدواج منطق hydration بين مسارات متوازية (Drift-Prone Duplication)

### الوصف
وجود شيفرة hydration منسوخة بين orchestrator وcompatibility façade.

### النتيجة
أي تعديل جزئي في مسار دون الآخر يخلق semantic drift صامت.

### الأثر
سلوك غير متطابق بين endpoints تبدو متشابهة للمستخدم.

---

## FM-07 — الحماية ضد الـrace غير مكتملة عند "الأسئلة السريعة"

### الوصف
العميل يملك gating للأحداث، لكنه لا يفرض precondition صارم يمنع follow-up قبل إقرار conversation identity بشكل نهائي.

### الأثر
نافذة سباق صغيرة لكن مؤذية جدًا، خاصة مع الشبكات المتقطعة/الموبايل.

---

## FM-08 — عدم وجود "عقدة مرساة سياقية" مستقلة (Anchor Memory Primitive)

### الوصف
الكيان المرجعي الأحدث لا يُخزن ككيان تشغيلي مستقل resilient، بل يُستنتج من history الخام.

### الأثر
حين يُقص history أو يتشوه، يضيع anchor بالكامل بدل أن يبقى كـ state بسيط (آخر كيان موضوعي مؤكد).

---

## FM-09 — عدم وجود SLOs متخصصة للسياق

### الوصف
لا توجد مؤشرات تشغيلية تقيس "سلامة السياق" مباشرة.

### أمثلة مؤشرات مفقودة
- FollowupWithoutAnchorRate
- ColdStartOnActiveConversationRate
- ConversationIdMissingOnFollowupRate
- ContextWindowDropRatio
- AmbiguousQuestionRecoveredRate

### الأثر
فريق التشغيل يرى الألم من التذاكر، لا من اللوحات المبكرة.

---

## FM-10 — غياب تصنيف رسمي للحالات السياقية الحرجة (Context Severity Taxonomy)

### الوصف
لا توجد مستويات Severity قياسية لحوادث السياق (P1/P2/P3) مرتبطة بخطوات احتواء تلقائي.

### الأثر
الاستجابة للحوادث تصبح ad-hoc وتختلف باختلاف الشخص المناوب.

---

## FM-11 — لا يوجد اختبار Chaos مركّز على إعادة الاتصال والسياق

### الوصف
اختبارات happy-path موجودة، لكن لا يوجد سيناريو منهجي يحاكي:
- reconnect أثناء stream،
- رسالة follow-up فورية بعد init،
- message burst مع jitter.

### الأثر
المشكلات تظهر في الإنتاج أولًا.

---

## FM-12 — تضارب الإدراك بين UX وModel Reality

### الوصف
المستخدم يرى سجلًا طويلًا في الواجهة، فيفترض أن النموذج يراه كاملًا.

### الأثر
حين يطلب النموذج توضيحًا، يتولد شعور "انهيار كارثي" لأن توقع المستخدم منطقي من منظور الواجهة.

---

## 4) السبب الجذري الأعلى (Root Cause of Root Causes)

**السبب الأعلى ليس "فقد رسالة"؛ بل غياب "عقد سياق موحد وقابل للتحقق" (Verifiable Context Contract).**

أي أن النظام يفتقد invariant تشغيلي على شكل:

- نفس `conversation_id` مثبت.
- نفس `thread_id` مثبت.
- وجود anchor صالح عند follow-up الإحالي.
- سبب صريح إذا لم يتحقق أي شرط (بدل استمرار صامت).

بدون هذا العقد، كل طبقة تجتهد محليًا، وتنتج فجوات تراكمية.

---

## 5) تحليل شجرة الإخفاق (Failure Tree)

### Top Event
**Ambiguous Follow-up Mis-handled (AFM)**

### Branch A: Identity Path
A1. conversation_id missing/invalid  
A2. sticky conversation not applied  
A3. reconnect race resets local assumptions

### Branch B: Hydration Path
B1. DB history short due limits  
B2. client context absent or sliced  
B3. merge outputs context where anchor dropped

### Branch C: Graph Input Path
C1. effective window too short  
C2. checkpointer unavailable  
C3. fallback to cold-start message-only

### Branch D: Linguistic Recovery Path
D1. ambiguous followup detected  
D2. anchor extraction fails  
D3. no explicit recovery protocol emitted

إذا تحقق أي مسار من A/B/C + D2/D3 ⇒ **AFM**.

---

## 6) مصفوفة المخاطر (Risk Matrix)

| الخطر | الاحتمال | الأثر | مستوى الخطر |
|------|----------|------|-------------|
| فقد conversation identity | متوسط-عالٍ | عالٍ | حرج |
| تعدد client paths | عالٍ | متوسط-عالٍ | عالٍ جدًا |
| truncation cascade | عالٍ | عالٍ | حرج |
| silent fallback | متوسط | عالٍ | عالٍ |
| heuristic anchor limits | متوسط | متوسط | متوسط-عالٍ |
| hydration drift بين المسارات | متوسط | عالٍ | عالٍ |
| غياب SLO سياقي | عالٍ | عالٍ | حرج |

---

## 7) خطة احتواء فوري (Containment — 72 ساعة)

## C1 — منع الانهيار الصامت
- عند سؤال إحالي + لا anchor: أرسل `context_missing` event صريح.
- امنع تمرير السؤال للنموذج مباشرة قبل محاولة استرجاع مرساة.

## C2 — تشديد عقد الهوية
- follow-up بدون conversation_id بعد init = protocol error واضح.
- فرض إعادة مزامنة identity بدل إنشاء محادثة جديدة تلقائيًا.

## C3 — قفل مسار legacy في الإنتاج
- feature flag إجباري لتعطيل legacy path تدريجيًا.

## C4 — مقاييس طوارئ
- dashboards عاجلة: MissingConversationId, ColdStartFollowup, AnchorRecoveryFailed.

---

## 8) إعادة تصميم متوسطة المدى (Stabilization — 2 إلى 4 أسابيع)

## S1 — Context Contract v2
إضافة حقول إلزامية لكل رسالة follow-up:
- `conversation_id`
- `thread_id`
- `turn_index`
- `context_checksum`

## S2 — Anchor Memory Primitive
تخزين آخر كيان مؤكد لكل conversation كحالة صغيرة مستقلة، تحدث عند كل turn، وتستخدم قبل heuristic extraction.

## S3 — Relevance-Aware Windowing
استبدال الحدود الثابتة بسياسة اختيار مرجحة (recency + entity relevance + unresolved refs).

## S4 — Contract Tests ضد drift
اختبارات تطابق سلوك hydration بين orchestrator وcompatibility façades.

## S5 — Chaos Context Suite
مجموعة اختبارات تحاكي jitter/reconnect/out-of-order/rapid follow-up.

---

## 9) خارطة إصلاح استراتيجية (Hardening — 1 إلى 2 ربع سنوي)

1. **توحيد قناة عميل وحيدة** production-grade.
2. **Context Service مركزي** بدل منطق سياق موزع داخل handlers.
3. **Event Sourcing خفيف للسياق** لتتبع لماذا ومن أين ضاع anchor.
4. **SLO رسمي للسياق** ضمن reliability objectives للمنصة.
5. **Postmortem template سياقي** إلزامي لكل حادث follow-up failure.

---

## 10) مؤشرات قبول النجاح (Definition of Done)

- انخفاض `FollowupWithoutAnchorRate` بنسبة ≥ 80%.
- `ColdStartOnFollowupRate` أقل من 1%.
- تطابق نتائج hydration عبر المسارات = 100% في contract tests.
- عدم ظهور طلبات توضيح غير لازمة في سيناريوهات pronoun follow-up القياسية.
- وجود إنذار آلي خلال < 5 دقائق عند تجاوز عتبة الانهيار السياقي.

---

## 11) خلاصة تنفيذية حاسمة

المشكلة **ليست سطحية** وليست "ذكاء اصطناعي نسي"؛ إنها عطب معماري تشغيلي متعدد الطبقات.  
بالتالي الحل الحقيقي هو:

- Contract صارم للهوية والسياق،
- مسار عميل موحد،
- إدارة نافذة سياق قائمة على الصلة،
- fallback صريح بدل الصمت،
- مراقبة Reliability مخصصة للسياق.

**من دون ذلك، ستتكرر الكارثة حتى لو تم تبديل النموذج.**

---

## 12) ملاحق تنفيذية سريعة

### A) قائمة قرارات لا تقبل التأجيل
- [ ] منع follow-up بلا conversation identity.
- [ ] تفعيل `context_missing` event.
- [ ] تعطيل legacy path في بيئات الإنتاج الحساسة.
- [ ] إطلاق 3 لوحات مراقبة سياقية خلال 72 ساعة.

### B) قائمة فحوص قبل كل release
- [ ] test: rapid follow-up after init.
- [ ] test: reconnect during stream + follow-up.
- [ ] test: mixed Arabic pronoun references.
- [ ] test: long conversation with forced truncation.

### C) كتالوج حوادث يجب التقاطه تلقائيًا
- ContextDropIncident
- IdentityMismatchIncident
- AnchorRecoveryFailureIncident
- SilentColdStartIncident

