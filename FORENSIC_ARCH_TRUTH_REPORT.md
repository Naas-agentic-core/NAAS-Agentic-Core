# 1) Executive Summary

أدناه أخطر 10 مشاكل مرتبة حسب: **architectural destructiveness → operational risk → change friction**.

1. **[P0] مساران Canonical متوازيان للدردشة (Monolith Chat vs Gateway→Orchestrator Chat)**
   - **Confidence:** Confirmed
   - **Evidence:**
     - `app/api/routers/customer_chat.py` و`app/api/routers/admin.py` يقدمان WS chat مباشرًا داخل المونوليث (`ChatOrchestrator.dispatch`).
     - `microservices/api_gateway/main.py` يقدّم نفس مسارات WS/HTTP chat ويوجهها إلى `orchestrator-service` أو `conversation-service`.
   - **Why it matters:** Source of truth للدردشة غير موحّد، ما يفتح split-brain سلوكي وتشخيصي.
   - **Root cause:** انتقال غير مكتمل من تنفيذ in-process إلى تنفيذ microservice مع façade دائم.
   - **Shortest safe fix:** فرض canonical runtime واحد (Gateway فقط) وتعطيل chat routes في app عند وضع production.
   - **Long-term fix:** استخراج chat بالكامل من `app/` وإبقاء app كتوافق read-only أو إزالته من مسار الإنتاج.

2. **[P0] Outbox موجود شكليًا لكن النشر الفعلي غير موثوق وقد يفشل صامتًا**
   - **Confidence:** Confirmed
   - **Evidence:**
     - `MissionStateManager.log_event` ينشئ outbox record ثم يستدعي `event_bus.publish(..., event)` حيث `event` كائن ORM لا dict.
     - `EventBus.publish` ينفذ `json.dumps(message)` ويتجاهل الفشل بسجل خطأ فقط.
     - لا يوجد worker يعالج `mission_outbox` pending.
   - **Why it matters:** ضياع أحداث البث الحي، وفقدان اتساق بين DB stream وWS stream.
   - **Root cause:** dual-write mitigation غير مكتمل (outbox pattern بدون relay).
   - **Shortest safe fix:** إرسال dict serializable فورًا + تحديث حالة outbox عند النجاح/الفشل.
   - **Long-term fix:** worker مستقل relay (poll/claim/publish/mark) مع retries وDLQ.

3. **[P0] split-brain في نماذج الحالة (Mission domain) بين `app/` و`orchestrator_service/`**
   - **Confidence:** Confirmed
   - **Evidence:**
     - `app/core/domain/mission.py` يعرّف نفس كيانات `missions/mission_events/mission_outbox`.
     - `microservices/orchestrator_service/src/models/mission.py` يعرّف النسخة الميكروسيرفسية نفسها تقريبًا.
   - **Why it matters:** ملكية الحالة غير واضحة؛ أي تعديل schema يرفع احتمال drift وتضارب migration.
   - **Root cause:** بقايا monolith domain بعد الانتقال إلى service-owned schema.
   - **Shortest safe fix:** إعلان orchestrator owner وحيد ومنع استخدام Mission models داخل app runtime.
   - **Long-term fix:** حذف/أرشفة نماذج mission من app + contract-based DTOs فقط.

4. **[P1] Conversation service هو parity stub فعليًا لكن مدمج في مسار canary الإنتاجي**
   - **Confidence:** Confirmed
   - **Evidence:**
     - `microservices/conversation_service/main.py` يعيد ردودًا synthetic (`conversation-service:{question}`) وecho-like envelopes.
     - gateway يحتوي rollout logic نحو conversation (`_resolve_chat_target_base`) حتى لو محمي بأعلام.
   - **Why it matters:** عند تفعيل خاطئ للأعلام، تتحول جلسات حقيقية إلى stub path.
   - **Root cause:** cutover feature flags قبل اكتمال capability.
   - **Shortest safe fix:** hard kill-switch دائم على conversation traffic ما لم contract parity tests end-to-end تمر ضد production-like payloads.
   - **Long-term fix:** إمّا تطويره ليصبح canonical chat service فعلي، أو إزالته من مسارات gateway.

