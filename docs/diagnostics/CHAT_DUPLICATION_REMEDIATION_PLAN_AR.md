# خطة علاج ازدواجية مسارات الدردشة بدون كسر الميزات (NAAS-Agentic-Core)

## 1) خارطة أدلة الازدواجية (Evidence Map)

### أ. ازدواجية WebSocket للدردشة بين المونوليث وخدمة Orchestrator
- المونوليث يعرّف قناة الإدارة: `/admin/api/chat/ws` داخل `app/api/routers/admin.py`.
- المونوليث يعرّف قناة العملاء: `/chat/ws` داخل `app/api/routers/customer_chat.py`.
- خدمة `orchestrator_service` تعرّف قنوات مماثلة (`/api/chat/ws` و`/admin/api/chat/ws`) داخل `microservices/orchestrator_service/src/api/routes.py`.
- النتيجة: خطر **Split-Brain** عند تشغيل قناتين فعالتين في آن واحد مع منطق توجيه مختلف.

### ب. ازدواجية منطق التنسيق (Orchestration Logic)
- `app/services/chat/orchestrator.py` ما زال يحتوي منطق تنسيق فعلي (Intent Detection + Strategy Handlers + Caching) مع تفويض جزئي إلى `orchestrator_client`.
- في الوقت نفسه، توجد طبقة تنسيق كاملة داخل `microservices/orchestrator_service/src/services/overmind`.
- النتيجة: انجراف سلوكي (Behavior Drift) بين تنفيذ محلي وتنفيذ خدمة مستقلة.

### ج. ازدواجية عقد بث الأحداث (delta مقابل assistant_delta)
- العقد الموحّد `ChatEventEnvelope` موجود في `app/contracts/chat_events.py`.
- طبقة التطبيع `normalize_streaming_event` في `app/services/chat/event_protocol.py` تتيح التوافق الخلفي عبر Feature Flag `CHAT_USE_UNIFIED_EVENT_ENVELOPE`.
- بعض الواجهات الأمامية ما زالت تستهلك `delta` تاريخياً.
- النتيجة: ازدواجية انتقالية مقبولة مؤقتاً، لكنها تحتاج خطة إزالة تدريجية مبنية على قياسات parity.

### د. ازدواجية عدّ ملفات بايثون (مقبولة انتقالياً)
- نية عدّ الملفات مرصودة في المونوليث (`app/services/chat/intent_detector.py`, `app/services/chat/intent_registry.py`).
- يوجد تنفيذ واضح للأداة في الخدمة المصغرة `microservices/orchestrator_service/src/contracts/admin_tools.py` (`admin.count_python_files`).
- التصنيف: **ازدواجية انتقالية مقبولة** فقط كمسار fallback حتى ثبات قناة orchestrator.

### هـ. ازدواجية استرجاع التمارين التعليمية
- المونوليث يستدعي الاسترجاع مباشرة عبر `app/services/overmind/domain/cognitive.py`.
- توجد كذلك خدمة بحث/استرجاع مستقلة في `microservices/research_agent/`.
- النتيجة: مخاطر فقدان التناسق بين ACL المحلي ومخرجات خدمة البحث الفعلية.

---

## 2) تحليل الأثر الجذري لكل ازدواجية

1. **سبب جذري:** انتقال مرحلي بدون Strangler boundaries صارمة.
   - **الأثر:** split-brain في التوجيه والبث، وصعوبة تفسير الأعطال.

2. **سبب جذري:** بقاء منطق تنسيق داخل المونوليث بدل الاكتفاء بـ BFF/ACL.
   - **الأثر:** drift في القرارات، واختلاف النتيجة لنفس السؤال حسب المسار.

3. **سبب جذري:** عقد أحداث غير موحّدة بالكامل على الواجهة.
   - **الأثر:** احتمال event loss دلالي (العميل يتجاهل نوعاً لا يعرفه).

