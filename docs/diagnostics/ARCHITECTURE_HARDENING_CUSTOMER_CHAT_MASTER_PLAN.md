# الخطة المعمارية الجذرية الفاخرة: توحيد مسار المحادثة إلى Orchestrator واحد (100% API-First)

## الملخص التنفيذي

هذه الوثيقة تقدم خارطة طريق تنفيذية لمدة أسبوع لتحويل نظام الدردشة من حالة الانقسام التشغيلي (Split-Brain) إلى حالة المصدر الواحد للقرار (Single Brain)، بحيث تصبح:

- **دردشة العميل والأدمن مبنية على نفس المحرك orchestration**.
- **الـ API Gateway بوابة عبور فقط (Ingress)** دون منطق أعمال.
- **عقد WebSocket/Event موحد وثابت** لكل المسارات.
- **نتيجة نهائية:** تدفق دردشة العميل يصبح مستقرًا، قابلًا للرصد، وقابلًا للتوسع دون مفاجآت إنتاجية.

---

## 1) تعريف المشكلة الحقيقية (Root Cause الحقيقي)

المشكلة ليست في واجهة المستخدم فقط، بل في **ازدواج ملكية المنطق**:

1. جزء من المسارات يعتمد محليًا على مكوّنات داخلية.
2. جزء آخر يعتمد على orchestrator-service عن بعد.
3. عند اختلاف بيئة التشغيل (Legacy/Modern) تتبدل نقطة القرار فينتج سلوك غير متناظر:
   - سيناريو يعمل للأدمن.
   - نفس السيناريو الدلالي يفشل للعميل.

### الأثر المباشر

- تفاوت في تجربة المستخدم حسب الدور.
- صعوبة تتبع الأعطال عبر خدمات متعددة.
- زيادة احتمال الانقطاعات الصامتة (Connected UI + Failed backend hop).

---

## 2) الهدف المعماري النهائي (Target State)

### المبدأ الحاكم

**Orchestrator هو المالك الوحيد لمنطق chat/mission orchestration.**

### توزيع المسؤوليات النهائي

- **Gateway (Ingress Only):**
  - Authentication عند الحافة.
  - Rate limiting.
  - Routing/Proxy.
  - Trace propagation.
  - بدون أي business logic للمحادثة.

- **Orchestrator (Single Brain):**
  - Intent routing.
  - Graph state execution.
  - Mission lifecycle.
  - Streaming الأحداث للواجهة.

- **Conversation Projection Service (أو module مستقل):**
  - read-models للمحادثات والملخصات.
  - عدم امتلاك قرار orchestration.

- **User Service:**
  - هوية وصلاحيات فقط.

---

## 3) العقد الموحد للأحداث (Unified WS/Event Contract)

> الهدف: أي عميل Frontend يستهلك نفس schema بغض النظر عن الدور أو نوع المهمة.

## 3.1 Envelope قياسي (إجباري)

```json
{
  "type": "assistant_delta",
  "trace_id": "uuid",
  "conversation_id": "string|number",
  "run_id": "string",
  "timestamp": "ISO-8601",
  "payload": {}
}
```

## 3.2 أنواع الأحداث القياسية

1. `conversation_init`
2. `assistant_delta`
3. `assistant_final`
4. `RUN_STARTED`
5. `PHASE_STARTED`
6. `PHASE_COMPLETED`
7. `assistant_error`
8. `complete`

## 3.3 قواعد صارمة

- لا يوجد payload مخصص لكل route.
- `assistant_error` يجب أن يكون مفهومًا للمستخدم وآمنًا (بدون تسريب أسرار).
- أي stream يجب أن ينتهي بـ `complete` حتى في حالات الفشل.
- event ordering يلتزم: init -> progress/delta -> final|error -> complete.

---

## 4) خطة تنفيذ أسبوعية (Architecture Hardening Sprint - 7 Days)

## اليوم 1: Contract-First Design

**المخرجات:**
- وثيقة رسمية لـ WS/Event schema (v1).
- جداول payload لكل event.
- سياسة backward compatibility.

**معيار القبول:**
- الموافقة المشتركة Backend/Frontend/QA على عقد واحد فقط.

## اليوم 2: Gateway Slimming

**المهام:**
- إزالة أي decision logic متعلق بالدردشة من الـ Gateway.
- حصر دوره في المصادقة، التوجيه، والحماية.

**معيار القبول:**
- gateway لا ينتج أي chat payload business-level، فقط يمرر ويؤمن.

## اليوم 3: Orchestrator Consolidation

**المهام:**
- نقل/تثبيت كل chat + mission routing داخل orchestrator.
- إيقاف أي fallback مساري محلي خارج orchestrator في المسار الحي.

**معيار القبول:**
- أي طلب chat/mission يصل في النهاية لنفس brain.