5. **[P1] Drift واضح بين الوثائق والمعمارية التشغيلية الفعلية**
   - **Confidence:** Confirmed
   - **Evidence:**
     - `docs/MICROSERVICES_PLATFORM.md` يذكر orchestrator على 8004 بينما compose/runtime فعلي 8006.
     - OpenAPI gateway (`docs/contracts/openapi/gateway-api.yaml`) يصف مسارات `/v1/gateway/services/...` لا تطابق `microservices/api_gateway/main.py`.
   - **Why it matters:** فرق التشغيل تبني runbooks خاطئة، وQA يختبر عقودًا ليست الحقيقة.
   - **Root cause:** توثيق غير مولّد من code-first runtime.
   - **Shortest safe fix:** تجميد docs غير المتزامنة ووضع ختم "non-runtime reference".
   - **Long-term fix:** توليد spec/contracts من التطبيق الفعلي ضمن CI ورفض drift.

6. **[P1] Gateway health لا يعكس readiness لمسار chat cutover بالكامل**
   - **Confidence:** Confirmed
   - **Evidence:**
     - `/health` في gateway يفحص عدة خدمات لكنه لا يفحص `conversation-service` رغم أنه target محتمل للـ chat.
   - **Why it matters:** readiness false-positive أثناء canary chat.
   - **Root cause:** health matrix لا تتبع decision graph routing.
   - **Shortest safe fix:** health conditional على rollout flags ويشمل targets الفعلية.
   - **Long-term fix:** route-aware health SLI (per critical route).

7. **[P1] دلالات WebSocket contract غير متسقة بين العقود والمخرجات الفعلية**
   - **Confidence:** Confirmed
   - **Evidence:**
     - العقد (`gateway_chat_content_contracts.json`) يطلب outgoing `status` + `response`.
     - orchestrator WS يرسل أنواع `conversation_init/assistant_delta/assistant_final/...`.
     - conversation-service WS يرسل envelope مختلف.
   - **Why it matters:** كسر clients أو ترقيعات parsing متراكمة في frontend.
   - **Root cause:** contract governance يغطي shape قديم بينما producers تطوروا.
   - **Shortest safe fix:** تحديث contract للحقيقة الحالية أو adapter موحّد بالgateway.
   - **Long-term fix:** schema-versioned WS events + consumer-driven contracts حقيقية.

8. **[P1] حدود Async/Backpressure غير مضبوطة في WS path**
   - **Confidence:** High-confidence hypothesis
   - **Evidence:**
     - `websocket_proxy` يمرر رسائل ثنائية الاتجاه بلا message size caps ولا queue bounds.
     - frontend `useRealtimeConnection` يكدس `pendingQueue` بلا حد أقصى.
   - **Why it matters:** slow consumer أو burst ينتج memory pressure وانقطاع تدريجي.
   - **Root cause:** تصميم optimistic للـ streaming بدون flow control contract.
   - **Shortest safe fix:** حدود queue + max frame/message + drop policy.
   - **Long-term fix:** backpressure-aware protocol (ack windows / bounded buffers / shedding).

9. **[P2] Orchestrator locking/idempotency يحمي جزئيًا لكنه يسمح بمناطق تكرار محتملة**
   - **Confidence:** High-confidence hypothesis
   - **Evidence:**
     - lock TTL=10s مع مهام طويلة.
     - dispatch يتم عبر `asyncio.create_task` ثم release lock سريع.
     - التعليقات نفسها تشير إلى "Better: check status".
   - **Why it matters:** احتمالات duplicate execution/zombie dispatch تحت retries والضغط.
   - **Root cause:** عدم وجود execution lease/state-claim durable.
   - **Shortest safe fix:** claim column + compare-and-set status transition قبل dispatch.
   - **Long-term fix:** durable job queue + worker model بدل fire-and-forget task.

10. **[P2] CI guardrails واسعة جدًا بإعفاءات شاملة تُضعف وظيفة الحوكمة**
    - **Confidence:** Confirmed
    - **Evidence:**
      - `scripts/ci_guardrails.py` يحتوي إعفاءات `microservices/**` و`app/**` مع `ANY_TOKEN`.
    - **Why it matters:** الانحرافات المعمارية تمر رغم وجود "guardrails".
    - **Root cause:** guardrails تحولت إلى رمزية بعد تراكم استثناءات.
    - **Shortest safe fix:** إزالة wildcard exemptions تدريجيًا.
    - **Long-term fix:** policy-as-code دقيقة لكل boundary مع fail-closed.

---