4. **سبب جذري:** عدم اكتمال Database-per-Service + Outbox.
   - **الأثر:** تضارب كتابة/قراءة وتتبّع ضعيف لمصدر الحقيقة.

---

## 3) خطة إصلاح تدريجية بدون كسر

## المرحلة A: تثبيت العقود والحماية (بدون تغيير سلوك المستخدم)
1. إبقاء المسارات الحالية كما هي (`/api/security/login`, `/admin/users/count`, `/v1/content/search`) كواجهات توافق.
2. فرض اختبارات عقود للمسارات الحرجة + حراسة عدم حجب event loop لعمليات DSPy.
3. اعتماد `ChatEventEnvelope` كعقد قياسي داخلي، مع استمرار التحويل التوافقي عبر الراية.

## المرحلة B: Strangler + ACL للدردشة
1. جعل المونوليث BFF فقط لمسارات الدردشة (مصادقة/تفويض/ترجمة عقد).
2. تحويل التنسيق التنفيذي تدريجياً إلى `orchestrator_service` عبر Feature Flag.
3. سياسة Canary: `1% -> 5% -> 25% -> 50% -> 100%` مع قياس parity قبل كل ترقية.

## المرحلة C: حماية البيانات (Database per Service)
1. منع أي كتابة مزدوجة لجداول المحادثة.
2. اعتماد Outbox/CDC للأحداث العابرة للخدمات.
3. منع القراءة العابرة لقواعد بيانات خدمات أخرى مباشرة.

## المرحلة D: إغلاق الازدواجية الضارة
1. إزالة مسارات التنسيق المحلية بعد اكتمال parity.
2. الإبقاء فقط على fallback تشغيلي قصير الأمد تحت راية رجوع (Kill Switch).

---

## 4) الاختبارات والضمانات المطلوبة

1. **Consumer-Driven Contracts**
   - تحقق ثبات واجهات: `/api/security/login`, `/admin/users/count`, `/v1/content/search`.
2. **Streaming Contract Tests**
   - تحقق توافق أحداث `delta` التاريخية مع `assistant_delta` الموحّد تحت Feature Flag.
3. **Non-Blocking Tests**
   - تحقق أن مسارات DSPy الثقيلة تعمل عبر `asyncio.to_thread` لتفادي تجميد event loop.
4. **Parity & Shadow Validation**
   - تنفيذ مزدوج (قديم/جديد) بصمت ومقارنة النتيجة قبل التحويل النهائي.

---

## 5) المتابعة وقياس النجاح (KPIs)

- نسبة التوجيه عبر المسار الجديد لكل Endpoint.
- Error Budget لكل مرحلة Canary.
- Event Contract Mismatch Rate.
- متوسط زمن الاستجابة p95 لمسارات الدردشة.
- معدل rollback لكل نشر.
- مدة الاستعادة MTTR عند فشل orchestrator.

> قاعدة الإزالة النهائية: لا حذف لأي مسار قديم قبل تحقيق parity متواصل مع window مراقبة كافٍ.


## 6) تنفيذ المرحلة التالية (Phase B - Canary Wiring)

- تمت إضافة أداة قرار حتمية للتوجيه التدريجي داخل المونوليث: `app/services/chat/orchestration_rollout.py`.
- التوجيه يعتمد على متغير البيئة `CHAT_ORCHESTRATOR_CANARY_PERCENT` (من 0 إلى 100):
  - `0`: إبقاء نوايا الوكلاء على المسار المحلي (Legacy).
  - `100`: تفويض كامل إلى `orchestrator_service`.
  - قيمة وسطية: Canary حتمي حسب `user_id`.
- تم ربط القرار فعليًا داخل `ChatOrchestrator.process` بحيث يصبح التحويل قابلًا للإرجاع فورًا بدون كسر الواجهات.
- تمت إضافة اختبارات وحدة لتثبيت سلوك canary والتحقق من الحتمية.
