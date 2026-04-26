# التشخيص الجراحي لعمى السياق في الدردشة (2026-04-26)

## السؤال الجنائي
هل «المونوليث» ما يزال يتحكم في سياق الإجابات؟ ولماذا تبدو المحادثة وكأنها تبدأ من الصفر؟

## الحكم التنفيذي المختصر
نعم، المونوليث ما يزال على مسار التنفيذ (Compatibility Facade) ويقوم بإدارة دورة حياة المحادثة محليًا قبل التفويض إلى orchestrator. هذا يخلق «سلطتين سياقيتين» (Local + Orchestrator) ويزيد احتمالات عمى السياق.

لكن السبب الأكثر مباشرة لبدء الدردشة من الصفر عند المستخدم النهائي ليس المونوليث وحده، بل سلسلة تبدأ من الواجهة:
1. `conversationId` يُحفظ في React state فقط.
2. عند التحميل/إعادة الفتح لا يوجد استرجاع إلزامي لآخر `conversationId`.
3. عند الإرسال بدون `conversation_id`، الخادم ينشئ محادثة جديدة.

## سلسلة المسؤولية الدقيقة (Root Cause Chain)

### 1) المونوليث ما يزال «بوابة تحكم» وليست مجرد Proxy
- ملف: `app/api/routers/customer_chat.py`
- الدليل:
  - تفعيل نمط الواجهة التوافقية `COMPATIBILITY_FACADE_MODE = True`.
  - إنشاء/التحقق من محادثة محلية وحفظ رسالة المستخدم محليًا.
  - تمرير `history_messages` و `conversation_id` إلى orchestrator عبر `orchestrator_client.chat_with_agent(...)`.

**الأثر:** السياق يمر عبر طبقتين تحفظان الحالة، وهذا يفتح باب عدم التطابق بين معرف المحادثة المحلي وسياق orchestrator.

### 2) نقطة القطع القاتلة: عدم وجود `conversation_id` في الطلب
- ملف: `frontend/app/hooks/useAgentSocket.js`
- الدليل:
  - `sendMessage` يضيف `payload.conversation_id` فقط إذا كانت قيمة `conversationId` غير `null/undefined`.

**الأثر:** أي فقدان لحالة `conversationId` في الواجهة يعني أن الطلب يُرسل بلا معرف محادثة.

### 3) سبب فقدان `conversationId` في الواجهة
- ملف: `frontend/app/components/CogniForgeApp.jsx`
- الدليل:
  - `conversationId` يعيش داخل hook/state فقط.
  - لا يوجد استدعاء إجباري في النسخة الحالية لاسترجاع آخر محادثة عند mount (على عكس legacy behavior المعروف تاريخيًا).
  - `handleNewChat` يمسح `conversationId` صراحةً (`setConversationId(null)`) ويمسح الرسائل.

**الأثر:** بعد reload أو بعد New Chat، أول رسالة غالبًا تنطلق بلا `conversation_id`.

### 4) السلوك النهائي عند الخادم عندما يغيب `conversation_id`
- ملف: `microservices/orchestrator_service/src/api/routes.py`
- الدليل:
  - `_ensure_conversation(...)` إذا استقبل `requested_conversation_id = None` ينشئ محادثة جديدة (`_create_new_conversation`).

**الأثر:** يُنظر للرسالة كجلسة جديدة => انطباع «كل مرة من الصفر».

## المتهم الأساسي «بدقة جراحية»
**Primary Owner (الأكثر تأثيرًا):**
- `frontend/app/components/CogniForgeApp.jsx` + `frontend/app/hooks/useAgentSocket.js`
- لماذا؟ لأنهما يقرران استمرار/فقدان `conversationId` قبل وصول الطلب للخادم.

**Secondary Owner (معماريًا):**
- `app/api/routers/customer_chat.py`
- لماذا؟ لأنه يبقي المونوليث في مسار السياق كمنسّق فعلي (وليس قناة عبور صافية)، ما يفاقم احتمالات الانقسام السياقي.

**Enforcement Point (تنفيذي):**
- `microservices/orchestrator_service/src/api/routes.py::_ensure_conversation`
- لماذا؟ لأنه الجهة التي تُحوّل «غياب المعرف» إلى «محادثة جديدة» فعليًا.

## توصية تصحيحية سريعة
1. فرض استرجاع `latest conversation` عند mount وتثبيت `conversationId` قبل أول إرسال.
2. إضافة guard يمنع `sendMessage` بدون `conversationId` في وضع «استئناف محادثة».
3. تقليل دور المونوليث في إدارة الحالة ونقل السلطة كاملة لمسار orchestrator + conversation service.
4. إضافة telemetry إلزامية: نسبة الطلبات المرسلة بدون `conversation_id` لكل نسخة Frontend.