# 2) Architecture Truth Map

## 2.1 الرسم المنطقي الفعلي من الكود

```text
Frontend (Next.js)
  ├─ HTTP -> /api/* rewrite -> API Gateway (8000)
  └─ WS   -> direct ws://.../api/chat/ws (not via rewrite)

API Gateway
  ├─ /api/v1/{planning,memory,users,auth,observability,research,reasoning,...} -> dedicated services
  ├─ /api/chat/* + /api/chat/ws + /admin/api/chat/ws -> orchestrator (default) or conversation (canary)
  └─ /api/v1/missions* -> orchestrator

Orchestrator Service
  ├─ /api/chat/messages (HTTP)
  ├─ /api/chat/ws + /admin/api/chat/ws (WS stategraph)
  ├─ /missions + /missions/{id}/events + /missions/{id}/ws
  └─ Redis pub/sub + Postgres mission state

Monolith app/ (still runnable)
  ├─ /api/chat/ws (customer)
  ├─ /admin/api/chat/ws (admin)
  ├─ internal ChatOrchestrator + boundary services + persistence
  └─ own domain models including mission entities
```

## 2.2 Service inventory (actual)

- `api-gateway`, `planning-agent`, `memory-agent`, `user-service`, `observability-service`, `orchestrator-service`, `research-agent`, `reasoning-agent`, `auditor-service`, `conversation-service`, plus infra stores (Redis, multiple Postgres).
- `app/` ليس خدمة compose افتراضية هنا، لكنه تطبيق FastAPI كامل قابل للتشغيل ويملك chat runtime فعلي.

## 2.3 Services mentioned vs incomplete/stub/not truly wired

- **conversation-service**: wired في compose وgateway، لكن capability الحالية stub/parity.
- **many platform claims (Kafka/NATS/Keycloak/Istio full chain)**: موجودة في docs/infra manifests، لكنها ليست path runtime الافتراضي في `docker-compose.yml` المحلي.

## 2.4 هل المشروع Monolith + Microservices معًا؟

- **نعم، Confirmed.**
- يوجد Microservices control-plane فعلي + monolith runtime بديل/متداخل خاصة في chat.

## 2.5 Naming drift

- أسماء متزامنة: `NAAS-Agentic-Core` + `EL-NUKHBA` + `CogniForge` مستخدمة بالتوازي في README/compose/docs.
- تأثير: هوية منتج/منصة غير موحدة، تزيد friction في ownership والوثائق.

## 2.6 Owner Matrix (مختصر تشغيلي)

| Service | Responsibility | Actual state owned | DB | Cache | Inbound | Outbound | Sync/Async |
|---|---|---|---|---|---|---|---|
| api-gateway | routing/proxy | no durable domain | none | in-process CB state | HTTP+WS | all services | sync + WS stream |
| orchestrator-service | missions/chat orchestration | missions, mission_events, conversations tables | postgres-orchestrator | redis pubsub/lock | HTTP+WS | planning/memory/research/reasoning/user/auditor | sync + async task |
| conversation-service | parity chat façade | none durable | none | none | HTTP+WS | none | sync/WS |
| planning-agent | plan generation | plans/steps | postgres-planning | none | HTTP | internal graph + optional DSPy | sync + to_thread |
| memory-agent | memory APIs | memory records | postgres-memory | none | HTTP | none | sync |
| user-service | auth/users/admin | user domain | postgres-user | none | HTTP | none | sync |
| observability-service | telemetry analytics | mostly in-memory runtime state | optional postgres config, but service logic in-memory repos | in-process | HTTP | none | sync |
| app (legacy/compat) | legacy API + chat | customer/admin conversations + overlapping mission models | monolith DB | optional caches | HTTP+WS | orchestrator via client + local logic | sync + WS |

## 2.7 Legacy vs modern matrix

- **Canonical (intended):** gateway + orchestrator-service for chat/mission.
- **Compatibility façade still active:** app admin/customer chat WS routes, gateway legacy-deprecated routes still callable.
- **Dead code candidates:** duplicated mission models in app, legacy contract surfaces not matching gateway runtime.
- **Transitional but prod-risky:** conversation-service canary scaffolding.

---

# 3) Critical Request Flows

