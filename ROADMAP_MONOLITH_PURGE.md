# 🗺️ ROADMAP_MONOLITH_PURGE: الاستئصال النهائي لنظام المونوليث القديم للدردشة (The Ultimate Purge)

**الوثيقة الاستراتيجية لمعمارية التخلص 100% من النظام القديم (API-First Microservices Decommissioning)**

تُمثل هذه الوثيقة الخارطة الهندسية الدقيقة، والمُصممة بأسلوب الجراحة التقنية العميقة (Surgical Precision Engineering)، لاقتلاع بقايا النظام القديم (Monolith) المتمثل في الاعتمادية الهجينة للـ WebSockets في الدردشة، وذلك دون التسبب في ثانية واحدة من انقطاع الخدمة (Zero Downtime).

---

## 🎯 التشخيص الدقيق للمشكلة المعمارية (The Split-Brain Pathology)

المشكلة الحالية تكمن في أن واجهة المستخدم الأمامية تعتمد على "واجهات توافق" (Compatibility Facades) موجودة في النظام القديم، وتحديداً في الملفين:
1. `app/api/routers/customer_chat.py`
2. `app/api/routers/admin.py`

بينما المحرك الحقيقي للذكاء الاصطناعي موجود الآن في `microservices/orchestrator_service`. تقوم بوابة `microservices/api_gateway/main.py` بتوجيه الـ WebSockets إلى النظام القديم، الذي يقوم بدوره بإعادة توجيهها (Proxy) عبر `orchestrator_client` إلى الخدمة المصغرة. هذا يولد مسار بيانات معقد (Gateway -> Monolith -> Microservice) ويهدد بحدوث "انقسام في الدماغ" (Split-Brain) عند إدارة الجلسات.

---

## 🔬 المرحلة التحضيرية (Phase 0): المراقبة العميقة وبناء خط الدفاع الأول

**الهدف:** إخضاع كل حزمة بيانات قادمة عبر الـ WebSocket للمراقبة الشاملة قبل أي تدخل جراحي.

1. **حقن أجهزة المراقبة (Telemetry Injection):**
   - في ملف `microservices/api_gateway/main.py`، التأكد من أن دوال `chat_ws_proxy` و `admin_chat_ws_proxy` تحقن وسماً واضحاً (Tag) `legacy_routing=true` في الـ Tracing (W3C `traceparent`) لكل طلب يتجه نحو `CORE_KERNEL_URL`.
   - **الناتج المتوقع:** لوحة تحكم (Dashboard) دقيقة ترصد نسبة حركة المرور القديمة وحجم البيانات المتبادلة.

2. **تجميد مسارات المونوليث (Registry Lockdown):**
   - تثبيت ملف `config/routes_registry.json` ومنع أي تعديل مستقبلي يُضيف نقاط وصول (Endpoints) جديدة نحو النظام القديم عبر إجراءات إجبارية في أنظمة التكامل المستمر (CI Pipelines).

---

## 🏗️ المرحلة الأولى (Phase 1): بناء البديل وتوحيد العقود (Shadow Engineering & Parity)

**الهدف:** إنشاء نقطة استقبال الـ WebSockets داخل الخدمات المصغرة لتكون متطابقة سلوكياً (Behavioral Parity) بنسبة 100% مع النظام القديم.

1. **توحيد شكل الرسائل (Payload Standardization):**
   - تحليل الدالة `normalize_streaming_event` الموجودة في `app/services/chat/event_protocol.py`.
   - نقل هذه الدالة وبناء منطق مطابق لها بالكامل داخل نقطة وصول الخدمة المصغرة الجديدة في `microservices/orchestrator_service/api/routers/chat.py` أو `microservices/conversation_service`.
   - **الشرط الحرج:** يجب أن يكون مُخرج الخدمة المصغرة مطابقاً تماماً لمُخرج المونوليث لكي لا تنهار واجهة Next.js.