## اليوم 4: State Ownership Cleanup

**المهام:**
- تعريف واضح لملكية state:
  - execution state داخل orchestrator.
  - conversation projections كقراءات منفصلة.
- منع تداخل الكتابة بين خدمات متعددة على نفس الحقيقة المنطقية.

**معيار القبول:**
- لا تضارب ملكية، ولا ازدواج مصدر حقيقة.

## اليوم 5: Frontend Contract Unification

**المهام:**
- reducer/hook واحد للتعامل مع كل الأحداث القياسية.
- إزالة branching حسب route/role داخل parser.

**معيار القبول:**
- نفس الكود الأمامي يدعم الأدمن والعميل بدون تفريعات خاصة.

## اليوم 6: Reliability Hardening

**المهام:**
- Circuit breaker بين gateway وorchestrator.
- Retry policy محسوب + jitter.
- Timeouts معيارية + idempotency key لطلبات البدء.
- Correlation/trace IDs عبر كل hop.

**معيار القبول:**
- الفشل الجزئي لا يكسر واجهة الدردشة، بل يظهر assistant_error + complete.

## اليوم 7: Verification & Go-Live Gate

**المهام:**
- مصفوفة E2E: (admin/customer) × (chat/mission) × (success/failure).
- اختبارات contract تلقائية.
- مراقبة KPI/SLO قبل الإطلاق وبعده.

**معيار القبول:**
- 0 فروقات عقد بين المسارات.
- نجاح دردشة العميل بنسبة مستقرة ضمن SLO.

---

## 5) تعريف النجاح التشغيلي (Definition of Done)

يُعتبر المشروع ناجحًا عندما تتحقق الشروط التالية جميعًا:

1. لا يوجد منطق orchestration حي خارج orchestrator.
2. gateway لا يملك business logic للمحادثة.
3. العقد الموحد للأحداث مستخدم في جميع المسارات.
4. جميع حالات الفشل تتحول لأحداث معيارية مفهومة.
5. تتبع كامل لكل طلب عبر `trace_id` من البداية للنهاية.
6. سيناريوهات العميل والأدمن تمر بنفس السلسلة التنفيذية مع اختلاف السياسات فقط.

---

## 6) لماذا هذه الخطة تجعل دردشة العميل "خارقة" فعليًا؟

لأنها تعالج **سبب العطل البنيوي** وليس العرض:

- توحيد brain يلغي التناقض بين الأدوار.
- العقد الموحد يلغي هشاشة التكامل Frontend/Backend.
- فصل المسؤوليات يرفع الاعتمادية وقابلية التطور.
- الرصد والتتبع يجعلان أي خلل قابلًا للتشخيص الفوري.

النتيجة العملية:

- استقرار أعلى.
- زمن استجابة أكثر توقعًا.
- تقليل جذري لأخطاء "متصل لكن لا يرد".
- قدرة توسع مؤسسي دون إعادة كتابة الواجهة في كل مرة.

---

## 7) Runbook تشغيلي مختصر بعد التنفيذ

1. تحقق صحة Gateway ingress (auth, routing, tracing).
2. تحقق health orchestrator + dependencies.
3. نفّذ smoke test لعقد الأحداث عبر WS.
4. راقب KPIs:
   - WS connect success rate.
   - First-token latency.
   - assistant_error rate.
   - complete-emission consistency.
5. فعّل rollback آلي إن تجاوزت الأخطاء عتبة الخطر.

---

## 8) KPI/SLO مقترحة للإنتاج

- `ws_connect_success_rate >= 99.9%`
- `assistant_error_rate <= 1.0%`
- `missing_complete_event_rate = 0%`
- `p95_first_token_latency <= 1.8s`
- `customer_chat_success_ratio >= 99.5%`

---

## 9) خارطة المخاطر والتخفيف

- **مخاطر:** كسر التوافق مع عملاء قدامى.
  - **تخفيف:** Versioned contract + grace window.

- **مخاطر:** ضغط زائد على orchestrator بعد التوحيد.
  - **تخفيف:** autoscaling + queue buffering + circuit breakers.

- **مخاطر:** ضبابية المراقبة عبر الخدمات.
  - **تخفيف:** tracing إلزامي + dashboards موحدة + alerting.

---

## 10) خاتمة تنفيذية

هذه الطريقة ليست تحسينًا موضعيًا؛ إنها **إعادة ضبط معمارية** لتحويل النظام إلى 100% API-First Microservices كما ينبغي:

- Brain واحد.
- Contract واحد.
- Ownership واضح.
- Operational excellence قابلة للقياس.

وعند تطبيقها بانضباط خلال أسبوع، ستكون النتيجة المنطقية: **دردشة العميل تعمل بثبات عالي، بجودة إنتاجية فاخرة، وبمسار قابل للتوسع بلا مفاجآت.**
