# التقرير الجنائي الفاخر: كارثة فشل استرجاع التمارين في منظومة الوكلاء المتعددين

## 1) الملخص التنفيذي (Executive Verdict)

هذا الخلل **ليس خلل محتوى** (التمرين موجود في قاعدة البيانات/المشروع/الإنترنت)، بل هو خلل **تشغيلي-معماري شبكي** في سلسلة التوجيه بين:

`Frontend -> WebSocket/API Gateway/Kernel -> orchestrator-service -> أدوات الاسترجاع`

النتيجة: النظام يسقط قبل الوصول لمحرك الاسترجاع نفسه، ثم يعرض للمستخدم خطأ اتصال خام.

---

## 2) الدليل القطعي من الرسالة الظاهرة

رسالة الواجهة المعروضة تتضمن محاولات على ثلاث وجهات:

- `http://localhost:8006/agent/chat`
- `http://orchestrator-service:8006/agent/chat`
- `http://host.docker.internal:8006/agent/chat`

وفشل DNS/اتصال (`All connection attempts failed`, `Name or service not known`) يعني أن الكارثة تقع في **طبقة Service Discovery / Networking** قبل أي reasoning فعلي.

---

## 3) الثغرات الخطيرة (Critical Findings)

## F-01 — Default URL قاتل داخل الإعدادات الأساسية (Root Misrouting)
**الخطورة:** حرج (Critical)  
**الأثر:** انهيار شامل لاستدعاءات `orchestrator-service` عند أي تشغيل خارج السيناريو المتوقع.

- في إعدادات النواة/الـKernel، افتراضي `ORCHESTRATOR_SERVICE_URL` يُحل إلى `localhost` بدل اسم الخدمة الداخلية، ما يخلق انحرافًا عن بيئة microservices الفعلية عندما لا يكون التنفيذ محليًا بنفس الحاوية.
- هذا يفسر ظهور محاولة `localhost:8006` ضمن التشخيص النهائي.

**لماذا هذا خطير جدًا؟**
لأنه يحوّل مسار الخدمة من Service-to-Service إلى Localhost ambiguity، فتنهار الاستدعاءات بين الحاويات/العقد.

---

## F-02 — تضارب إعدادات البوابة API Gateway مع الواقع الشبكي
**الخطورة:** حرج (Critical)  
**الأثر:** فشل WS/HTTP routing على مسارات الدردشة.

- `api_gateway` يملك افتراضي `ORCHESTRATOR_SERVICE_URL = http://localhost:8006`، وهو افتراضي خطر داخل نمط Docker/K8s إذا لم تتم إعادة ضبطه بوضوح.
- عند بناء هدف WebSocket، البوابة تحول HTTP إلى WS آليًا؛ أي خطأ في الأصل ينعكس مباشرة في قناة البث الحية.

**لماذا هذا خطير جدًا؟**
لأن أي deployment drift بسيط يُسقط قناة الوكلاء كاملة، بينما الواجهة تبدو “متصلة” شكليًا.

---

## F-03 — تسريب معلومات بنية داخلية للمستخدم النهائي (Internal Topology Disclosure)
**الخطورة:** عالٍ (High)  
**الأثر:** كشف hostnames داخلية + منافذ + سلوك retry للمهاجم/المستخدم.

- عميل orchestrator يرسل للمستخدم نص تشخيص يتضمن تفاصيل endpoints الداخلية وفشل DNS.
- هذه المعلومات حساسة تشغيليًا (Operational Intelligence Leak) وتُستخدم في الاستطلاع (Recon).

**لماذا هذا خطير؟**
لأن الخطأ التحليلي الداخلي يجب أن يذهب للسجلات فقط، لا للـUI.

---

## F-04 — نقطة فشل أحادية (SPOF) لمسار CONTENT_RETRIEVAL
**الخطورة:** حرج (Critical)  
**الأثر:** أي اضطراب في orchestrator يقتل كامل سيناريو "أعطني تمرين".

- منسق الدردشة يوجه `CONTENT_RETRIEVAL` مباشرة إلى microservice الخارجي.
- لا يوجد degraded-mode حقيقي لمحتوى التمارين، فقط fallback خاص جدًا بعدّ ملفات Python.

**لماذا هذا خطير؟**
لأن graceful degradation غير متوازن: fallback موجود لأداة إدارية ضيقة، وغير موجود لسيناريو المستخدم الأساسي.

---

## F-05 — Surface هجوم إداري مكشوف بدون اعتماد ظاهر على الحماية
**الخطورة:** حرج (Critical)  
**الأثر:** إمكانية استدعاء أدوات إدارية مباشرة إذا لم توجد حماية على مستوى شبكة/Ingress.

