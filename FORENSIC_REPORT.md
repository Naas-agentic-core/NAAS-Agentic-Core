# تقرير التحليل الجذري: فشل اتصال الزبون ونجاح المسؤول في قنوات WebSocket

## 1. الملخص التنفيذي الجذري (BLUF - Bottom Line Up Front)
سبب الفشل هو **تطبيق سياسة أمنية تمنع تمرير التوكن عبر `Query String` في بيئات الإنتاج (Production/Staging)**، مقترنًا بـ **استخدام واجهة الزبون لبروتوكول قديم (`?token=...`)** بينما تستخدم واجهة الأدمن بروتوكول `sec-websocket-protocol` المعتمد لتمرير التوكن بشكل آمن.

## 2. تحليل مسار التنفيذ (Execution Flow Analysis)
يبدأ مسار الاتصال عند طلب العميل إنشاء جلسة `WebSocket` عبر `API Gateway`. يتم توجيه الطلب إلى الخدمات الخلفية (`Orchestrator` أو `Legacy Monolith`) وهناك يتم التحقق من الصلاحيات.

**نقطة الانحراف (Divergence Point):**
1. **مسار الأدمن (النجاح):**
   - تقوم واجهة الأدمن بتمرير التوكن باستخدام مصفوفة البروتوكولات الفرعية: `new WebSocket(url, ['jwt', token])`.
   - تستقبل دالة `extract_websocket_auth` في الخادم الطلب، وتقرأ التوكن بنجاح من ترويسة `sec-websocket-protocol`.
   - يكتمل الاتصال بنجاح.

2. **مسار الزبون (الفشل):**
   - تقوم واجهة الزبون بتمرير التوكن كمعامل استعلام (Query Parameter): `new WebSocket(url + "?token=" + token)`.
   - في دالة `extract_websocket_auth`، تفشل محاولة قراءة التوكن من `sec-websocket-protocol`.
   - تنتقل الدالة إلى مسار التوافقية (Fallback) عبر قراءة `query_params['token']`.
   - **الخطأ القاتل:** يتم التحقق من متغير البيئة `ENVIRONMENT`. إذا كانت القيمة `production` أو `staging`، تقوم الدالة صراحة برفض التوكن وإرجاع `None`.
   - يُغلق الخادم الاتصال مع رمز الخطأ `4401` (Unauthorized).

## 3. الأدلة الجنائية التقنية (Forensic Evidence)
تم عزل المشكلة بدقة من خلال مراجعة الشيفرات المصدرية التالية:

- **أداة المصادقة (`app/api/routers/ws_auth.py`):**
  - السطر المعني برفض مسار التوافقية في بيئات الإنتاج:
    ```python
    settings = get_settings()
    if settings.ENVIRONMENT in ("production", "staging"):
        return None, None
    ```
  - يؤكد هذا السطر إحباط أي محاولة للاتصال عبر `?token=...` خارج بيئة التطوير.

- **سلوك واجهات العميل:**
  - واجهة الأدمن تستخدم `app/static/superhuman_dashboard.html` التي ترسل: `['jwt', token]`.
  - واجهة الزبون (`frontend/public/js/legacy-app.jsx`) لا تزال ترسل التوكن في مسار URL.

- **إغلاق الاتصال (`app/api/routers/admin.py` و `app/api/routers/customer_chat.py`):**
  - إذا لم يتم استرجاع التوكن عبر `extract_websocket_auth`، يتم إغلاق الاتصال فوراً:
    ```python
    token, selected_protocol = extract_websocket_auth(websocket)
    if not token:
        await websocket.close(code=4401)
        return
    ```

## 4. مصفوفة التناقض (Discrepancy Matrix)

| العنصر | مسار المسؤول (Admin) | مسار الزبون (Customer) |
| :--- | :--- | :--- |
| **Endpoint Used** | `/admin/api/chat/ws` | `/api/chat/ws` |
| **Auth Method** | Subprotocol Payload | Query String (`?token=...`) |
| **Protocol Header** | `Sec-WebSocket-Protocol: jwt, <token>` | *None or Generic* |
| **Server Environment Policy** | Allowed (Bypasses Fallback Block) | Blocked in `production`/`staging` |
| **Result** | Success (`101 Switching Protocols`) | Connection Closed (`4401 Unauthorized`) |

## 5. العوامل الخفية المحتملة (Blind Spots & Edge Cases)
- **آليات التخزين المؤقت (Browser Cache):** قد يستمر العميل في استخدام نسخة قديمة من الواجهة الأمامية التي تعتمد `Query Token` إذا لم يتم مسح ذاكرة التخزين المؤقت.
- **إعدادات Nginx/API Gateway Proxy:** قد يقوم الخادم الوكيل بإسقاط ترويسة `Sec-WebSocket-Protocol` لطلبات معينة أو تعديلها، على الرغم من أن السلوك الحالي في الكود يوضح أن الفشل يقع في طبقة التطبيق.
- **تكوين بيئة التشغيل (Environment Variable Drift):** غياب توحيد متغيرات البيئة بين الحاويات. لو كان النظام يعمل في بيئة `development`، لنجح مسار الزبون عبر مسار التوافقية (Fallback).

## 6. خطوات التحقق غير المدمرة (Non-Destructive Falsifiability Tests)
يمكن إثبات هذا التشخيص دون إجراء أي تعديل على الشيفرة عبر الخطوات التالية:

1. **فحص الشبكة عبر أدوات المطور (Browser DevTools):**
   - افتح واجهة الزبون في الإنتاج. في علامة تبويب `Network`، قم بتصفية طلبات `WS`. تحقق من مسار الطلب، ستجده يحتوي على `?token=...` وتأكد من غياب التوكن عن `Sec-WebSocket-Protocol`.

2. **محاكاة الاتصال باستخدام `wscat`:**
   - الاتصال بطريقة الأدمن (سينجح):
     `wscat -c wss://<domain>/api/chat/ws -s "jwt, <valid_customer_token>"`
   - الاتصال بطريقة الزبون (سيفشل بـ 4401):
     `wscat -c "wss://<domain>/api/chat/ws?token=<valid_customer_token>"`

3. **تغيير مؤقت لبيئة التشغيل محلياً (Local Emulation):**
   - قم بتشغيل الخادم المحلي مع تعيين المتغير `ENVIRONMENT="production"`.
   - حاول استخدام واجهة الزبون المحلية للاتصال. ستفشل فوراً بنفس الخطأ (4401)، مما يثبت أن الحظر ناتج حصرياً عن سياسة البيئة.