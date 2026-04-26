# Context Blindness Forensics — 2026-04-26

## Scope
This report records a code-and-test-grounded diagnosis of chat context-loss behavior across routing, identity, persistence, schema, semantic resolution, node contract, frontend continuity, test evidence, and observability.

## Key confirmed findings
1. There are parallel chat WS entrypoints in monolith (`app/api/routers/*.py`), gateway (`microservices/api_gateway/main.py`), and orchestrator (`microservices/orchestrator_service/src/api/routes.py`).
2. Gateway HTTP chat proxy routes `/api/chat/*` to orchestrator, but orchestrator does not expose `/api/chat/latest`, while monolith does; this creates route contract divergence.
3. Orchestrator compiles graph without checkpointer when initialization fails/unavailable; this is an explicit fallback mode.
4. Orchestrator HTTP path can generate UUID conversation identifiers before DB reconciliation, while WS path forces DB-backed conversation IDs.
5. Frontend keeps `conversationId` only in React runtime state and resets it on new chat/reload path unless history is reloaded.
6. Tests demonstrate strong identity/checkpointer intent, but WS stategraph tests are currently failing due to runtime envelope/error path mismatch.

## Evidence sources
- app/api/routers/customer_chat.py
- app/api/routers/admin.py
- microservices/api_gateway/main.py
- microservices/orchestrator_service/src/api/routes.py
- microservices/orchestrator_service/src/services/overmind/graph/main.py
- microservices/orchestrator_service/src/services/overmind/graph/general_knowledge.py
- microservices/orchestrator_service/src/services/overmind/graph/supervisor.py
- frontend/app/hooks/useAgentSocket.js
- frontend/app/hooks/useRealtimeConnection.js
- frontend/app/components/CogniForgeApp.jsx
- tests/unit/test_chat_context_seed_strategy.py
- tests/unit/test_context_utils.py
- tests/microservices/test_orchestrator_chat_stategraph.py
- tests/contracts/test_gateway_routing_contracts.py
