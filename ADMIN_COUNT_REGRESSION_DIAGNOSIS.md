# التشريح الجراحي لخلل "إجابات عامة بدل العدّ الدقيق" في أسئلة الأدمن

## 1) ملخص تنفيذي شديد الدقة

الخلل **ليس** في قدرة النظام على العدّ نفسها، بل في **مسار التوجيه (Routing) قبل التنفيذ**:

1. في المسار القديم/Legacy (`/agent/chat`) يتم اكتشاف النية عبر `IntentDetector`.
2. أنماط `ADMIN_QUERY` الحالية لا تحتوي كلمات مثل `python / بايثون / files / ملفات / count`، لذلك سؤال مثل:
   - "كم عدد ملفات بايثون في المشروع؟"
   يُصنَّف `DEFAULT` بدل `ADMIN_QUERY`.
3. عند `DEFAULT` يذهب النظام إلى `chat fallback` (مساعد تعليمي عام) بدل استدعاء أدوات العدّ.
4. النتيجة: إجابة عامة من LLM (مثل: "لا أستطيع إعطاء عدد دقيق...") بدل نتيجة shell/tool رقمية.

إذن: **الانحدار Regression في طبقة Intent-Routing، لا في طبقة Tool-Execution**.

---

## 2) الدليل التشغيلي (Evidence) من الكود والاختبار المباشر

### 2.1 اختبار مباشر على كاشف النية الحالي
تم تشغيل:

```bash
python - <<'PY'
import asyncio
from microservices.orchestrator_service.src.services.overmind.utils.intent_detector import IntentDetector

async def main():
    d=IntentDetector()
    for q in ["كم عدد ملفات بايثون في المشروع", "count python files", "كم عدد المستخدمين", "database tables"]:
        r=await d.detect(q)
        print(q, '=>', r.intent.value, r.confidence)

asyncio.run(main())
PY
```

النتيجة:
- `كم عدد ملفات بايثون في المشروع => DEFAULT`
- `count python files => DEFAULT`
- بينما `كم عدد المستخدمين => ADMIN_QUERY`
- و `database tables => ADMIN_QUERY`

**استنتاج قطعي:** العدّ الخاص بملفات بايثون لا يمر إلى قناة الأدمن في هذا المسار.

### 2.2 سبب هذا السلوك من ملف الأنماط
أنماط `ADMIN_QUERY` الحالية تركّز على users/database/services/structure، بدون `python/files/count`.

### 2.3 ماذا يحدث بعد فشل التصنيف؟
في `OrchestratorAgent`:
- إذا لم تكن النية `ADMIN_QUERY`، ينتقل النظام إلى `_handle_chat_fallback`.
- `_handle_chat_fallback` مبني كمعلّم عام (Smart Tutor)، ويشجّع الشرح العام وليس تنفيذ أدوات نظام.

**هذه هي البوابة التي تولّد الإجابة العامة الظاهرة في الصورة.**

---

## 3) لماذا ظهر الخلل بعد التحول إلى Microservices؟

السبب البنيوي ليس "الميكروسيرفس بحد ذاته" بل **تعدد المسارات غير المتناظرة** بعد التفكيك:

1. يوجد مسار Unified StateGraph (`/admin/api/chat/ws`) وفيه حارس حتمي للكلمات الإدارية.
2. ويوجد مسار Legacy مباشر (`/agent/chat`) يعتمد `IntentDetector` مختلف.
3. عند عدم اتساق القواعد بين المسارين، ستحصل ظاهرة:
   - أحيانًا نفس السؤال يعطي عدًّا دقيقًا.
   - وأحيانًا يعطي إجابة عامة.

هذا نمط شائع بعد الانتقال من Monolith إلى Microservices + multi-entrypoints: 
**تجزؤ منطق التوجيه (Routing Drift).**

---

## 4) الأسباب الجذرية (Root Causes) مرتبة حسب الأثر

## RC-1 (حرج): فجوة تصنيف في `IntentDetector`
- `ADMIN_QUERY` لا يطابق أسئلة "count python files".
- النتيجة: Redirect إلى fallback chat.
- الأثر: ضياع الدقة الرقمية بالكامل.

## RC-2 (حرج/هيكلي): تعدد ممرات الإدمن بدون Contract Routing موحّد
- وجود أكثر من بوابة تنفيذ (Legacy Agent vs Unified Graph) بقواعد مختلفة.
- لا يوجد "Source of Truth" واحد للـ routing policy.
- الأثر: سلوك متذبذب حسب endpoint المستخدم من الواجهة/العميل.

## RC-3 (متوسط): fallback تعليمي permissive جدًا لأسئلة تتطلب أدوات
- عند فشل intent، fallback لا يتصدى بطلب re-route بل يولّد إجابة عامة.
- الأثر: "نجاح شكلي" UX لكنه "فشل وظيفي" في متطلبات الأدمن.

## RC-4 (متوسط): عدم صرامة إجبارية End-to-End على مسار الأدمن
- توجد محاولات صرامة ممتازة في أجزاء من النظام، لكنها ليست مفروضة على كل entrypoint.
- الأثر: تفاوت في الالتزام بمبدأ "No tool = No answer".

---

## 5) مصفوفة الأعراض ↔ السبب

- **عرض:** "لا أستطيع إعطاء عدد دقيق" في سؤال عدّ مباشر.
  - **سبب مباشر:** السؤال لم يصنف `ADMIN_QUERY`.
- **عرض:** النظام كان دقيق سابقًا (Monolith) والآن متقلب.
  - **سبب بنيوي:** route fragmentation بعد الفصل إلى خدمات ومسارات متعددة.
- **عرض:** بعض أسئلة الأدمن تعمل (مثل users/tables) وبعضها لا.
  - **سبب:** أنماط `admin_queries` تغطي بعضها فقط.

---

## 6) التشخيص النهائي (Final Diagnosis)

الخلل ناتج عن **انقطاع سلسلة القرار الإداري** عند أول عقدة تصنيف في مسار Legacy:

`Admin Question (python files)`
→ `IntentDetector` لا يتعرف عليها كـ `ADMIN_QUERY`
→ `DEFAULT`
→ `Smart Tutor Fallback`
→ `LLM general answer`

بدل السلسلة الصحيحة:

`Admin Question (python files)`
→ `ADMIN_QUERY`
→ `AdminAgent / Admin Tool Contract`
→ `shell/tool execution`
→ `exact numeric answer`

---

## 7) لماذا هذا التشخيص "جراحي" وموثوق؟

لأنه مبني على:
1. فحص مسار التنفيذ الفعلي endpoint-by-endpoint.
2. ربط السلوك المرئي في الصورة مع منطق fallback التعليمي.
3. اختبار حي لكاشف النية أثبت الانحراف بنفس صياغة السؤال.
4. تحليل الفارق المعماري بين المسار الموحد والمسار القديم.

---

## 8) خلاصة تنفيذية للإدارة

- **ما تعطل؟** ليس العدّ، بل التوجيه إلى العدّ.
- **متى يتعطل؟** عندما يأتي السؤال بصيغة ملفات بايثون في المسار الذي يعتمد `IntentDetector` الحالي.
- **لماذا الآن؟** بعد تفكيك المنظومة، تعددت مسارات الدخول وتباينت قواعد intent/routing.
- **ما النتيجة؟** ردود تعليمية عامة بدل قياسات تشغيلية دقيقة.

> التشخيص القاطع: **Regression in Admin Intent Routing Policy under multi-path microservice architecture.**
