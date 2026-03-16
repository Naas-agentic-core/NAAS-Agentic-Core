# التشخيص الأدلّي لازدواجية المنطق وخطر المونوليث الموزّع

## الملخص التنفيذي (10 نقاط)
1. يوجد **Split-Brain فعلي** لمسار الدردشة: المونوليث يملك WebSocket محليًا بينما الـ API Gateway يمرّر نفس المسار إلى orchestrator/conversation، ما يخلق ازدواجية سلطة القرار والتدفق.
2. `ChatOrchestrator` داخل المونوليث ما زال ينفّذ Intent detection والتوجيه ويقوم بتفويض جزئي فقط إلى خدمة الأوركستراتور؛ هذه صيغة **Partial Delegation Anti-Pattern**.
3. يوجد انحراف عقدي في أحداث البث (`delta` مقابل `assistant_delta`) بما يرفع كلفة التوافق الخلفي واختبارات الواجهة.
4. خدمة orchestrator تستخدم DSPy بشكل متزامن داخل عقدة حاسمة، ما يعرّض event loop للحجب تحت الحمل.
5. نمط الأحداث الحالي في مهام mission يعتمد Redis Pub/Sub غير المستديم؛ توجد فجوة فقد أحداث بين replay من DB وبدء subscribe.
6. قاعدة **Database per Service** مهددة: جداول المحادثة (`customer_conversations`, `customer_messages`) تُكتب من المونوليث ومن orchestrator في نفس الوقت.
7. توجد ازدواجية منطق RBAC بين `app/` و`user_service` (مقبولة مرحليًا جزئيًا لتحقيق الاستقلالية، لكنها بلا بوابة تكافؤ سلوكي).
8. توجد ازدواجية عالية داخل المونوليث نفسه (admin/customer chat persistence/streaming) تزيد سطح التباين قبل الاستخراج إلى خدمات.
9. الامتثال الدستوري الحالي **جزئي**: استقلال الشيفرة بين الخدمات جيد، لكن الاستقلال التشغيلي وملكية الدومين في chat غير محسومين.
10. الأولوية التنفيذية الصحيحة خلال 90 يوم: **تحصين المونوليث → استخراج Chat Orchestration/BFF أولًا → استخراج تدريجي لباقي الخدمات مع Outbox/Streams وحوكمة CI معمارية**.

---

## 1) خريطة ازدواجية المنطق (Evidence Map)

| المجال | الموضع الأول | الموضع الثاني | نوع الازدواجية | التصنيف | الخطورة | الأثر |
|---|---|---|---|---|---|---|
| Chat WebSocket Ownership | `app/api/routers/customer_chat.py::chat_stream_ws` | `microservices/api_gateway/main.py::chat_ws_proxy` | orchestration + transport | Harmful Duplication | High | Split-brain + تضارب ownership |
| Chat Orchestration | `app/services/chat/orchestrator.py::process` | `microservices/orchestrator_service/src/services/overmind/graph/main.py::SupervisorNode` | business logic/orchestration | Harmful Duplication | High | behavior drift في routing/fallback |
| Chat Streaming Event Schema | `app/api/routers/customer_chat.py` (normalization to `delta`) | `microservices/orchestrator_service/src/api/routes.py` (`assistant_delta`) | schema/transport | Harmful Duplication | Med | contract drift للـ frontend |
| Mission Event Streaming | `microservices/orchestrator_service/src/api/routes.py::stream_mission_ws` (DB replay + subscribe) | `microservices/orchestrator_service/src/core/event_bus.py::subscribe` (Pub/Sub) | transport/eventing | Harmful Duplication | High | event loss window |
| Chat Persistence Tables | `app/services/customer/chat_persistence.py` | `microservices/orchestrator_service/src/api/routes.py::_ensure_conversation` | business logic + data ownership | Harmful Duplication | High | تضارب كتابة على نفس الجداول |
| RBAC Seeding & Role-Permission Mapping | `app/services/rbac.py::RBACService` | `microservices/user_service/src/services/rbac.py::RBACService` | business logic | Transitional Duplication | Med | drift بطيء إذا غابت parity tests |
| Admin/Customer Chat Persistence | `app/services/admin/chat_persistence.py` | `app/services/customer/chat_persistence.py` | business logic | Harmful Duplication | Med | إصلاح مزدوج + صعوبة refactor |
| Gateway↔Conversation ACL | `microservices/api_gateway/legacy_acl/adapter.py` | `app/services/boundaries/*` | anti-corruption/adapter duplication | Transitional Duplication | Low | عبء صيانة مؤقت |

