# SUPER AGENT FAILURE FORENSIC REPORT

## 1. EXECUTIVE SUMMARY
Super Agent / المهمة الخارقة is failing for both admin and customer roles because the WebSocket payload contract for mission intent (`mission_type`) sent by the UI is not recognized by the `orchestrator-service` during the API Gateway canary routing phase. Consequently, the API Gateway proxy either routes the request incorrectly, or the orchestrator fallback triggers standard chat instead of `mission_complex`. Meanwhile, if the legacy monolith intercept occurs (due to proxy bypass or misconfiguration), it hits `MissionComplexHandler`, attempts an HTTP bridge call (`orchestrator_client.create_mission`), and fails immediately with the hardcoded string `"❌ **خطأ في النظام:** لم نتمكن من بدء المهمة (Dispatch Failed)."`.

Ordinary chat works because it either successfully routes to the modern `_run_chat_langgraph` in `orchestrator-service` (which gracefully handles standard text intents) or completes via the local monolith fallback handler (`DefaultChatHandler`), persisting correctly in both cases without triggering the strict HTTP mission dispatch bridge.

## 2. CURRENT RUNTIME TRUTH
- **API Gateway Routing:** `microservices/api_gateway/main.py` explicitly proxies both `/api/chat/ws` and `/admin/api/chat/ws` to either `conversation-service` (via canary) or `orchestrator-service` using `_resolve_chat_ws_target`.
- **Monolith Intercept Risk:** The legacy monolith WS endpoints (`app/api/routers/admin.py` and `app/api/routers/customer_chat.py`) still exist and parse `mission_type` from the root of the JSON payload. If they intercept traffic, they trigger `ChatOrchestrator.dispatch`.
- **Orchestrator Service Reality:** `microservices/orchestrator_service/src/api/routes.py` expects `mission_type: mission_complex` either at the root or nested inside a `metadata` object to trigger `handle_mission_complex_stream`.
- **The "Dispatch Failed" Source:** The exact string `"❌ **خطأ في النظام:** لم نتمكن من بدء المهمة (Dispatch Failed)."` originates strictly from `app/services/chat/handlers/strategy_handlers.py` in the monolith's `MissionComplexHandler.execute()` exception block.

## 3. WORKING ORDINARY CHAT FLOW
1. **Client Emission:** UI sends a standard chat payload (e.g., `{"question": "Hello"}`).
2. **Gateway Proxy:** `microservices/api_gateway/websockets.py` proxies the connection to `orchestrator-service` (or `conversation-service` via canary).
3. **Execution (Orchestrator):** In `microservices/orchestrator_service/src/api/routes.py`, `admin_chat_ws_stategraph` or `customer_chat_ws_stategraph` receives the payload.
4. **Contract Verification:** It checks for `mission_type == "mission_complex"`. Finding none, it defaults to `_run_chat_langgraph(objective, {})`.
5. **Persistence:** The StateGraph handles standard execution and yields status/response events back through the WS proxy.
6. **Result:** Both admin and customer successfully receive ordinary chat responses because the path avoids the legacy HTTP dispatch bridge.

## 4. FAILING SUPER AGENT FLOW
**Scenario A (Monolith Intercept):**
1. UI sends payload with `mission_type: "mission_complex"`.
2. Traffic hits legacy `app/api/routers/admin.py` or `customer_chat.py`.
3. `ChatOrchestrator.dispatch` delegates to `MissionComplexHandler` (`app/services/chat/handlers/strategy_handlers.py`).
4. Handler calls `start_mission(session=None, ...)`.
5. This attempts an HTTP call to the orchestrator via `orchestrator_client.create_mission()`.
6. The HTTP call fails (network isolation, auth, or schema mismatch).
7. The exception block catches it and emits the hardcoded UI string: `"❌ **خطأ في النظام:** لم نتمكن من بدء المهمة (Dispatch Failed)."`.

**Scenario B (Orchestrator Payload Miss):**
1. Gateway successfully proxies to `orchestrator-service` (`microservices/orchestrator_service/src/api/routes.py`).
2. The UI sends `mission_type` in a format the route does not expect (e.g., UI sends `metadata: { mission_type: ... }` but backend expects root, or vice versa, though the modern backend attempts to check both).
3. If the condition `isinstance(metadata, dict) and metadata.get("mission_type") == "mission_complex" or mission_type == "mission_complex"` evaluates to False (e.g. malformed JSON or nested differently by UI), the orchestrator silently falls back to `_run_chat_langgraph(objective, {})` (ordinary chat) instead of `handle_mission_complex_stream`.
4. The mission is executed as an ordinary chat, causing a mismatch between the user's intent (Super Agent) and the execution reality.

## 5. EXACT DIVERGENCE POINT
The exact divergence point occurs at the parsing of the `mission_type` intent.
- **In Monolith (`app/api/routers/admin.py` & `customer_chat.py`):**
  ```python
  mission_type = payload.get("mission_type")
  metadata = {}
  if mission_type:
      metadata["mission_type"] = mission_type
  ```
  This creates a `ChatDispatchRequest` which explicitly triggers `MissionComplexHandler`.
- **In Orchestrator (`microservices/orchestrator_service/src/api/routes.py`):**
  ```python
  metadata = incoming.get("metadata", {})
  mission_type = incoming.get("mission_type")
  if (isinstance(metadata, dict) and metadata.get("mission_type") == "mission_complex") or mission_type == "mission_complex":
      async for chunk in handle_mission_complex_stream...
  ```
  If this logic is bypassed, ordinary chat takes over.

