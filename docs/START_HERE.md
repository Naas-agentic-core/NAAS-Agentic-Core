# Start Here (Beginner-Friendly)

مرحبًا بك في منصة **CogniForge**. هذا الدليل هو نقطة البداية الوحيدة للمطورين الجدد.

## 1) ما هو هذا المستودع؟

- منصة **API-First** مبنية على مبادئ الحدود الصارمة بين الخدمات.
- تعتمد على **طبقات واضحة** لكل خدمة: API → Domain → Use Cases → Infra → Tests.

## 2) أين أبدأ؟

1. اقرأ نظرة عامة على المعمارية:
   - `docs/ARCHITECTURE.md`
2. اقرأ قواعد الجودة والاختبارات:
   - `docs/quality/standards.md`
   - `docs/quality/testing.md`
3. استعرض خريطة المستودع الحالية:
   - `docs/REPOSITORY_MAP.md`
4. اقرأ دليل التوجيه العملي للمستودع:
   - `docs/guides/NEWCOMER_CODEBASE_MAP.md`

## 3) تشغيل المشروع محليًا

### المتطلبات الأساسية

- Python 3.12+
- Docker (اختياري للخدمات)

### تثبيت الاعتماديات

```bash
make install-dev
```

### تشغيل الاختبارات

```bash
make test
```

### تشغيل فحوصات CI محليًا

```bash
make ci
```

## 4) كيف تتنقل داخل المشروع؟

- **الواجهات (API):** `app/api` أو `microservices/<service>/api`
- **المنطق التجاري:** `app/domain` أو `microservices/<service>/domain`
- **حالات الاستخدام:** `app/application/use_cases` أو `microservices/<service>/use_cases`
- **البنية التحتية:** `app/infrastructure` أو `microservices/<service>/infra`
- **الاختبارات:** `tests/` (تعكس بنية المصدر)

## 5) ماذا أفعل إن ضعت؟

ابدأ من `docs/ARCHITECTURE.md` ثم عد إلى هذا الملف. هذا المستودع مبني ليكون واضحًا للمبتدئين.
