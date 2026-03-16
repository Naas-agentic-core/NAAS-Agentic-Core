# خطة الإصلاح التدريجي الشامل لكارثة NAAS-Agentic-Core (Evidence-Based)

## ملخص تنفيذي
هذا المستند يترجم التقارير الجنائية الحالية إلى **خطة تنفيذية تدريجية** بدون كسر المسارات الحرجة: 
1) تسجيل الدخول `/login`، 2) عدّ ملفات بايثون للإدارة، 3) استرجاع التمارين للزبائن.  
النهج المعتمد: **Strangler Fig + Anti-Corruption Layer** مع منع أي Big-Bang Rewrite.

---

## 1) خريطة الأعطال والازدواجية (Duplication & Failure Map)

| المجال | الملف الأول | الملف الثاني | نوع الازدواجية | التصنيف | الخطورة | الأثر | السبب الجذري | الإصلاح المقترح |
|---|---|---|---|---|---|---|---|---|
| مسار WS للدردشة | `app/api/routers/customer_chat.py` (`/api/chat/ws`) | `microservices/api_gateway/main.py` (`/api/chat/ws`) | ازدواج نقطة دخول Runtime | Structural Split-Brain | P0 | تضارب ملكية جلسة WS وتباين السلوك حسب البوابة | تشغيل مسار محلي Legacy بالتوازي مع WS Proxy في Gateway | تثبيت سلطة WS في الـBFF فقط ثم إطفاء المسار المحلي تدريجياً عبر Canary |
| سلطة التنسيق | `app/services/chat/orchestrator.py` (`ChatOrchestrator`) | `microservices/orchestrator_service/src/services/overmind/graph/main.py` (`SupervisorNode`) | ازدواج منطق قرار النية/المسار | Orchestration Drift | P0 | نفس السؤال قد يُصنَّف بشكل مختلف (مسار عام vs أدوات إدارية) | وجود منسّقين فعليين داخل Monolith + Microservice | توحيد سلطة القرار في orchestrator-service وإبقاء app كـThin BFF |
| عقد الحدث | `app/api/routers/customer_chat.py` يرسل `delta` | `microservices/orchestrator_service` يولّد `assistant_delta` | تعدد Schemas لنفس الغرض | Contract Drift | P1 | تعطل/تسطيح streaming في الواجهات وفقد semantic event typing | غياب Envelope موحّد إلزامي | فرض `ChatEventEnvelope` موحّد وترجمة وحيدة في ACL |
| بث المهام | `microservices/orchestrator_service/src/core/event_bus.py` (Redis Pub/Sub) | `app/core/redis_bus.py` (Bridge) | قناة غير مستديمة + تحويلات متضاربة | Event Durability Gap | P1 | فقد أحداث عند انقطاع المستهلك/إعادة الاتصال | الاعتماد على Pub/Sub fire-and-forget | استبدال قناة الـmission بـRedis Streams + consumer groups + replay |
| عدّ ملفات بايثون | `app/infrastructure/clients/orchestrator_client.py::_build_local_file_count_response` | `microservices/orchestrator_service/src/contracts/admin_tools.py` (`admin.count_python_files`) | ازدواج capability execution | Transitional Duplication (مقبول مؤقتاً) | P1 | احتمال drift في رسالة الخرج أو في قواعد recognition | وجود fallback محلي + tool بعيد بدون عقد استهلاكي موحّد | تثبيت Consumer Contract لرسالة النتيجة، والإبقاء المؤقت على fallback حتى parity |
| RBAC | `app/services/rbac.py` | `microservices/user_service/src/services/rbac.py` | تكرار منطق الأعمال | Risky Duplication | P1 | تباين البذور/الأوصاف/التحديثات عبر الزمن | ترحيل غير مكتمل مع dual ownership | نقل ownership إلى user_service مع Token Claims ثابتة وقراءة فقط في app |
| Persistence داخل المونوليث | `app/services/admin/chat_persistence.py` | `app/services/customer/chat_persistence.py` | تكرار Repository Pattern مع اختلاف طفيف | Manageable Duplication | P2 | عبء صيانة واحتمال drift في قواعد التخزين | عدم وجود abstraction مشتركة على مستوى interface | توحيد abstraction على مستوى port داخلي مع بقاء schema ownership واضح |
| ملكية بيانات المحادثات | `app/core/domain/chat.py` + persisters في app | SQL writes داخل `microservices/orchestrator_service/src/api/routes.py` | كتابة نفس الجداول من خدمتين | Database Ownership Leak | P0 | خرق Database-per-Service + تنازع state | تشغيل Hybrid يكتب من monolith والمicroservice لنفس الجداول | خطة فصل DB تدريجية: owner واحد للكتابة + Outbox/CDC للنسخ |

