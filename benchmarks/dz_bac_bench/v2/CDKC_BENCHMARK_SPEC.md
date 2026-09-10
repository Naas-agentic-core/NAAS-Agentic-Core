# DZ-BAC-Bench v2 — CDKC Benchmark Specification

## معيار البكالوريا الجزائرية v2 — مواصفة معيار CDKC

> **الإصدار:** v2.0.0-cdkc
> **الأساس:** v1 (موجود) + CDKC (جديد كلياً)
> **الحالة:** PROPOSED — لا يُدعى جاهزاً حتى 100 مهمة معايرة
> **الترخيص المقترح:** مفتوح (MIT) للمهام، مغلق للبيانات الخام الحساسة

### الفروق عن v1

| الخاصية | v1 | v2 CDKC |
|---|---|---|
| ما يقيسه | دقة إجابة | معرفة دائمة + استرجاع + تحقق + ثقة + لغة |
| التحقق | LLM-as-Judge | تحقق رمزي أولاً، LLM خط أساس فقط |
| اللغة | عربية فصيحة | عربي + فرنسي + دارجة + تبديل |
| المعايرة | لا | Brier + reliability + resolution + is_calibrated |
| المنشأ | غير محدد | كل مهمة بمصدر + تاريخ + مؤلف |
| إعادة التشغيل | غير محددة | بذور + إصدارات + نصوص كاملة |

### هيكل المهمة

```jsonl
{
  "task_id": "dz-bac-2023-math-ex2-step3",
  "version": "2.0.0-cdkc",
  "concept_id": "continuity",
  "stream": "sciences_experimentales",
  "session_year": 2023,
  "statement_ar": "ناقش اتصال الدالة f عند 0",
  "statement_fr": "Discuter la continuité de f en 0",
  "language_switches": [],
  "difficulty_b": 0.8,
  "discrimination_a": 1.2,
  "barem_nodes": ["continuity-def", "limit-calc"],
  "steps": [
    {"claim": "lim f(x) = ...", "verification": "limit", "points": 0.5},
    {"claim": "f(0) = ...", "verification": "equality", "points": 0.5}
  ],
  "expected_verdict": "proven",
  "cdkc": {
    "durable_mastery": 0.25,
    "retrievability": 0.85,
    "confidence": 0.90,
    "symbolic_verdict": "proven",
    "cdkc_clipped": 0.12,
    "quadrant": "dangerous"
  },
  "provenance": "bac-2023-math — خطأ حقيقي مصنف",
  "author": "research-independent-v1",
  "created_at": "2026-09-10T00:00:00Z"
}
```

### معايير القبول

- كل مهمة: نص أصلي + concept_id من shared/curriculum + barem_nodes غير فارغة + steps غير فارغة + content_hash فريد
- كل حزمة 100 مهمة: ≥30 معايرة (≥4 ملاحظات غير مدعومة) + تغطية ≥10 مفاهيم + ≥3 شعب
- بطاقة معايرة منشورة: brier + reliability + resolution + is_calibrated
- بيان حدود: ما لم يُختبر — يُكتب أولاً

### بوابات CI المستقبلية

- `check_item_coverage`: كل (مفهوم × شعبة) له حد أدنى من العناصر
- `check_barem_item_linkage`: رسم لا دوري + مجموع نقاط مطابق
- `check_symbolic_no_timeout_pass`: TIMEOUT لا يمر أبداً
- `check_cdkc_maturity`: غير المعاير موسوم إجبارياً

### الفوائد الأربع من حركة واحدة

1. تُنجز الالتزام المقطوع بمجموعة اختبار موسومة ومعدل خطأ مقيس
2. تجذب باحثين ومساهمين مجاناً (حل لمشكلة فريق صغير)
3. تجعل هذا المشروع المرجع الذي يُقاس عليه غيره لا العكس
4. تحوّل ضعفاً معلناً (لا بيانات جزائرية) إلى مركز ثقل أكاديمي

نشر نتائج النماذج العامة على المعيار ليس تواضعاً — هو الحركة التنافسية: من يحدد ملعب القياس يحدد القواعد.

### ما لا يجوز ادعاؤه

لا "بنك أسئلة ذكي" — بل: "N عنصراً، منها M معايرة على عدد كافٍ من الاستجابات، والباقي بصعوبة مقدرة تصريحياً ومعلمة كذلك."

لا "نتوقع نجاح ابنك" — بل: "توزيع احتمالي مشروط بالأداء المقيس حتى اليوم، ودقتنا التاريخية منشورة. في الدورة الأولى هذا التوقع غير معاير ونقوله."

---

*مواصفة معيار بقرار باحث مستقل — إضافة لا حذف.*
