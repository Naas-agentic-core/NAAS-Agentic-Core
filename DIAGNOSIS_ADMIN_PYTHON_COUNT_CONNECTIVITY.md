# تشريح تشخيصي جراحي — خلل عدّ ملفات بايثون لدى الأدمن بعد التحوّل إلى Microservices

## 1) الملخص التنفيذي

المشكلة الظاهرة في الواجهة (`Error connecting to agent: All connection attempts failed`) **ليست فشلاً في أداة العد نفسها**، بل هي فشل في طبقة الربط الشبكي بين نواة النظام (Monolith/Kernel) وخدمة `orchestrator-service` قبل الوصول أصلًا إلى أداة العد.

بمعنى أدق: طلب الأدمن يمر عبر WebSocket، ثم يتم تفويضه إلى `orchestrator_client.chat_with_agent`، وعند تعذّر الاتصال بعنوان خدمة الـ Orchestrator يحدث `httpx.ConnectError`، فتقوم طبقة العميل بإرجاع الحدث `assistant_error` بنفس الرسالة التي ظهرت لك في الصورة.

---

## 2) الدليل القاطع من مسار التنفيذ (Execution Path)

### A) الواجهة الأمامية تعرض رسالة `assistant_error` كما هي
- في `useAgentSocket`، عند استقبال نوع الحدث `assistant_error` يتم عرضه حرفيًا كـ `Error: <content>`.

### B) مصدر نص الخطأ نفسه
- في `app/infrastructure/clients/orchestrator_client.py`، أي استثناء أثناء `chat_with_agent` يتم تحويله إلى:
  - `type = assistant_error`
  - `payload.content = "Error connecting to agent: {e}"`

### C) سبب الاستدعاء أصلًا من قناة الأدمن
- في `app/api/routers/admin.py`، قناة الأدمن WebSocket تستدعي `ChatOrchestrator.dispatch`.
- في `app/services/chat/orchestrator.py`، نية `ADMIN_QUERY` تُفوَّض مباشرة إلى `orchestrator_client.chat_with_agent` (microservice delegation).

### D) ماذا يحدث داخل خدمة Orchestrator عندما تكون متاحة؟
- في `microservices/orchestrator_service/src/services/overmind/agents/orchestrator.py`، نية `ADMIN_QUERY` تُوجَّه إلى `admin_agent`.
- وداخل `microservices/orchestrator_service/src/services/overmind/agents/admin.py`، أداة `count_python_files` تستخدم أمر shell مباشر (`find . -name '*.py' | wc -l`)؛ أي أن منطق العد موجود فعلًا.

**الاستنتاج الجراحي:** الانهيار يحدث **قبل** تنفيذ أداة العد، تحديدًا عند جسر الاتصال إلى `orchestrator-service`.

---

## 3) لماذا كان يعمل سابقًا في النظام المونوليث؟

في وضع المونوليث القديم، العد غالبًا كان محليًا في نفس العملية/السياق (نفس الحاوية أو نفس runtime)، دون قفزة شبكية لخدمة خارجية.

بعد التحول إلى Microservices، أصبح نفس الطلب يحتاج:
1. WebSocket → Kernel
2. Kernel → Orchestrator Service عبر HTTP stream
3. Orchestrator → AdminAgent Tool

أي خلل في الخطوة (2) يكفي لإظهار فشل كامل رغم أن أداة العد نفسها سليمة.

---

## 4) الأسباب الجذرية المحتملة مرتبة بالأولوية

## السبب الجذري رقم 1 (الأرجح):
**DNS/Service Discovery غير متاح من البيئة التي يعمل فيها الـ Kernel**

- العنوان الافتراضي في العميل: `http://orchestrator-service:8006`.
- هذا الاسم ينجح فقط داخل شبكة Docker/Compose الداخلية.
- إذا كانت عملية الـ Kernel تعمل خارج الشبكة الداخلية (أو عبر نشر هجين)، فلن يتم حل الاسم، فتظهر `All connection attempts failed`.

### دليل تشغيلي مباشر من البيئة الحالية
- أمر `getent hosts orchestrator-service` أعاد لا شيء (لا يوجد حل DNS).
- أمر `getent hosts research-agent` كذلك أعاد لا شيء.

هذا يدل أن الاعتماد على أسماء الخدمات الداخلية دون شبكة مشتركة سيؤدي لفشل الاتصال.

---

## السبب الجذري رقم 2:
**Drift في إعدادات المنافذ/العناوين بين الخدمات**

