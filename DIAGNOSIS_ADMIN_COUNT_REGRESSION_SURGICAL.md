# تشريح جراحي للخلل: لماذا أصبح الأدمن يحصل على إجابة عامة بدل العدّ الدقيق؟

## 1) الملخص التنفيذي (Executive Autopsy)

**الخلاصة القاطعة:** المشكلة ليست في "قدرة النموذج" فقط، بل في **انكسار مسار التنفيذ الحتمي** عبر حدود المايكروسيرفس (Routing + Intent + Tool Registration + Endpoint Drift). النتيجة: سؤال إداري مثل "كم عدد ملفات بايثون؟" قد لا يصل أصلاً إلى أداة العدّ الفعلية، أو يصل لمسار لا يملك سياق الأدمن، أو يصل لمسار يملك الأدوات نظريًا لكن السجل غير مُحمَّل وقت التنفيذ.

بالتالي يعود النظام إلى إجابة لغوية عامة (Reasoning/Tree-of-Thought style) بدل تنفيذ shell/tool حقيقي.

---

## 2) الدليل الجنائي من الشيفرة (Evidence)

### A) انقسام مسارات التنفيذ (Dual Control Plane)

يوجد مساران مختلفان فعليًا للدردشة:

1. **مسار StateGraph الحديث** عبر WebSocket `/admin/api/chat/ws` و `/api/chat/ws` الذي ينفذ `create_unified_graph()` مباشرة.
2. **مسار `/agent/chat`** الذي يقرر إن كان الطلب "admin" بناءً على `context.chat_scope` فقط تقريبًا.

عند هذا الانقسام، أي عميل/واجهة يضرب المسار القديم أو يرسل Context غير مكتمل سيذهب لمسار مختلف سلوكيًا.

### B) شرط الأدمن في `/agent/chat` هش

في نقطة `/agent/chat`، التحويل إلى `admin_app` مشروط بـ:
- `context.get("chat_scope") == "admin"`
- أو `request.context.get("chat_scope") == "admin"`

**لا يوجد اشتقاق صريح من صلاحيات JWT هنا**. إذا لم يُمرَّر `chat_scope=admin` في الـ payload، يتم التعامل مع السؤال الإداري كدردشة عامة.

### C) فجوة تسجيل أدوات الأدمن في مسار StateGraph

عقدة تنفيذ أدوات الأدمن في graph (`ExecuteToolNode`) تعتمد على `get_registry().get(tool_name)`. لكن مسار `/api/chat/messages` وWS الذي يستدعي `create_unified_graph()` لا يستدعي بوضوح `register_all_tools()` قبل التشغيل.

النتيجة المتوقعة في بعض الظروف التشغيلية:
- `tool_fn` غير موجود
- رجوع حالة خطأ داخل `final_response`
- أو fallback لسلوك عام في طبقة أعلى/واجهة

### D) احتمال Canary Routing إلى conversation-service

البوابة (API Gateway) فيها توجيه canary لمسارات WS نحو `conversation-service` بناءً على `ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT`.

إذا تم رفع النسبة في البيئة الفعلية، قد تتحول جلسة admin WS إلى conversation-service (stub/parity) بدل orchestrator-service الحقيقي، فتفقد تنفيذ الأدوات الإدارية الدقيقة.

### E) تضاعف منطق النية Intent عبر طبقات متعددة

هناك أكثر من مكان لكشف Intent (monolith + microservice + graph patterns + emergency guards). هذا يخلق **Behavior Drift**: نفس السؤال قد يصنَّف ADMIN في طبقة، وDEFAULT في أخرى، حسب المسار الذي وصل له.

---

## 3) لماذا كان المونوليث "يعد بدقة" ثم تراجع الآن؟

في النسخة المونوليثية، المسار كان أقصر:
- نية السؤال + أدوات shell كانت غالبًا في نفس السياق التنفيذي.

بعد التحول لـ microservices:
- زاد عدد نقاط الفشل (Gateway/Service Boundary/Context Contract/Registry Lifecycle).
- أي انقطاع بسيط في contract أو bootstrap يجعل النظام يرجع لإجابة لغوية عامة.

**التحول المعماري ليس المشكلة بحد ذاته**؛ المشكلة هي عدم إحكام "الخط الإداري الحتمي" End-to-End كقناة واحدة صلبة.

---

## 4) التشخيص الجذري (Ranked Root Causes)

1. **Root Cause #1 (أعلى احتمال):** Endpoint/Context Drift — الطلبات الإدارية لا تحمل دومًا `chat_scope=admin` إلى `/agent/chat`، فتسقط لمسار عام.
2. **Root Cause #2:** Registry Lifecycle Gap — أدوات الأدمن ليست مضمونة التسجيل قبل تنفيذ graph في كل نقاط الدخول.
3. **Root Cause #3:** Canary Misroute Risk — نسبة rollout قد تحول admin WS إلى خدمة محادثة parity غير مهيأة للأدوات الإدارية.
4. **Root Cause #4:** Intent Logic Duplication — تعدد كواشف النية يسبب عدم اتساق classification بين المسارات.

---

## 5) بصمات العطل المطابقة لصورتك

النمط الظاهر في الصورة (إجابة إنشائية عامة مع Tree-of-Thought بدل رقم فعلي) يتطابق مع أحد السيناريوهين غالبًا:

- **Scenario A:** السؤال لم يدخل قناة admin execution أصلًا (misroute/misclassification/context missing).
- **Scenario B:** دخل القناة لكن لم يجد أداة جاهزة/مسجلة فعاد fallback نصّي.

---

## 6) خطة التحقق التشخيصي (بدون تعديل شيفرة)

1. تتبع route_id الفعلي لكل جلسة WS (`chat_ws_admin` vs `chat_ws_customer`) من لوج gateway.
2. تأكيد target النهائي: `orchestrator-service` أم `conversation-service`.
3. عند كل سؤال من نوع "count python files":
   - log intent (قبل/بعد classifier)
   - log resolved_tool
   - log registry contains tool?
   - log tool_invoked=true/false
4. مطابقة payload الداخل `/agent/chat` والتأكد هل يحمل `chat_scope=admin`.

---

## 7) الحكم النهائي

العطل الحالي هو **عطل تكاملي معماري** (Integration Regression) وليس عطلًا معرفيًا في LLM.

بصياغة دقيقة:
> "القناة الإدارية الحتمية لم تعد قناة واحدة مغلقة هندسيًا من الواجهة حتى الأداة؛ بل أصبحت عرضة للتشعب بين مسارات متعددة، وبعضها ينتهي بإجابة لغوية عامة بدل تنفيذ قياس فعلي."

هذا يفسر لماذا كان النظام سابقًا "دقيقًا خارقًا" عند العدّ (عندما كان مسار التنفيذ موحدًا وقريبًا من shell)، ولماذا أصبح الآن أحيانًا "عامًا" بعد التفكيك الميكروسيرفسي.