### الملاحظات الأدلّية السريعة
- المونوليث يعرّف WebSocket للدردشة ويستدعي `ChatOrchestrator.dispatch` مباشرة.
- البوابة تعرّف `/api/chat/ws` وتحوّله إلى orchestrator/conversation حسب flags.
- منسق الدردشة بالمونوليث يفوض فقط بعض intents إلى `orchestrator_client.chat_with_agent`.
- خدمة orchestrator ترسل `assistant_delta` بينما واجهة المونوليث تُطبع أحداثًا على نمط `delta`.

### Duplicate Logic Index
- نطاق القياس في هذا التقرير: الوحدات النشطة الحرجة (Chat/Auth/Eventing/Observability) = **20 وحدة**.
- الوحدات المكررة وظيفيًا = **8 وحدات**.
- **Duplicate Logic Index = 8 / 20 = 0.40 (40%)**.
- الهدف خلال 90 يوم: خفضه إلى **≤ 0.18**.

---

## 2) تقييم الالتزام بالدستور (Constitution Compliance)

| القاعدة الدستورية | الحالة | الدليل | الإصلاح المقترح |
|---|---|---|---|
| استقلالية الخدمة (No in-process cross-service imports) | ملتزم | لا توجد imports مباشرة بين خدمات مختلفة؛ الاستدعاء عبر gateway/http client | الاستمرار مع Fitness Gate يمنع أي import cross-service |
| التواصل عبر الشبكة فقط | جزئي | التفويض من المونوليث للأوركستراتور عبر client موجود، لكن ما يزال منطق orchestration المحلي فعالًا | تحويل المونوليث إلى Thin BFF وإزالة decision logic المحلي |
| عدم مشاركة منطق الأعمال بمكتبة مشتركة | ملتزم شكليًا / جزئي سلوكيًا | يوجد تكرار RBAC بدل shared library (مقبول دستوريًا)، لكن دون contract parity | إضافة Behavioral Parity Tests وCDC بين Gateway/User Service |
| Database per Service | غير ملتزم في chat | نفس جداول chat تُستخدم في `app/core/domain/chat.py` وتُكتب من orchestrator SQL | فصل مخزن Conversation Service ومنع أي كتابة chat من app |
| Zero Trust | جزئي | تحققات token موجودة، لكن بعض WS flows تتحقق هوية فقط دون سياسات دقيقة موحّدة | Policy enforcement موحّد على gateway + service JWT scopes + mTLS داخلي |

---

## 3) تشخيص الأعطال الحاسمة (Critical Failures)

### 3.1 Split-Brain في مسارات المحادثة
- **الوضع الحالي:** مسار WS موجود في المونوليث، ومسار WS موازٍ في الـ API Gateway لنفس endpoint المنطقي.
- **الخطر:** ازدواج ownership للحالة، وتباين behavior بين مسار local dispatch ومسار proxy إلى orchestrator/conversation.
- **الإجراء العلاجي:** Gate واضح: Chat command/routing authority = orchestrator فقط؛ app يصبح transport/auth shell فقط.

### 3.2 ازدواج WebSocket بين المونوليث وorchestrator
- **الوضع الحالي:** `chat_stream_ws` بالمونوليث يمرّر stream محليًا بعد `ChatOrchestrator.dispatch`، بينما gateway يمرّر `/api/chat/ws` إلى خدمة خارجية.
- **الخطر:** split brain + صعوبة debugging + اختلاف format للأحداث.
- **الإجراء:** توحيد contract stream وإيقاف مسار WS المحلي خلف feature flag ثم إزالته.

### 3.3 DSPy داخل سياق قد يحجب async loop
- **الوضع الحالي:** `SupervisorNode.__call__` ينفّذ `self.dspy_classifier(query=query)` تزامنيًا.
- **الخطر:** under load قد يجمّد workers ويزيد timeouts في WS/HTTP.
- **الإجراء:** تحويل الاستدعاء إلى `await asyncio.to_thread(...)` أو اعتماد واجهة async أصلية + اختبار حمل على intent routing.

### 3.4 نمط الأحداث: Pub/Sub غير مستديم
- **الوضع الحالي:** `stream_mission_ws` يسحب history من DB ثم يبدأ subscribe على Pub/Sub.
- **الخطر:** فقد أحداث في نافذة الزمن بين الخطوتين.
- **الإجراء:** Redis Streams + consumer offsets أو Outbox + relay؛ ومنع الاعتماد على Pub/Sub كـ source-of-truth.

### جدول Failure Mode Analysis