## 3.1 Chat HTTP flow
- **Entrypoint:** `api-gateway /api/chat/{path}`.
- **Path:** gateway decides target via rollout+parity flags.
- **State transitions:** none in gateway; target handles persistence.
- **Retry semantics:** GET/HEAD/OPTIONS فقط retriable في proxy.
- **Timeout semantics:** connect/read/write from gateway settings.
- **Idempotency:** غير مضمونة لمسارات POST chat.
- **Persistence truth:** orchestrator DB (عند target orchestrator) أو لا شيء (conversation stub).
- **Partial failure:** gateway returns 502/503.
- **Restart behavior:** in-flight stream تنقطع.
- **Duplicate request:** ممكن ينتج duplicate processing في target.

## 3.2 Chat WS flow
- **Entrypoint:** `api-gateway /api/chat/ws` أو `/admin/api/chat/ws`.
- **Auth:** forwarded subprotocols (jwt, token)؛ no explicit gateway JWT validation for WS route نفسها.
- **Streaming behavior:** full-duplex proxy بلا backpressure controls واضحة.
- **Disconnect:** task cancel عند أول طرف ينتهي؛ no drain policy.
- **Slow consumer:** غير مضبوط (Unknown upper bounds).

## 3.3 Gateway -> Orchestrator flow
- proxy عبر `GatewayProxy.forward` مع circuit breaker + retries limited.
- body streaming uses `request.stream()` (non-replayable), لذلك retries مقيدة عمليًا.

## 3.4 Conversation-service parity/cutover
- governed by `CONVERSATION_PARITY_VERIFIED` + `CONVERSATION_CAPABILITY_LEVEL` + rollout percent.
- failure mode: misconfiguration => traffic to stub path.

## 3.5 Mission launch flow
- `/missions` في orchestrator -> `start_mission`.
- create mission (idempotency key optional) -> redis lock محاولة -> `asyncio.create_task` background run.
- persistence truth: mission tables in orchestrator DB.
- partial failure: lock failure يدخل degraded dispatch.

## 3.6 Agent orchestration flow
- orchestrator bootstraps LangGraph admin/unified graph if deps available.
- warmup invocation used as readiness signal جزئي.
- on missing deps, startup does not fail بالكامل (warning + degraded capability).

## 3.7 Retrieval/reranker flow
- Present across planning/reasoning/orchestrator code, لكن تفعيل runtime يعتمد تبعيات وpaths متعددة.
- **Unknown from code-only certainty:** مستوى reranker الحقيقي في production traffic دون run trace.

## 3.8 Auth flow
- HTTP services تعتمد service token/JWT checks حسب الخدمة.
- WS auth extraction via subprotocol + query fallback (orchestrator allows fallback broadly).

## 3.9 Telemetry flow
- gateway لديه middlewares trace/request-id.
- observability-service يستقبل telemetry لكنه يحلل in-memory غالبًا.
- end-to-end distributed trace غير مثبت بالكامل من runtime path المحلي.

## 3.10 Frontend proxy flow
- HTTP via Next rewrites to gateway.
- WS bypass rewrites مباشرة إلى `NEXT_PUBLIC_WS_URL`/location-derived URL.
- this creates dual transport assumptions بين server-side rewrite وclient-side WS direct.

---

# 4) Root-Cause Architecture Diagnosis

## Diagnosis A: "Distributed Monolith by Parallel Control Planes"
- **Evidence chain:** app chat orchestration + microservice chat orchestration + gateway routing to both modern/stub targets.
- **Why root cause:** لأنه يولّد كل الأعراض: contract drift, debugging hell, rollout fragility.
- **Blast radius:** chat UX, persistence consistency, operational oncall.
- **Refactor direction:** canonical control plane واحد (gateway→orchestrator), وحذف التنفيذ الموازي في app.

## Diagnosis B: "Transactional illusion: outbox without relay"
- **Evidence chain:** outbox writes موجودة، لكن publish best-effort + no worker + swallowed errors.
- **Why root cause:** يقطع ضمان delivery بين state change وevent stream.
- **Blast radius:** mission WS reliability, replay correctness.
- **Refactor direction:** durable outbox relay service + explicit publish status transitions.

## Diagnosis C: "Contract governance is lagging runtime"
- **Evidence chain:** WS contracts require fields لا تطابق producers، OpenAPI gateway paths لا تطابق main runtime.
- **Why root cause:** يمنع safe evolution ويخلق fragile adapters.
- **Blast radius:** frontend compatibility, partner integration.
- **Refactor direction:** contract-from-code generation + consumer tests against live handlers.

