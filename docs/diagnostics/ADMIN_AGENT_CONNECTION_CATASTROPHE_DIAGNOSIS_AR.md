# التشخيص الخارق: لماذا يظهر للأدمن خطأ `Error connecting to agent: All connection attempts failed`

## ملخص تنفيذي سريع
هذه ليست مشكلة واجهة فقط، بل **سلسلة فشل متعددة الطبقات** تبدأ من توجيه نية الأدمن إلى مسار الميكروسيرفس، ثم فشل اتصال HTTP بالخدمة الوسيطة (Orchestrator)، ثم تسريب الخطأ كنص JSON خام إلى واجهة الأدمن.

النتيجة التي تظهر في الصورة (`assistant_error` + `All connection attempts failed`) هي **عرض نهائي** لفشل الاتصال الشبكي بين Backend وOrchestrator، وليست سببًا بحد ذاتها.

---

## 1) لماذا يحدث هذا غالبًا للأدمن تحديدًا؟

### مسار الأدمن يختلف عن المستخدم العادي
- عند كون المستخدم Admin، يتم توجيه الدردشة عبر `AdminChatBoundaryService` ثم `AdminChatStreamer` ثم `ChatOrchestrator`.
- `ChatRoleDispatcher` يفصل المسارات حسب الدور: الأدمن لمسار Admin، والعميل لمسار Customer.

### سؤال مثل: "كم عدد ملفات بايثون في المشروع"
هذا السؤال يطابق نية `ADMIN_QUERY` (بسبب وجود كلمات مثل `ملفات بايثون` في أنماط النية).

### ماذا يحدث بعد التطابق؟
- `ChatOrchestrator` يعتبر `ADMIN_QUERY` من النوايا التي يجب تفويضها إلى Orchestrator Microservice.
- لذلك يتم استدعاء `orchestrator_client.chat_with_agent(...)` بدل المسار المحلي.

**الخلاصة:** الأدمن يدخل تلقائيًا في مسار يعتمد على خدمة خارجية إضافية (Orchestrator)، لذا يتأثر مباشرة إذا هذه الخدمة غير متاحة.

---

## 2) نقطة الفشل الأساسية (Root Trigger)

داخل `orchestrator_client.chat_with_agent`:
- يتم إرسال طلب إلى:
  - `POST {ORCHESTRATOR_SERVICE_URL}/agent/chat`
- يوجد Retry ثلاث مرات فقط على أخطاء الاتصال (`ConnectError/Timeout`).
- إذا فشل الاتصال بالكامل، يتم التقاط الاستثناء ثم إرسال حدث خطأ.

الرسالة `All connection attempts failed` تأتي عادة من طبقة HTTP (httpx/httpcore) عندما:
1. الخدمة غير شغالة أصلًا.
2. DNS/hostname غير قابل للحل من بيئة الـ backend.
3. المنفذ غير مفتوح أو مغلق بجدار/شبكة.
4. `ORCHESTRATOR_SERVICE_URL` غير صحيح في البيئة الفعلية.

---

## 3) سبب إضافي يجعل الشكل "كارثي" في الواجهة

حتى بعد فشل الاتصال، يوجد خلل تغليف للخطأ:
- في فرع الاستثناء داخل `orchestrator_client.chat_with_agent`، يتم عمل `yield json.dumps({...assistant_error...})` كنص، وليس dict.
- هذا النص يمر لاحقًا عبر `AdminChatStreamer`، فيتعامل معه كـ string عادي ويحوّله إلى حدث `delta`.
- النتيجة: واجهة المستخدم تعرض JSON الخام كنص داخل الرسالة، بدل التعامل معه كحدث خطأ منظّم.

**إذن لدينا مشكلتان متتاليتان:**
1. فشل اتصال حقيقي مع الخدمة.
2. تشويه شكل رسالة الخطأ عند النقل للواجهة.

---

## 4) تحليل معماري لاحتمالات السبب (مرتبة بالأرجحية)