2. **اختبار التوجيه الشبحي (Shadow Routing Test - اختياري):**
   - تطوير مسار وهمي (Shadow Route) في البوابة `microservices/api_gateway` يستقبل الطلب، يُمرره للنظام القديم ليُعالج فعلياً، لكنه ينسخ الطلب في الخلفية للخدمة المصغرة لمقارنة الردود (Diffing) للتأكد من التطابق قبل التوجيه الحقيقي.

---

## 🔀 المرحلة الثانية (Phase 2): التحويل الجراحي الموجه (The Controlled Cutover)

**الهدف:** نقل شريان الحياة (Traffic) ببطء شديد من المونوليث إلى الخدمة المصغرة باستخدام تقنية الخنق التدريجي (Strangler Fig Pattern).

1. **تفعيل صمام التوجيه في البوابة (Gateway Routing Valve):**
   - الاعتماد على متغير البيئة `ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT` المُعرّف في إعدادات بوابة الـ API.
   - تعديل دالة `_resolve_chat_ws_target` في `microservices/api_gateway/main.py` لتبدأ فعلياً بتوجيه النسبة المحددة نحو خدمة `CONVERSATION_SERVICE_URL` بدلاً من المونوليث.

2. **الجدول الزمني للتحويل (Rollout Schedule):**
   - **اليوم 1:** تحويل 1% من المستخدمين (للفرق الداخلية والمراقبة).
   - **اليوم 3:** زيادة النسبة إلى 10% بعد التأكد من عدم وجود أخطاء في الـ Logs (تحديداً أخطاء 500 أو انقطاع في الـ WebSocket).
   - **اليوم 7:** زيادة النسبة إلى 50%.
   - **اليوم 10:** التحويل الشامل بنسبة 100%.

3. **القدرة الفائقة على التراجع السريع (Instant Rollback):**
   - في حالة حدوث أي انهيار (Frontend Crash)، يتم إعادة `ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT` إلى القيمة `0` فوراً. ستقوم البوابة بإعادة توجيه كل شيء للمونوليث في أجزاء من الثانية.

---

## ☠️ المرحلة الثالثة (Phase 3): الاستئصال النهائي والتطهير المعماري (The Ultimate Purge)

**الهدف:** بعد نجاح التحويل وثبات نسبة المونوليث عند 0% لمدة 14 يوماً، تبدأ عملية الحذف النهائي والعميق.

1. **إعدام الواجهات التوافقية (Execution of Compatibility Facades):**
   - الحذف المادي للملفين بالكامل:
     - `rm app/api/routers/customer_chat.py`
     - `rm app/api/routers/admin.py`
   - إزالة أي استيراد (Imports) لهذين الملفين من `app/main.py` أو `app/api/router.py`.

2. **تطهير بوابة الـ API (Gateway Cleanup):**
   - تنظيف ملف `microservices/api_gateway/main.py` من أي منطق يخص الرجوع للمونوليث (Fallback Logic).
   - إزالة روابط توجيه الـ WebSockets القديمة (`legacy_acl.websocket_target`).

3. **تفكيك البنية التحتية (Infrastructure Decommissioning):**
   - إيقاف حاوية `core-kernel` نهائياً من ملفات `docker-compose.yml` الافتراضية للإنتاج.
   - إغلاق قاعدة بيانات `postgres-core` بعد التأكد من تفريغها من أي بيانات حرجة.

---

## 👑 مؤشرات النصر الاستراتيجي (Success Metrics)

تُعتبر هذه الخارطة مكتملة والمهمة منجزة عند تحقيق المؤشرات التالية:
1. **استهلاك المونوليث = 0%**: لا يوجد أي طلب (Request) واحد يصل إلى `core-kernel` لمدة أسبوعين متتاليين.
2. **ارتباط واجهة المستخدم = 100% Microservices**: جميع اتصال الـ WebSockets من الـ Frontend يمر مباشرة عبر الـ Gateway إلى `orchestrator-service` أو `conversation-service`.
3. **أكواد نظيفة**: حذف ملفات `app/api/routers/customer_chat.py` و `app/api/routers/admin.py` بنجاح واجتياز جميع اختبارات (CI Pipeline).

> **"النظام العظيم لا يُبنى بإضافة الكود، بل بشجاعة حذفه عندما ينتهي دوره."**