### تمييز مهم: ازدواجية انتقالية vs ازدواجية ضارة
- **Transitional Duplication (مسموح مؤقتاً):** fallback المحلي لعدّ الملفات/استرجاع التمارين داخل `orchestrator_client` لتأمين الاستمرارية عند تعطل control plane.  
- **Harmful Duplication (يجب إزالته):** ازدواج سلطة orchestration وازدواج WS endpoints وازدواج RBAC ownership.

---

## 2) تقييم الالتزام بالدستور (Constitution Compliance)

| قاعدة دستورية | الحالة | الدليل من الكود | الفجوة | الإجراء التصحيحي |
|---|---|---|---|---|
| استقلالية الخدمة | جزئي | وجود `ChatOrchestrator` في المونوليث بالتوازي مع orchestrator graph | سلطة قرار مزدوجة | نقل orchestration authority كاملة للخدمة الخارجية |
| التواصل عبر الشبكة فقط بين الخدمات | جزئي | app يستخدم `orchestrator_client`، لكن لا يزال ينفّذ منطق orchestration محلياً | app ليس BFF رقيقاً بالكامل | إبقاء app طبقة نقل/تحقق فقط وإزالة القرار المحلي |
| قاعدة بيانات لكل خدمة | غير ملتزم | app وorchestrator_service يكتبان جداول conversations/messages نفسها | Data ownership leak | owner وحيد للكتابة + ACL + migration stages |
| عدم مشاركة منطق الأعمال | غير ملتزم | تكرار RBAC في monolith + user_service | Contract drift/security drift | توحيد RBAC authority في user_service |
| Zero Trust | جزئي | سياسات WS auth متباينة بين المسارات المحلية والبوابة | تفاوت سلوك المصادقة وتوحيد الرسائل | توحيد authN/authZ policy وevented errors عبر gateway/bff |
| Observability/Correlation | جزئي | gateway يحقن traces، لكن ليس كل hops بعقد موحّد للأحداث | صعوبة تتبّع الأعطال عبر المسارات المختلطة | إلزام Trace ID + request_id في كل envelope وفي كل hop |

---

## 3) تشخيص الأعطال الجذرية (Failure Modes)

| العطل | العرض | السبب الجذري | قابلية الرصد | الاحتواء الفوري | الإصلاح الدائم |
|---|---|---|---|---|---|
| Split-Brain Chat | اختلاف النتائج حسب نقطة الدخول | مساران WS فعالان + منسّقان مختلفان | متوسطة (تحتاج traces مقارنة) | Feature flag لتجميد مسار واحد لكل tenant | Thin BFF + إزالة منطق `ChatOrchestrator` المحلي |
| Event Loop Blocking | ارتفاع latency/تجمّد WS تحت الضغط | نداء DSPy متزامن داخل `SupervisorNode.__call__` | عالية عبر loop lag metrics | تغليف النداء بـ`asyncio.to_thread` | حظر CI لأي sync I/O في عقد graph |
| Event Loss | فقد mission events بعد reconnect | Redis Pub/Sub غير مستديم | منخفضة حالياً | replay يدوي من DB للمتصلين الجدد | Redis Streams + consumer groups + offsets |
| Schema Drift (`delta`/`assistant_delta`) | واجهة عميل تستقبل أنواع متضاربة | عدم وجود canonical event contract موحّد | عالية عبر contract tests | adapter واحد عند boundary | توحيد envelope في جميع الخدمات |
| Admin Count Regression | إجابة عامة بدل رقم دقيق | drift في intent routing + path duality | متوسطة | fallback محلي في `orchestrator_client` | authority موحد + CDC contracts للأدوات |

---

## 4) خطة التفكيك التدريجية بدون كسر الميزات (3 Waves)

## Wave 1 (أسابيع 1-4): Modular Monolith Hardening
**الهدف:** جعل المونوليث واجهة حدودية صلبة بدل منسق قرار موازٍ.

### الأعمال
1. تجميد عقود `/login` وعدم تغيير request/response shape نهائياً.  
2. فرض Event Envelope موحّد (`assistant_delta`, `assistant_final`, `assistant_error`, `status`).  
3. منع أي إضافة جديدة داخل `ChatOrchestrator` المحلي (حالة deprecation enforced).  
4. تفعيل Fitness Gates: منع imports المتقاطعة ومنع وصول DB عبر حدود غير مالكة.

### ضمانات عدم الكسر
- **Login:** يبقى `security.py:/login -> AuthBoundaryService.authenticate_user` دون تعديل واجهة.  
- **File Count:** الإبقاء على `_build_local_file_count_response` كحماية مؤقتة.  
- **Exercise Retrieval:** الإبقاء على `_build_local_retrieval_response` + `detect_exercise_retrieval`/`make_result` كما هي.

### Exit Criteria
- 100% من أحداث chat تطابق العقد الموحد.
- Contract tests خضراء لمسارات login/admin count/exercise retrieval.

## Wave 2 (أسابيع 5-8): Chat Orchestration/BFF Extraction
**الهدف:** نقل سلطة التنفيذ بالكامل إلى orchestrator/conversation service.