## Diagnosis D: "Cutover by flags over non-ready target"
- **Evidence chain:** conversation-service stub + gateway rollout knobs.
- **Why root cause:** temporal coupling عالي (flags/rollout states).
- **Blast radius:** production chat quality.
- **Refactor direction:** capability gate tied to canary SLO evidence, not manual flag only.

## Diagnosis E: "Governance guardrails degraded by mega-exemptions"
- **Evidence chain:** `ANY_TOKEN` exemptions واسعة.
- **Why root cause:** architecture policy not enforceable عمليًا.
- **Blast radius:** uncontrolled drift across modules.
- **Refactor direction:** shrink exemptions + mandatory owner approvals per exemption.

---

# 5) WebSocket / Streaming / Async Audit

- **WS termination points:** gateway websocket routes + orchestrator ws + conversation ws + app ws.
- **accept locations:** all above call `websocket.accept(...)` مباشرة.
- **auth locations:**
  - orchestrator: `extract_websocket_auth` + `decode_user_id`.
  - app: similar with env-based fallback restrictions.
  - gateway WS: proxy-only, no local JWT validation.
- **message limits/rate limits:** غير مثبت limits واضحة في gateway WS أو orchestrator WS loops.
- **backpressure controls:** لا queue bounds في backend WS proxy؛ frontend pending queue غير محدود.
- **heartbeat/ping-pong:** غير واضح في تطبيق WS handlers (Unknown from code explicitness).
- **blocking داخل async path:** planning uses `asyncio.to_thread` لتخفيف graph.invoke blocking (good).
- **unsafe assumptions:** request streaming retries + unlimited pending buffers.
- **slow downstream/client disconnect:** proxy cancels pending task عند FIRST_COMPLETED، لكن لا graceful finalization semantics.

---

# 6) State, Transactions, Consistency

- **Core entities:** missions/plans/tasks/events/outbox + chat conversations/messages.
- **True owner (intended):** orchestrator for mission domain؛ لكن app يحتفظ بنسخ models (ownership ambiguity).
- **Outbox:** موجود schema + writes.
- **Atomic publication with DB write:** غير متحقق؛ فقط DB atomic ثم publish best-effort.
- **Redis usage:** lock + pub/sub (ليس source of truth).
- **Durability:** DB durable، Redis events non-durable pub/sub.
- **Event loss possible:** نعم (Confirmed).
- **Idempotency:** mission create يعتمد `idempotency_key` unique؛ chat idempotency غير واضحة.
- **Unique constraints/txn boundaries:** idempotency key unique موجود؛ لكن distributed execution claim غير مكتمل.
- **Race conditions:** محتملة في dispatch/lock release timing.
- **Distributed lock anti-pattern:** lock قصير + release قبل اكتمال العمل الطويل.
- **Duplicate/zombie work:** احتمال مرتفع تحت retry/restart scenarios (High-confidence hypothesis).

---

# 7) Agents / Orchestration / Reasoning Layer

- **Graph الحقيقي:** orchestrator يبني `admin_graph` و`create_unified_graph` عند startup (إذا التبعيات متاحة).
- **Supervisor/nodes:** موجودة ضمن `services/overmind/graph/*` وlanggraph service stack.
- **Exit conditions/max_iterations:** غير موحدة في نقطة واحدة من الملفات المقروءة؛ تعتمد graph internals.
- **Validator gates:** warmup check exists لكنه check وظيفي محدود (tool invoked or not).
- **DSPy role:** planning agent يستخدم DSPy اختياريًا؛ fallback plan عند غياب التبعيات/API key.
- **LlamaIndex/MCP/tooling:** موجودة في dependencies وtool registry، لكن الاستخدام الإنتاجي الكامل يحتاج runtime traces.
- **Tool governance:** admin tool contract + auth checks موجودة لكن broad exception/fallbacks تقلل الصرامة.
- **Dead branches/stubs:** conversation stub، legacy orchestrator paths في app client fallback logic.
- **Production-ready vs demo-grade:** mixed؛ بعض المسارات production-minded، بعضها parity/demo scaffolding.
- **Transport coupling:** قوي بين orchestration output shapes وWS/frontend parsing heuristics.

---

# 8) Frontend / API Contract / Compatibility Analysis