## 6. PERSISTENCE VS UI TRUTH MISMATCH
- **The Mismatch:** The UI displays a Super Agent failure ("Dispatch Failed" or generic error), but the database persists the conversation as an ordinary chat, or drops the mission intent entirely.
- **Why:** When `MissionComplexHandler` fails and emits the "Dispatch Failed" string, the initial user question has already been persisted to the conversation history by the `ChatBoundaryService` (which happens prior to dispatcher execution). The assistant's error message may or may not be appended to the same history, but the `Conversation` entity never receives the `mission_id` association because the mission was never created successfully in the remote `orchestrator-service`. Thus, the DB reflects an ordinary chat with an error, while the UI requested a Super Agent mission.

## 7. REQUEST CONTRACT ANALYSIS
- **Monolith Expectation:** UI sends `mission_type` at the root. The monolith router moves it into `metadata` for the `ChatDispatchRequest`.
- **Orchestrator Expectation:** `routes.py` explicitly checks *both* the root `mission_type` and `metadata.get("mission_type")`.
- **The Break:** If the UI wraps the payload in an unexpected envelope, or if the API Gateway's `conversation-service` canary (`_response_envelope`) intercepts the WS stream, the `mission_type` contract is shattered, and the orchestrator never sees the complex intent.

## 8. WEBSOCKET EVENT ANALYSIS
- **Monolith:** Emits `{"type": "status", ...}` and `{"type": "assistant_error", "payload": {"content": "❌ ... (Dispatch Failed)."}}`.
- **Orchestrator `handle_mission_complex_stream`:** Emits strict NDJSON strings (`RUN_STARTED`, `PHASE_STARTED`, `assistant_delta`, `assistant_final`) formatted via `_json_event` in `microservices/orchestrator_service/src/services/overmind/utils/mission_complex.py`.
- **Inconsistency:** The UI FSM expects the structured `RUN_STARTED` events from the microservice. When the monolith intercepts and fails, it emits an `assistant_error` directly, breaking the UI's mission state machine and leaving it hanging or showing the "Dispatch Failed" text.

## 9. ROOT CAUSE CLASSIFICATION
**PERSISTENCE / EXECUTION SPLIT-BRAIN**
(With secondary factors of MISSION DISPATCH CONTRACT DRIFT).

## 10. RANKED CAUSAL HYPOTHESES
1. **Split-Brain Execution (Highest Confidence):** Traffic is still hitting the legacy monolith WS endpoints (`app/api/routers/admin.py`), triggering the deprecated `MissionComplexHandler`, which hard-fails on the `orchestrator_client` HTTP bridge.
2. **WebSocket Event Contract Mismatch (High Confidence):** The UI expects `RUN_STARTED` events from the modern orchestrator, but receives raw `assistant_error` JSON payloads from the monolith.
3. **Mission Dispatch Contract Drift (Medium Confidence):** Canary routing to `conversation-service` drops the `mission_type` entirely, acting as an echo chamber.

## 11. HIGHEST-CONFIDENCE ROOT CAUSE
The highest-confidence root cause is **PERSISTENCE / EXECUTION SPLIT-BRAIN**. Despite the API Gateway's existence, local dev or specific client connections are still routing to the Monolith's legacy WS endpoints (`app/api/routers/admin.py` or `customer_chat.py`). Once there, Super Agent intent is routed to `MissionComplexHandler` (`app/services/chat/handlers/strategy_handlers.py`), which attempts a synchronous HTTP bridge call to the microservice. This bridge fails, emitting the explicit `"Dispatch Failed"` string, while ordinary chat succeeds because it uses the local `DefaultChatHandler` which doesn't require the bridge.

## 12. CODE EVIDENCE INDEX
- **"Dispatch Failed" Source:** `app/services/chat/handlers/strategy_handlers.py` line ~243 inside `MissionComplexHandler.execute()`.
- **Legacy Monolith WS Route:** `app/api/routers/admin.py` (`@router.websocket("/api/chat/ws")`).
- **Modern Orchestrator WS Route:** `microservices/orchestrator_service/src/api/routes.py` (`@router.websocket("/admin/api/chat/ws")`).
- **Gateway Proxy Logic:** `microservices/api_gateway/main.py` (`_resolve_chat_ws_target`).

## 13. FILES INSPECTED
- `app/services/chat/handlers/strategy_handlers.py`
- `microservices/api_gateway/main.py`
- `microservices/api_gateway/websockets.py`
- `microservices/orchestrator_service/src/api/routes.py`
- `microservices/orchestrator_service/src/services/overmind/utils/mission_complex.py`
- `app/api/routers/admin.py`
- `app/api/routers/customer_chat.py`
- `microservices/conversation_service/main.py`

## 14. MINIMAL SAFE FIX BOUNDARY
The minimal safe fix boundary requires:
1. Deleting the legacy WebSocket endpoints (`@router.websocket("/api/chat/ws")` and `@router.websocket("/ws")`) from `app/api/routers/admin.py` and `app/api/routers/customer_chat.py` to physically prevent the monolith from intercepting WS traffic.
2. Deleting or disabling `MissionComplexHandler` in `app/services/chat/handlers/strategy_handlers.py` to ensure the "Dispatch Failed" bridge path is unreachable.
3. Ensuring the UI connects strictly to the API Gateway port to leverage `microservices/orchestrator_service/src/api/routes.py` natively.