| العرض | السبب الجذري | قابلية الرصد | إجراء الاحتواء |
|---|---|---|---|
| ردود chat تختلف حسب المسار | split-brain orchestration | متوسطة (logs مشتتة) | route lock + unified trace IDs |
| انقطاع/بطء WS وقت الذروة | DSPy sync call داخل مسار حرج | منخفضة بدون profiling | `to_thread` + latency SLO alarms |
| ضياع أحداث mission | Pub/Sub non-durable race | منخفضة (لا offset tracking) | Redis Streams/Outbox + replay by offset |
| تباين schema stream | `delta` vs `assistant_delta` | عالية (frontend parsing errors) | Contract versioned envelope + CDC |
| drift في صلاحيات RBAC | نسختان منطقيتان دون parity gate | متوسطة | parity tests + ownership matrix واضح |

---

## 4) خطة التفكيك المرحلية (3 Waves)

## Wave 1 — Modular Monolith Hardening (الأسبوع 1–4)
**الأهداف**
- تثبيت حدود الدومين داخل app ومنع أي orchestration business logic خارج ACL/BFF.

**الأعمال**
1. تعريف واجهة `ChatCommandPort` واحدة في app تستدعي orchestrator فقط.
2. إغلاق جميع فروع القرار في `ChatOrchestrator` خلف feature flag تمهيدًا للإزالة.
3. توحيد envelope الأحداث (`type`, `payload`, `trace_id`, `seq`).
4. إعداد Architecture Fitness Functions: منع استدعاء chat domain من routers مباشرة.

**متطلبات المنصة**
- Feature Flag service، Trace propagation، CDC test harness.

**المخاطر**
- كسر clients قديمة إذا تغير schema.

**شروط الدخول/الخروج**
- دخول: baseline traces مفعلة.
- خروج: 0% business routing داخل app chat + parity report أخضر.

## Wave 2 — Chat Orchestration/BFF Extraction (الأولوية الأولى، الأسبوع 5–8)
**الأهداف**
- نقل سلطة القرار كاملة لخدمة orchestrator/conversation مع إبقاء app كبوابة BFF رقيقة.

**الأعمال**
1. **Shadow Mode:** تشغيل المخرجات القديمة والجديدة بالتوازي دون تأثير المستخدم.
2. **Feature Flags + Canary:** 1% → 5% → 25% → 50% → 100% لمسار WS/HTTP.
3. **Anti-Corruption Layer:** ترجمة أي payload legacy إلى contract الخدمة الجديدة.
4. **Database per Service:** إيقاف أي كتابة chat من app، ومنع cross-service joins.

**متطلبات المنصة**
- dual-path observability، replay harness، rollback switch < 10 دقائق.

**المخاطر**
- latency أعلى مؤقتًا.

**شروط الدخول/الخروج**
- دخول: CDC passing + shadow parity ≥ 99%.
- خروج: 100% من chat intents تمر عبر orchestrator service contract.

## Wave 3 — Core Services Progressive Extraction (الأسبوع 9–12)
**الأهداف**
- استخراج تدريجي لخدمات core ذات التكرار الأعلى (Auth/RBAC, Observability eventing).

**الأعمال**
1. RBAC ownership إلى `user_service` مع API-only reads/writes.
2. استبدال Pub/Sub الهش بـ Redis Streams/Outbox للأحداث الحرجة.
3. معالجة أي استدعاءات متزامنة داخل async (`asyncio.to_thread` أو async-native clients).
4. إيقاف ACLs المؤقتة التي انتهت صلاحيتها.

**متطلبات المنصة**
- stream retention policies، DLQ، idempotency keys.

**المخاطر**
- migration fatigue وتداخل أولويات الفرق.

**شروط الدخول/الخروج**
- دخول: ownership matrix مصادق عليه.
- خروج: Duplicate Logic Index ≤ 0.18 + zero non-network internal calls.

---

## 5) آليات الحوكمة والاختبار (Regression Gates)

1. **Consumer-Driven Contracts (CDC):**
   - Gate إجباري قبل الدمج لأي تغيير schema في chat/auth/events.
2. **Architecture Fitness Functions (CI):**
   - منع imports مخالفة.
   - منع routers من استدعاء domain internals مباشرة.
3. **Trace IDs موحّدة:**
   - `X-Correlation-ID` إلزامي في كل hop + stream events.
4. **Chaos / Partial Failure Tests:**
   - انقطاع orchestrator، بطء Redis، انقطاع user_service.
5. **دستور-كحارس PR:**
   - أي PR يخالف قواعد الاستقلالية/DB per service/Zero Trust = فشل CI.

### Ownership Matrix
| النطاق | المالك الأساسي | المالك الثانوي |
|---|---|---|
| API Gateway (edge auth/rate-limit/routing) | Platform Team | Security |
| Orchestrator (intent + workflow decisions) | Orchestration Team | AI Platform |
| Conversation state & message history | Conversation Service Team | Data Platform |
| RBAC/Auth domain | User Service Team | Security |
| Mission events backbone | Platform Eventing Team | SRE |

---