### A) الأعلى احتمالًا: الخدمة الهدف غير متاحة Runtime
- Orchestrator service down/crashed/restarting.
- Health endpoint لا يستجيب أو يستجيب ببطء شديد.

### B) `ORCHESTRATOR_SERVICE_URL` غير متوافق مع سياق التشغيل
- في docker-compose قد يكون صحيحًا (`http://orchestrator-service:8006`).
- لكن خارج compose أو في نشر جزئي، قد يصبح hostname غير قابل للوصول.
- أي فرق بين `.env` المتوقعة وبيئة العملية الفعلية يخلق نفس الأعراض.

### C) Network Segmentation / Proxy / Firewall
- backend لا يستطيع الوصول داخليًا إلى الشبكة التي يعيش فيها orchestrator.
- أو proxy/Nginx يمنع route الداخلي.

### D) مهلة/زمن استجابة أعلى من الحدود
- timeout قد يسبق readiness الكامل للخدمة.

---

## 5) لماذا الرسالة تظهر فور طلب "إداري" تحديدًا؟

لأن Trigger intent هو نفسه الذي ينقل التنفيذ لمسار الميكروسيرفس:
- `ADMIN_QUERY`, `ANALYTICS_REPORT`, `LEARNING_SUMMARY`, `CURRICULUM_PLAN`, `CONTENT_RETRIEVAL`
- هذه المجموعة لا تُنفَّذ محليًا في نفس الطبقة مثل دردشة عادية، بل تُفوَّض خارجيًا.

لذلك أي سؤال "إداري/تحليلي" يصطدم مباشرة بعنق الزجاجة الشبكي.

---

## 6) مسار تدفق الفشل (Failure Chain)

1. الأدمن يرسل سؤالًا إداريًا.
2. Intent Detector يصنفه `ADMIN_QUERY`.
3. ChatOrchestrator يفوضه إلى `orchestrator_client.chat_with_agent`.
4. client يحاول الاتصال 3 مرات بـ `/agent/chat`.
5. جميع المحاولات تفشل -> `All connection attempts failed`.
6. الخطأ يُعاد كنص JSON (`json.dumps`) بدل dict.
7. Admin streamer يعامله كقطعة نص (delta).
8. الواجهة تعرض JSON الخام داخل الرسالة.

---

## 7) تشخيص جراحي بدون تعديل كود (Runbook تحقق ميداني)

نفّذ من نفس بيئة الـ backend (نفس الحاوية/الـpod):

1. اطبع القيمة الفعلية:
   - `echo $ORCHESTRATOR_SERVICE_URL`
2. تحقق DNS:
   - `getent hosts orchestrator-service` (إن كان hostname داخلي)
3. تحقق health:
   - `curl -sv "$ORCHESTRATOR_SERVICE_URL/health"`
4. تحقق endpoint المستخدم فعليًا:
   - `curl -sv -X POST "$ORCHESTRATOR_SERVICE_URL/agent/chat" -H 'Content-Type: application/json' -d '{"question":"ping","user_id":1}'`
5. راقب backend logs وقت الطلب الإداري:
   - ابحث عن `Failed to chat with agent`.
6. راقب orchestrator logs بنفس timestamp:
   - هل وصل الطلب أصلًا أم لا؟

**قراءة النتائج:**
- إذا health يفشل: المشكلة بنية/شبكة/خدمة.
- إذا health ينجح و`/agent/chat` يفشل: المشكلة في endpoint نفسه (routing/auth/payload).
- إذا الطلب لا يصل للخدمة: المشكلة DNS/network/policy.

---

## الحكم النهائي (Forensic Verdict)

**السبب الجذري المرجّح جدًا:**
فشل اتصال backend بخدمة Orchestrator على المسار الإداري المفوّض (`/agent/chat`)، لذلك تظهر `All connection attempts failed`.

**السبب الذي يجعل المشهد يبدو "كارثة بصرية":**
الخطأ يتم تسليمه كسلسلة JSON خام ثم يُعرض كنص عادي في واجهة الأدمن.

بكلمة واحدة: **Root Cause = Connectivity**, و**Blast Radius = Error Serialization/Presentation**.