- مسارات أدوات الإدارة (`/api/v1/tools/{tool}/invoke`) تُعرّف مباشرة في router ولا يظهر عليها `Depends` أمني صريح في نفس المسار.
- في بيئات misconfigured exposure، هذا يفتح أدوات حساسة للنداء المباشر.

**لماذا هذا خطير؟**
لأنه يخالف Zero Trust: المسار الإداري يجب أن يكون مقيّدًا بالتوثيق والتفويض داخل endpoint نفسه، لا افتراض حماية خارجية فقط.

---

## F-06 — مفاتيح/قيم أمنية افتراضية خطيرة (Hardcoded Weak Defaults)
**الخطورة:** عالٍ (High)  
**الأثر:** خطر اختراق بيئات غير منضبطة وخصوصًا staging المنسوخ من التطوير.

- وجود `SECRET_KEY` افتراضي صريح في إعدادات API Gateway.
- وجود إعدادات permissive واسعة (`allow_methods=['*']`, `allow_headers=['*']`) مع احتمالات CORS/host misgovernance إذا لم تُضبط بيئيًا بدقة.

**لماذا هذا خطير؟**
لأن الثقة على “سنغيره لاحقًا” سبب كلاسيكي للحوادث الإنتاجية.

---

## F-07 — عدم اتساق مسار التشغيل (Bypass/Drift بين Gateway وKernel)
**الخطورة:** عالٍ (High)  
**الأثر:** سلوك غير حتمي: أحيانًا عبر Gateway وأحيانًا via direct kernel bridge.

- المشروع يحوي أكثر من مسار للوصول لنفس intent (WS proxy + direct orchestrator client).
- عند أي divergence في ENV بين المسارات، قد ينجح chat عادي ويفشل mission/content أو العكس.

**لماذا هذا خطير؟**
لأنه يدمّر قابلية التشخيص ويخلق “نجاح كاذب” في اختبارات smoke.

---

## 4) لماذا يظهر الفشل مع "التمرين" أكثر من الطلبات الأخرى؟

- الطلبات التعليمية (`CONTENT_RETRIEVAL`) تمر بخط تفويض إلزامي إلى orchestrator.
- الطلبات الأخرى قد تملك fallback محلي أو تمر بمسارات أقل اعتمادًا على نفس hop.
- لهذا يعتقد المستخدم أن "التمرين غير موجود" بينما الحقيقة أن **خط النقل مكسور** قبل الاسترجاع.

---

## 5) التشخيص البنيوي النهائي (Root Cause Statement)

**الجذر الحقيقي:**
1. انحراف إعداد `ORCHESTRATOR_SERVICE_URL` بين البيئات (localhost vs service DNS).  
2. تعدد نقاط التوجيه (Gateway + Kernel bridge) بدون مصدر حقيقة واحد صارم.  
3. غياب degraded retrieval mode لمهام العميل الأساسية.  
4. تسريب التشخيص الداخلي مباشرة لواجهة المستخدم.

**إذن:** الفشل **تشغيلي-شبكي-حوكمي** وليس معرفيًا/بيانيًا.

---

## 6) خريطة المخاطر (Risk Matrix)

- Availability: **حرج جدًا** (انقطاع الخدمة الوظيفية الأساسية للمستخدم).
- Security: **عالٍ** (تسريب topology + مسارات إدارية حساسة).
- Reliability: **حرج** (سلوك غير حتمي بسبب تعدد المسارات).
- Operability: **حرج** (Mean Time To Recovery مرتفع بسبب Drift).

---

## 7) دلائل الكود المؤيدة للتشخيص (Evidence Pointers)

- إعدادات URL الافتراضية ومسار resolver:
  - `app/core/settings/base.py`
- منطق fallback ومحاولات endpoint وتسريب diagnostic للواجهة:
  - `app/infrastructure/clients/orchestrator_client.py`
- إعدادات API Gateway الافتراضية وتوجيه WS:
  - `microservices/api_gateway/config.py`
  - `microservices/api_gateway/main.py`
- تعريف مسارات أدوات الإدارة في orchestrator:
  - `microservices/orchestrator_service/src/api/routes.py`

---

## 8) الحكم التنفيذي النهائي

المنظومة الحالية **لا تفشل لأن التمرين مفقود**؛ بل تفشل لأن طبقة النقل بين خدمات المنظومة ليست محكومة بمصدر إعداد موحد وآمن مع fallback وظيفي عادل للعميل.  
وبالتالي، الكارثة هي **Architecture & Runtime Governance Failure** ضمن منظومة API-first microservices متعددة الوكلاء.