## 6) Migration Backlog (Stories قابلة للتنفيذ)

| ID | القصة | Owner | Estimate | Dependency | Rollback |
|---|---|---|---|---|---|
| MIG-01 | توحيد Chat Stream Envelope وإضافة versioning | Orchestration | 5 أيام | لا شيء | إعادة parser legacy في gateway |
| MIG-02 | تفعيل Shadow Mode لمسارات chat WS/HTTP | Gateway | 4 أيام | MIG-01 | إطفاء flag خلال دقائق |
| MIG-03 | نقل ChatOrchestrator في app إلى Thin Adapter | Monolith Core | 6 أيام | MIG-02 | إعادة تفعيل local strategy عبر flag |
| MIG-04 | تطبيق `asyncio.to_thread` لعقد DSPy + اختبارات حمل | Orchestration | 3 أيام | لا شيء | الرجوع commit + تقليل traffic canary |
| MIG-05 | Redis Streams/Outbox لمسار mission events | Platform Eventing | 8 أيام | MIG-02 | fallback مؤقت لـ Pub/Sub مع polling reconciliation |
| MIG-06 | RBAC ownership كامل في user_service + CDC | Identity Team | 7 أيام | MIG-03 | fallback إلى app RBAC endpoints مؤقتًا |

---

## 7) ADR-lite (Decision Log)

### ADR-CHAT-001: سلطة تنسيق واحدة للمحادثة
- **Decision:** orchestrator service هو authority الوحيد للقرار.
- **Why:** إزالة split-brain وتقليل drift.
- **Consequences:** app يصبح BFF رقيق؛ أي ذكاء قرار خارج الخدمة مرفوض.

### ADR-EVT-002: استبدال Pub/Sub للأحداث الحرجة
- **Decision:** Redis Streams/Outbox بدل Pub/Sub كـ source-of-truth.
- **Why:** ضمان durability وإمكانية replay.
- **Consequences:** زيادة بسيطة في التعقيد التشغيلي مقابل موثوقية أعلى.

### ADR-AUTH-003: RBAC domain ownership
- **Decision:** user_service يملك RBAC؛ app يستخدم API contracts فقط.
- **Why:** إنهاء drift بين نسختين RBAC.
- **Consequences:** حاجة CDC واختبارات توافق عند كل تغيير صلاحيات.

---

## 8) KPIs (خط أساس + هدف زمني)

| KPI | خط الأساس الحالي | هدف 60 يوم | هدف 90 يوم |
|---|---:|---:|---:|
| % مسارات chat المنقولة للخدمة | 0–25% (متغير بالـflags) | 75% | 100% |
| Duplicate Logic Index | 0.40 | 0.25 | ≤ 0.18 |
| نسبة الاستدعاءات الداخلية غير الشبكية بين حدود الخدمات | > 0 (فعليًا في chat monolith) | < 0.1 | 0 |
| Deployment Failure Rate | baseline من CI الحالي | -20% | -35% |
| MTTR للأعطال متعددة الخدمات | baseline تشغيلي | -20% | -30% |
| SLO attainment (chat) | غير موحّد | 99.0% | 99.5% |
| Event loss incidents (mission) | موجودة احتماليًا | 0 مع replay | 0 مستدامة |

---

## 9) خطة 90 يوم (30/60/90)

### أول 30 يوم
- تثبيت العقود (chat/events/auth) + تفعيل CDC.
- Shadow Mode لمسارات chat.
- معالجة DSPy blocking (`to_thread`) واختبار حمل.
- **مخاطر:** drift في schema أثناء التوازي.
- **التخفيف:** versioned contract + dual parsers مؤقتة.

### خلال 60 يوم
- cutover تدريجي canary إلى orchestrator authority.
- منع كتابات chat من app وتثبيت Database per Service boundaries.
- إدخال Redis Streams/Outbox للأحداث الحرجة.
- **مخاطر:** زيادة latency.
- **التخفيف:** early streaming + timeouts + circuit breakers.

### خلال 90 يوم
- إزالة decision logic المحلي في app/chat نهائيًا.
- توحيد ownership في RBAC/auth domain.
- تفعيل policy gate يمنع أي PR يعيد الازدواجية.
- **مخاطر:** ارتداد معماري مع ضغط التسليم.
- **التخفيف:** ADR enforcement + architecture board أسبوعي + fitness CI gates.

---

## 10) ملاحظة ختامية
الازدواجية المؤقتة أثناء Strangler Fig مقبولة فقط إذا كانت **مؤطرة بزمن + معرّفة كـ Transitional + محمية ببوابات تكافؤ سلوكي**. ما عدا ذلك فهي تتحول إلى **Harmful Duplication** وتعيد إنتاج المونوليث الموزّع.