- frontend HTTP يعتمد gateway rewrites.
- frontend WS يعتمد direct URL logic وليس rewrite، ما يضيف coupling بيئي (port inference/host fallback).
- frontend parsing يدعم أنواع أحداث متعددة (assistant_delta/final/error/conversation_init)، ما يعكس contract non-uniformity.
- migration path موجود لكن فوضوي جزئيًا: façade compatibility من جهة، وعقود WS legacy shape من جهة أخرى.

---

# 9) Docs-vs-Code-vs-Compose Drift

| Claim in docs | Code reality | Compose reality | Test coverage | Operational implication | Severity |
|---|---|---|---|---|---|
| Orchestrator at 8004 (`docs/MICROSERVICES_PLATFORM.md`) | orchestrator code/urls use 8006 | compose maps 8006:8006 | no strict doc-port test | runbook misrouting | P1 |
| Gateway OpenAPI paths `/v1/gateway/services/...` | gateway runtime exposes `/api/v1/...`, `/api/chat/...` etc | compose runs that runtime | partial contract tests, not this spec parity | integrator confusion | P1 |
| Architecture claims strict microservice separation | app still has full chat WS execution path | app not in default compose but code alive/tests active | many tests on app chat | split-brain risk remains | P0 |
| Conversation as gradual cutover target | service itself parity stub | compose deploys it as normal service | capability tests exist | accidental bad cutover | P1 |
| Event backbone reliability | outbox+pubsub implementation incomplete | redis present but no relay worker | no worker coverage | event loss under fault | P0 |

---

# 10) Observability & Operability Audit

- **What exists:** structured logs, request-id/trace middleware في gateway، health endpoints، observability-service APIs.
- **Propagation:** trace context injection موجود gateway-side، لكن end-to-end proof across services غير مكتمل.
- **Alerts/SLIs:** لا evidence قوي على alert rules مرتبطة critical chat/mission path في compose runtime المحلي.
- **Measurable now:** health status، basic service metrics endpoints، بعض telemetry events.
- **Blind spots:** WS backpressure, event delivery success rate (outbox->publish), duplicate mission dispatch rate.
- **Healthchecks:** موجودة في compose لمعظم الخدمات؛ لكن ليست كلها meaningful لمسارات الأعمال (مثلاً conversation omitted in gateway /health deps).
- **CI protection quality:** قوي في lint/tests، لكن guardrails المعمارية مخففة بإعفاءات واسعة.

---

# 11) Top 20 Findings Table

