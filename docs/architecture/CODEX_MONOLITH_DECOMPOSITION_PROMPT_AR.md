# برومبت تشخيص الازدواجية وتفكيك المونوليث (Codex)

## الهدف
استخدم هذا البرومبت عندما تريد من Codex إجراء **تشخيص معماري أدلّي** (evidence-based) لمشكلة ازدواجية المنطق وبقاء المونوليث، ثم تقديم خطة تفكيك تدريجية متوافقة مع دستور الخدمات المصغّرة في هذا المستودع.

---

## البرومبت الجاهز

> **مهمّتك:** أنت معماري برمجيات خبير ومحلّل تعليمات برمجية. لديك مستودع بعنوان `HOUSSAM16ai/NAAS-Agentic-Core` يحتوي على المونوليث (`app/`) وخدمات مصغّرة (`microservices/`) مبنية بـ Python وFastAPI وLangGraph وLlamaIndex وDSPy وNext.js. المطلوب: تشخيص دقيق لازدواجية المنطق ومخاطر الـDistributed Monolith، ثم إنتاج خطة عملية للتفكيك التدريجي.
>
> **مصادر إلزامية للقراءة قبل التحليل:**
> 1) `docs/ARCH_MICROSERVICES_CONSTITUTION.md`
> 2) `docs/architecture/05_monolith_to_microservices_roadmap_ar.md`
> 3) `docs/architecture/FULL_CODEBASE_MULTI_AGENT_DIAGNOSTIC.md`
> 4) `FINAL_ARCHITECTURE_DIAGNOSTIC.md`
> 5) `docs/architecture/NEXT_MICROSERVICE_CANDIDATE_REPORT.md`
>
> **منهجية العمل (إلزامية):**
> - لا تكرر نص الوثائق حرفيًا. لخّص ثم طبّق على الكود الفعلي.
> - كل استنتاج يجب أن يرتبط بدليل: مسار ملف + وظيفة/صف + أثر معماري.
> - ميّز بوضوح بين: (أ) الوضع الحالي، (ب) المخاطر، (ج) الإجراءات العلاجية.
> - أي اقتراح هجرة يجب أن يتجنب Big Bang Rewrite ويلتزم Strangler Fig + Anti-Corruption Layer.
>
> **المخرجات المطلوبة:**
>
> ### 1) خريطة ازدواجية المنطق
> - أنشئ جدولًا يحصي كل منطق مكرر بين `app/` و`microservices/`.
> - ضمّن على الأقل:
>   - اسم المجال (Chat, Observability, AIOps, Auth, ...)
>   - الموضع الأول (ملف/خدمة)
>   - الموضع الثاني (ملف/خدمة)
>   - نوع الازدواجية (business logic / orchestration / transport / schema)
>   - مستوى الخطورة (High/Med/Low)
>   - الأثر (behavior drift, testing complexity, split-brain, ...)
>
> ### 2) تقييم الالتزام بالدستور
> - افحص كل خدمة مقابل القواعد الدستورية:
>   - استقلالية الخدمة
>   - التواصل الشبكي فقط (HTTP/gRPC/events)
>   - عدم مشاركة منطق الأعمال عبر مكتبات مشتركة
>   - Database per Service
>   - Zero Trust
> - قدّم **جدول امتثال**: القاعدة، الحالة (ملتزم/جزئي/غير ملتزم)، الدليل، الإصلاح المقترح.
>
> ### 3) تشخيص الأعطال الحاسمة
> - حدّد نقاط Split-Brain في مسارات المحادثة.
> - حدّد أي تكرار بين WebSocket في المونوليث ومنطق الـorchestrator.
> - افحص استخدام DSPy داخل سياقات Async وحدد حالات حجب event loop.
> - افحص نمط الأحداث الحالي: Pub/Sub غير مستديم مقابل Redis Streams/Outbox.
> - أضف **تحليل فشل** (Failure Mode): العرض، السبب الجذري، قابلية الرصد، إجراء الاحتواء.
>
> ### 4) خطة تفكيك المونوليث (Roadmap تنفيذية)
> - خطة مرحلية من 3 موجات:
>   1. Modular Monolith Hardening
>   2. Chat Orchestration/BFF Extraction (الأولوية الأولى)
>   3. Core Services Progressive Extraction
> - لكل موجة: الأهداف، الأعمال، متطلبات المنصة، المخاطر، شروط الدخول/الخروج.
> - إلزاميًا:
>   - Shadow Mode + Feature Flags + Canary
>   - Anti-Corruption Layer أثناء الانتقال
>   - Database per Service ومنع cross-service joins
>   - استبدال Pub/Sub الهش بـ Redis Streams أو Outbox
>   - معالجة الاستدعاءات المتزامنة داخل async باستخدام `asyncio.to_thread` أو بدائل async أصلية
>
> ### 5) آليات الحوكمة والاختبار
> - عرّف بوابات منع الارتداد (Regression Gates):
>   - Consumer-Driven Contracts
>   - Architecture fitness functions (CI)
>   - Trace IDs موحّدة عبر الخدمات
>   - Chaos / Partial failure tests
>   - سياسات تمنع دمج أي PR يخالف الدستور
> - اذكر من يملك القرار (Ownership matrix) بين Gateway / Orchestrator / Domain Services.
>
> ### 6) مؤشرات النجاح (KPIs)
> - قدّم KPIs قابلة للقياس زمنيًا، مثل:
>   - % المسارات المنقولة من المونوليث
>   - معدل فشل النشر Deployment Failure Rate
>   - MTTR
>   - SLO attainment per service
>   - Duplicate logic index
>   - نسبة الاعتماد على استدعاءات داخلية غير شبكية (يجب أن تؤول للصفر)
>
> **تنسيق الإخراج:**
> - ابدأ بملخص تنفيذي (10 نقاط كحد أقصى).
> - استخدم جداول موجزة للتشخيص والامتثال.
> - أختم بخطة 90 يومًا (30/60/90) مع مخاطر وتخفيفات واضحة.
> - اجعل اللغة مباشرة وقابلة للتنفيذ، وابتعد عن العموميات.

---

## تحسينات إضافية موصى بها عند الاستخدام

- اطلب من Codex حساب **"Duplicate Logic Index"** بهذه الصيغة:
  `عدد الوحدات المكررة وظيفيًا / إجمالي الوحدات النشطة`.
- اطلب منه تصنيف كل تكرار إلى:
  - تكرار مقبول مؤقتًا (Transitional Duplication)
  - تكرار ضار دائم (Harmful Duplication)
- اطلب إنشاء **Migration Backlog** بصيغة Stories قابلة للتنفيذ (Owner + Estimate + Dependency + Rollback).
- اطلب **Decision Log (ADR-lite)** لكل قرار معماري حساس لتفادي الارتداد.

---

## معايير قبول الإجابة (Definition of Done)

تعتبر إجابة Codex ناجحة فقط إذا:
1. تضمنت أدلة ملفية واضحة لكل استنتاج.
2. فرّقت بين الدَّين المؤقت أثناء الهجرة والتصميم المخالف الدائم.
3. قدمت خطة انتقال تدريجية بدون Big Bang Rewrite.
4. حددت حوكمة تمنع إعادة إنتاج الازدواجية لاحقًا.
5. تضمنت KPIs كمية بخط أساس وهدف زمني.
