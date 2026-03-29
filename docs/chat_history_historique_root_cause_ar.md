# تشخيص جذري: لماذا لا يظهر `historique` للمحادثات؟

## الملخص التنفيذي
المشكلة **ليست** أن قاعدة البيانات لا تعمل، بل أن مسار الدردشة الفعلي للعميل القياسي يعمل حالياً كـ **واجهة توافقية (Compatibility Facade)** تقوم بتمرير الرسائل إلى `orchestrator-service` فقط، بينما واجهات استرجاع التاريخ (`/api/chat/conversations` و`/api/chat/latest`) تقرأ من جداول محلية (`customer_conversations`/`customer_messages`).

النتيجة: **انفصال مسار الكتابة عن مسار القراءة** (Write/Read Split-Brain)، فيظهر للمستخدم أن التاريخ “لا يُحفظ”.

## الأدلة التقنية المباشرة

1. تفعيل وضع الواجهة التوافقية محلياً:
   - `COMPATIBILITY_FACADE_MODE = True`.
2. نفس الملف يصرّح أن التنفيذ المحلي محجوب:
   - `LEGACY_LOCAL_EXECUTION_BLOCKED = True`.
3. WebSocket في `/api/chat/ws` يمرر الرسائل إلى `orchestrator_client.chat_with_agent(...)` بدل استدعاء `CustomerChatBoundaryService.orchestrate_chat_stream(...)` المحلي.
4. واجهات التاريخ (`/api/chat/conversations`, `/api/chat/conversations/{id}`, `/api/chat/latest`) تعتمد على `CustomerChatBoundaryService` المحلي الذي يقرأ من `CustomerChatPersistence` المحلي.
5. في مسار التوافق داخل WebSocket، حدث `conversation_init` القادم من الـ orchestrator يتم **تعديله/تجريده** بحيث لا يثبت معرف المحادثة الخارجي محلياً، ما يزيد صعوبة الربط.

## الاستنتاج البنيوي
الحالة الحالية تولد ثلاث قواعد بيانات منطقية مختلفة:

- **مصدر كتابة فعلي**: orchestrator (خارج المونوليث في هذا المسار).
- **مصدر قراءة الواجهة**: جداول محلية في المونوليث.
- **معرّف محادثة معروض في الواجهة**: قد يُعاد كتابته أو حجبه عند `conversation_init`.

وهذا يفسّر ظهور “لا يوجد historique” حتى عند نجاح الردود الفورية في الدردشة.

## الأسباب الثانوية المحتملة (تفاقم المشكلة)
- عدم وجود مزامنة/replication event بين orchestrator والتخزين المحلي.
- عدم وجود fallback محلي للكتابة عند فشل orchestrator.
- غياب قياسات SLI واضحة لمسار `chat_write_success` مقابل `history_read_success`.

## خطة إصلاح عملية (مرتبة حسب الأولوية)

### P0 — توحيد مصدر الحقيقة
اختر أحد الخيارين فوراً:
1. **إما** إعادة تفعيل الكتابة المحلية لنفس مسار WS (باستدعاء Boundary المحلي).
2. **أو** تحويل واجهات التاريخ لتقرأ من نفس مصدر orchestrator (API موحد للتاريخ).

> القاعدة الذهبية: لا يجوز أن يكتب النظام في خدمة ويقرأ التاريخ من خدمة مختلفة بدون مزامنة موثوقة.

### P1 — ثبات معرف المحادثة
- منع أي تعديل يغيّر `conversation_id` بدون طبقة mapping رسمية.
- إنشاء `conversation_id_mapping` إذا كان لابد من معرفين (خارجي/داخلي).

### P1 — مسار مزامنة رسمي (إن استمر الفصل)
- بث events من orchestrator (`conversation.created`, `message.saved`) مع consumer محلي idempotent.
- إضافة DLQ + retry + deduplication key.

### P2 — مراقبة واسترجاع
- مقاييس إلزامية:
  - `chat_messages_written_total`
  - `chat_history_reads_total`
  - `history_empty_after_successful_chat_total`
- إنذار فوري إذا زادت نسبة `history_empty_after_successful_chat_total` عن حد العتبة.

## اختبار قبول بعد الإصلاح
1. إنشاء محادثة جديدة عبر `/api/chat/ws`.
2. إرسال رسالتين.
3. استدعاء `/api/chat/conversations` يجب أن يعرض المحادثة.
4. استدعاء `/api/chat/conversations/{id}` يجب أن يعيد الرسالتين.
5. إعادة تحميل الواجهة: التاريخ يظهر دون فقدان.

## ملاحظة معمارية
هذه المشكلة هي نموذج كلاسيكي لـ **Split-Brain بين مسار الكتابة ومسار القراءة** داخل انتقالات microservices/cutover. معالجة جذرية تعني توحيد المصدر أو بناء مزامنة events موثوقة—وليس ترقيعاً في الواجهة فقط.