| ID | Category | Title | Sev | Confidence | Evidence | Root cause | Blast radius | Customer impact | Engineering drag | Fix now | Fix later | Test to prove | Owner |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| F-01 | Architecture | Dual canonical chat paths | P0 | Confirmed | app routers + gateway chat routes | incomplete cutover | chat platform | inconsistent behavior | high | disable app chat in prod | remove legacy chat | end-to-end single path test | Platform |
| F-02 | Consistency | Outbox relay missing | P0 | Confirmed | state.log_event + event_bus | partial pattern | mission events | missing live updates | high | serialize dict + status updates | dedicated outbox worker | fault-injection publish loss test | Orchestrator |
| F-03 | Ownership | Mission model duplication | P0 | Confirmed | app/core/domain/mission + orchestrator models | split ownership | schema governance | latent data drift | high | declare single owner | delete duplicate models | architecture import ban test | Arch Council |
| F-04 | Cutover | Conversation stub in rollout path | P1 | Confirmed | conversation main + gateway rollout | premature canary path | chat traffic | degraded answers | medium | rollout hard-stop | real implementation or remove | synthetic+real parity suite | Gateway/Conversation |
| F-05 | Contracts | WS envelope mismatch | P1 | Confirmed | consumer contract vs ws payloads | stale contracts | frontend/ws clients | parse failures | high | update contract now | versioned event schemas | CDC tests with real payloads | API Gov |
| F-06 | Docs drift | Orchestrator port drift | P1 | Confirmed | docs vs compose/code | manual docs | ops runbooks | incident risk | medium | patch docs | spec generation | doc parity CI test | DevRel |
| F-07 | Observability | Gateway health missing conversation dependency | P1 | Confirmed | gateway /health service map | route-unaware health | rollout readiness | hidden degradation | medium | conditional health target checks | route SLI matrix | health-by-route test | Platform |
| F-08 | Async | No WS backpressure bounds | P1 | High-confidence | websocket_proxy + frontend queue | optimistic streaming design | ws stability | disconnects/latency | high | queue/message caps | protocol-level flow control | load test slow consumer | Realtime |
| F-09 | Idempotency | Dispatch duplication window | P2 | High-confidence | entrypoint lock/task flow | weak execution lease | mission exec | double-run risk | medium | CAS status claim | durable job queue | duplicate-trigger chaos test | Orchestrator |
| F-10 | Governance | Guardrails over-exempted | P2 | Confirmed | ci_guardrails ANY_TOKEN wildcards | policy erosion | whole repo | drift accumulation | high | remove broad exemptions | ownership-based policies | red-team boundary tests | QA/Architecture |
| F-11 | Security/WS | Query token fallback inconsistency app vs orchestrator | P2 | Confirmed | ws auth helper differences | duplicated auth logic | ws auth behavior | inconsistent access | medium | unify auth policy module | central auth gateway for WS | ws auth matrix test | Security |
| F-12 | Compatibility | Frontend WS direct routing bypasses rewrite model | P2 | Confirmed | next config + hooks | split transport assumptions | frontend connectivity | env-specific breakage | medium | explicit WS URL required | central BFF ws endpoint | env matrix e2e | Frontend |
| F-13 | Runtime | external docker network prerequisite undocumented in compose | P2 | Confirmed | compose network external:true | hidden infra dependency | local deploy | startup failure | low | document/create script | remove external hard dependency | compose up smoke test | DevOps |
| F-14 | Contracts | OpenAPI gateway spec not runtime-accurate | P1 | Confirmed | gateway-api.yaml vs main.py | stale artifact | integrations | client errors | medium | mark deprecated spec | auto-generate spec | spec-vs-route parity test | API Gov |
| F-15 | Data durability | Redis pub/sub only for live stream | P2 | Confirmed | event_bus subscribe/publish | non-durable stream bus | live observers | missed events | medium | replay from DB by sequence | durable stream bus | disconnect/reconnect replay test | Orchestrator |
| F-16 | Complexity | Orchestrator client has local fallback execution paths | P2 | Confirmed | app orchestrator_client local tools/retrieval | hidden coupling to local FS/tools | service boundaries | unpredictable behavior | high | disable fallback in prod | isolate fallback service | mode-specific contract tests | App Team |
| F-17 | Drift | naming/product identity drift | P3 | Confirmed | README/docs/compose names | parallel branding evolution | docs & onboarding | confusion | low | naming glossary | repository-wide rename policy | docs lint for naming | PM/Arch |
| F-18 | Testing | Large test surface includes both legacy and modern paths | P2 | Confirmed | pytest collect 1640 tests | transition not converged | delivery velocity | slow migration | medium | tag canonical suites | retire legacy suites in phases | coverage by domain ownership | QA |
| F-19 | Operability | readiness based on health only, not dependency SLOs | P2 | High-confidence | simple /health checks | shallow readiness model | deployments | silent brownouts | medium | add dependency latency/error thresholds | progressive readiness gates | canary gate tests | SRE |
| F-20 | Architecture | Monolith app still critical to many tests/routes | P1 | Confirmed | app routers/tests heavy | incomplete decomposition | long-term agility | major refactor friction | high | explicit scope split | separate repos/services | decomposition completion KPI | CTO Office |

---

# 12) The 3 Most Dangerous Things

1. **أخطر مشكلة معمارية:** وجود مسارين canonical للدردشة (app وmicroservices) يخلق split-brain دائم.
2. **أخطر مشكلة تشغيلية عند التوسع:** WS/event flow بدون backpressure + outbox غير مُرحّل durable.
3. **أخطر مشكلة صيانة/سرعة فريق:** drift الوثائق/العقود + guardrails المعطلة باستثناءات واسعة.

---

# 13) Refactor Roadmap

## خلال 72 ساعة (Containment)
- قفل production على canonical chat path واحد عبر gateway→orchestrator فقط.
- تعطيل conversation rollout (0%) hard-coded في production profile.
- إصلاح publish payload ليكون serializable dict + تسجيل فشل outbox بوضوح.
- إضافة check CI يمنع اختلاف gateway routes عن contract الأساسي.