توجد مؤشرات على عدم اتساق عبر المكوّنات:
- `research-agent` يعمل على 8007 في `docker-compose`.
- بعض القيم الافتراضية في بعض العملاء تشير تاريخيًا إلى 8000.

حتى لو لم يكن هذا هو سبب خطأ الأدمن الحالي مباشرة، فهو عرض قوي على وجود "Config Drift" قد يظهر بأشكال مشابهة لاحقًا.

---

## السبب الجذري رقم 3:
**الاعتماد الإجباري (Hard dependency) دون مسار تدهور (Graceful Degradation) في استعلامات الأدمن**

حاليًا الأدمن لا يملك fallback محلي عند تعطل `orchestrator-service`، لذلك أي انقطاع شبكة يتحول فورًا إلى خطأ ظاهر للمستخدم النهائي بدل تقديم بديل جزئي.

---

## 5) تحليل مطابق لصورتك وسلوكك الموصوف

- سؤالك كان بسيطًا: "كم عدد ملفات بايثون في المشروع".
- هذا من نوايا `ADMIN_QUERY`.
- الواجهة عرضت خطأ اتصال وكيل (`Error connecting to agent...`) وليس خطأ "فشل تنفيذ أداة العد".

إذن المشكلة متوافقة 100% مع **انقطاع جسر التفويض إلى orchestrator-service**، وليست مشكلة منطق العد نفسه.

---

## 6) خطة تشخيص ميداني دقيقة (بدون تعديل شيفرة)

1. تأكيد URL الفعلي في Runtime للـ Kernel:
   - قيمة `ORCHESTRATOR_SERVICE_URL` الفعلية أثناء التشغيل.
2. تأكيد أن العملية التي تخدم `/admin/api/chat/ws` ترى نفس الشبكة التي فيها `orchestrator-service`.
3. اختبار صحي من نفس Runtime:
   - `curl -v $ORCHESTRATOR_SERVICE_URL/health`
4. فحص سجلات kernel عند الخطأ:
   - وجود `Failed to chat with agent` من `orchestrator-client`.
5. فحص سجل orchestrator:
   - هل وصل الطلب أصلًا لـ `/agent/chat` أم لا.
6. فحص reverse proxy / ingress:
   - هل يمنع الخروج إلى hostnames الداخلية أو يعيد توجيه خاطئ.

---

## 7) الحكم النهائي (Verdict)

**الخلل الحالي هو خلل ربط شبكي/اكتشاف خدمة في طبقة Microservice delegation، وليس خللًا في أداة shell التي تعد ملفات بايثون.**

السبب الأكثر احتمالًا: البيئة التي ينفذ فيها Kernel لا تستطيع الوصول أو حل اسم `orchestrator-service` كما هو متوقع داخل Docker network، فتنتهي المكالمة بـ `All connection attempts failed`، ثم تُعرض الرسالة حرفيًا في واجهة الأدمن.

---

## 8) أثر معماري مستقبلي (API-First / Multi-Agent / LangGraph / MCP)

هذا الحادث يبيّن أن انتقال النظام إلى بنية Microservices المتقدمة (StateGraph + Multi-Agent + API-first) يتطلب ضبطًا صارمًا لثلاث طبقات:

1. **Service Discovery Contract** (من يرى من؟ بأي اسم؟)
2. **Runtime Topology Contract** (داخل نفس شبكة Docker أم نشر هجين؟)
3. **Resilience Contract** (circuit-breaker + fallback + user-safe error mapping)

بدون هذه العقود التشغيلية، الأنظمة الذكية المتقدمة (LangGraph/LlamaIndex/DSPy/Reranker/Kagent/MCP/TLM) ستتأثر من أبسط نقطة: فشل النقل بين عقدتين.

---

## 9) ملحق الأدلة (Evidence Index)

- مصدر نص الخطأ المرسل للواجهة: `app/infrastructure/clients/orchestrator_client.py`
- مسار تفويض الأدمن إلى microservice: `app/services/chat/orchestrator.py`
- نقطة WebSocket الأدمن: `app/api/routers/admin.py`
- راوتر `/agent/chat` في orchestrator-service: `microservices/orchestrator_service/src/api/routes.py`
- توجيه `ADMIN_QUERY` إلى `admin_agent`: `microservices/orchestrator_service/src/services/overmind/agents/orchestrator.py`
- تنفيذ shell لعد ملفات بايثون: `microservices/orchestrator_service/src/services/overmind/agents/admin.py`
- مؤشرات إعدادات URLs والمنافذ: `app/core/settings/base.py`, `microservices/orchestrator_service/src/core/config.py`, `docker-compose.yml`