### الأعمال
1. app يصبح BFF رقيق: auth + trace ids + proxy streaming فقط.  
2. Shadow Mode: تنفيذ المسار الجديد في الخلفية ومقارنة parity.  
3. Canary: 1% → 5% → 25% → 50% → 100%.  
4. بعد تحقق parity: إيقاف WS المحلي وإزالة routing المحلي لـ`ChatOrchestrator`.

### ضمانات عدم الكسر
- fallback المحلي يبقى مفعلًا فقط عند فشل orchestrator حتى اكتمال parity.
- واجهة العميل لا تتغير (backward compatible event translation خلال الانتقال).

## Wave 3 (أسابيع 9-12): Core Services Progressive Extraction
**الهدف:** إنهاء الديون البنيوية عالية الخطورة.

### الأعمال
1. RBAC/Auth ownership إلى user_service (source of truth واحد).  
2. استبدال Pub/Sub في mission stream بـRedis Streams + Outbox.  
3. إزالة الاستدعاءات المتزامنة داخل async nodes (`asyncio.to_thread` أو async-native).  
4. توحيد ملكية التخزين (single-writer policy) وإيقاف dual writes.

### Exit Criteria
- لا يوجد write تنافسي لنفس جداول المحادثات من خدمتين.
- لا يوجد sync blocking path داخل graph runtime.

---

## 5) آليات الحوكمة والاختبار

## 5.1 Consumer-Driven Contracts
- Chat WS contract: أنواع الأحداث وترتيبها (`init -> delta/status -> final|error -> complete`).
- Auth contract: `/login` response shape ثابت.
- Admin count contract: رسالة متوافقة مع `make_result` في `file_intelligence`.
- Exercise retrieval contract: fallback يحترم `ExerciseRetrievalResult` semantics.

## 5.2 Architecture Fitness Functions (CI)
1. منع أي import مباشر عبر حدود service ownership.  
2. منع كتابة جداول غير مملوكة للخدمة.  
3. منع sync I/O في async graph nodes.

## 5.3 Observability & Chaos
- Correlation/Trace IDs إلزامية على جميع hops.  
- Chaos Scenarios: 
  - orchestrator down
  - Redis latency spike
  - user_service down
- قياس degradation behavior والتأكد من fallback السليم.

## 5.4 Migration Backlog + ADR-lite
### نموذج Story Backlog
| Story ID | الوصف | المالك | التقدير | الاعتمادية | Rollback |
|---|---|---|---|---|---|
| MIG-CHAT-001 | Freeze chat contracts + unified envelope | Platform | 3d | لا شيء | تعطيل flag |
| MIG-CHAT-004 | Enable shadow mode for customer chat | API/BFF | 4d | MIG-CHAT-001 | fallback to legacy path |
| MIG-DATA-007 | Streams migration for mission events | Infra | 5d | MIG-CHAT-004 | switch back to pub/sub |
| MIG-RBAC-010 | RBAC ownership transfer to user_service | IAM | 6d | MIG-DATA-007 | claims fallback readonly |

### ADR-lite المطلوبة
- ADR-CHAT-001: Single orchestration authority.
- ADR-EVENT-002: Redis Streams replacing Pub/Sub for mission events.
- ADR-IAM-003: RBAC ownership and claims propagation policy.

---

## 6) المؤشرات (KPIs) وخط الأساس

| KPI | Baseline (حالي) | هدف 60 يوم | هدف 90 يوم |
|---|---:|---:|---:|
| Duplicate Logic Index | 0.40 | ≤0.25 | ≤0.18 |
| نسبة مسارات chat المنقولة للسلطة الموحدة | 0-20% (حسب البيئة) | 70% | 100% |
| معدل فشل النشر (Deployment Failure Rate) | يُقاس من آخر 30 نشر | -30% | -50% |
| MTTR | baseline من incidents الأخيرة | -20% | -35% |
| SLO attainment (chat availability/latency) | baseline تشغيلية | +10% | +20% |
| incidents of event loss | baseline من mission streaming | -50% | ~0 حوادث |
| نسبة الاستدعاءات الداخلية غير الشبكية عبر الحدود | مرتفعة/هجينة | -50% | ≤10% |

### طريقة القياس
- baseline أسبوع أول قبل أي cutover.
- مراجعة أسبوعية مع scoreboard وقرار go/no-go لكل wave.

---

## ملاحق الحماية للمسارات الحساسة (Non-Breaking Annex)
1. **لا تعديل** على API contract لمسار `/login`.  
2. **لا تعديل سلوكي** على `detect_exercise_retrieval` و`make_result` في capability retrieval.  
3. **لا كسر** لرسالة عدّ الملفات المتوافقة تاريخياً من `file_intelligence.make_result`.  
4. **الإبقاء على fallback المحلي** في `orchestrator_client` حتى اكتمال parity المثبت اختباريًا.