## خلال أسبوعين (Structural correction)
- بناء outbox relay worker (pending→published/failed + retries).
- توحيد WS auth policy module بين app/orchestrator.
- فرض queue/message limits في WS backend/frontend.
- تحديث docs الحرجة (ports/routes/canonical ownership).

## خلال 6 أسابيع (Migration strategy)
- نقل/إزالة chat execution من app بالكامل.
- إلغاء mission domain duplication في app.
- اعتماد event schema versioning (v1/v2) مع adapters transitional.
- تقليل guardrail exemptions بنسبة كبيرة مع owners.

## خلال 3 أشهر (Consolidation)
- فصل legacy compatibility إلى package/repo مستقل أو إزالته.
- route-aware SLO dashboards + alerting على critical flows.
- deprecation رسمي لمسارات legacy مع rollback playbook.

## Kill list
- app chat WS التنفيذي في production path.
- أي fallback محلي في orchestrator client داخل production mode.

## Merge list
- merge auth extraction logic لمسار WS.
- merge contract source-of-truth into generated artifacts.

## Canonical path decisions
- Chat/Mission canonical = API Gateway → Orchestrator Service.
- Conversation Service: إمّا promote كامل بعد parity حقيقي أو إزالة تامة من routing.

## Deprecation plan
- إعلان legacy routes deprecated مع metrics usage window.
- بعد zero-traffic window، حذف endpoints تدريجيًا.

## Rollback plan
- feature flag per route مع instant fallback إلى orchestrator-only.
- database changes backward-compatible حتى اكتمال cutover.

---

# 14) Proof Appendix

## أهم الملفات المقروءة
- `README.md`, `docker-compose.yml`, `pyproject.toml`, `requirements*.txt`
- `app/main.py`, `app/kernel.py`, `app/api/routers/{customer_chat,admin,ws_auth,registry}.py`
- `app/services/chat/orchestrator.py`, `app/infrastructure/clients/orchestrator_client.py`
- `microservices/api_gateway/{main,proxy,websockets,config}.py`
- `microservices/orchestrator_service/{main.py,src/api/routes.py,src/core/event_bus.py,src/services/overmind/{state.py,entrypoint.py},src/models/mission.py}`
- `microservices/conversation_service/main.py`
- `frontend/next.config.js`, `frontend/app/hooks/{useAgentSocket,useRealtimeConnection}.js`
- `scripts/ci_guardrails.py`, `.github/workflows/ci.yml`
- عقود/توثيق: `docs/contracts/...`, `docs/MICROSERVICES_PLATFORM.md`, `docs/ARCH_SPLIT_BRAIN_REPORT.md`

## أوامر الفحص المستخدمة
- `find . -maxdepth 4 -type f`
- `find . -maxdepth 2 -type d`
- `rg -n "websocket|...|RLS" app microservices frontend tests scripts docs infra .github/workflows`
- `pytest --collect-only -q`
- `python scripts/ci_guardrails.py`
- `ruff check .`

## Search map (keywords)
- websocket/streaming/retry/circuit/timeout/Redis/pubsub/outbox/idempotency/transaction/async/LangGraph/DSPy/llama/retriever/MCP/auth/gateway/conversation/mission/orchestrator/trace/prometheus/health/parity/rollout/canary/supabase/RLS.

## Missing information that blocks certainty
- لا يوجد runtime production traces فعلية (latency distributions, disconnect rates, queue pressure).
- لا يوجد chaos/load execution artifacts حديثة لمسارات WS الحرجة.
- لا يوجد evidence تشغيلي يثبت نسبة استخدام app legacy vs gateway path في الإنتاج.

## What must be measured in staging/prod
- outbox pending age + publish success rate.
- duplicate mission dispatch rate.
- WS queue depth / dropped messages / reconnect storm metrics.
- per-route cutover success/error SLOs خلال canary.

## Code-proven vs runtime-unproven
- **Code-proven:** split paths, outbox gap, contract drift, stub conversation capability.
- **Runtime-unproven:** الحجم الحقيقي للانفجارات تحت ضغط فعلي، وتكرار الأخطاء في traffic real-world.

---

## Security-only appendix (not prioritized)

- SECRET/CORS hardening موجود جزئيًا في settings validators.
- WS auth fallback via query in orchestrator يحتاج tightening موحد.
- هذه ليست أعلى المخاطر مقارنةً بمخاطر source-of-truth والانهيار التشغيلي أعلاه.
