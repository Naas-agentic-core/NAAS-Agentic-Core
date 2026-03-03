# SUPER AGENT FINAL RUNTIME TRUTH REPORT

## 1. Executive Summary

* **CONFIRMED:** The API Gateway intelligently routes `/api/chat/ws` and `/admin/api/chat/ws` natively to the `orchestrator-service` via a modern websocket proxy.
* **CONFIRMED:** Ordinary chat and Super Agent share the exact same WebSocket endpoint (`/api/chat/ws` and `/admin/api/chat/ws`) on the `orchestrator-service`.
* **CONFIRMED:** The divergence between ordinary chat and Super Agent happens deep inside `orchestrator-service/src/api/routes.py` based on the payload containing `mission_type == "mission_complex"`.
* **CONFIRMED:** Super Agent uses `handle_mission_complex_stream` which yields raw JSON string chunks sent via `websocket.send_text()`, whereas ordinary chat uses `_run_chat_langgraph` which sends a serialized JSON dict via `websocket.send_json()`.
* **HIGH-CONFIDENCE:** Super Agent failure ("Dispatch Failed" or generic UI error) is caused by a protocol mismatch: the UI expects `send_json` (parsed objects) like ordinary chat, but Super Agent streams raw NDJSON strings (`send_text()`).
* **HIGH-CONFIDENCE:** The legacy monolith routing is a "safe residual" and not in the live path for websocket chat traffic due to 0% rollout configuration and direct gateway routing.
* **UNKNOWN/UNPROVEN ASSUMPTION:** It is falsely assumed that the Super Agent mission is properly linked to a user's `Conversation` in persistence. Our trace of `handle_mission_complex_stream` shows it spins up a `start_mission` with no `conversation_id` linkage and does not invoke `CustomerChatPersistence` to save user or assistant messages.
* **REMAINING AMBIGUITY:** Tests that "prove" persistence for Super Agent are likely mocking the intent dispatcher, meaning they do not reflect the modern microservice runtime where `orchestrator-service` handles the execution independently of the monolith's conversation tables.

## 2. Confirmed Live Control-Plane Truth

* **Admin Ordinary Chat:**
  * Client connects to `/admin/api/chat/ws`.
  * API Gateway `microservices/api_gateway/main.py::admin_chat_ws_proxy` receives the request.
  * API Gateway resolves target via `_resolve_chat_ws_target`. With 0% rollout to Conversation Service, target is `ws://orchestrator-service:8006/admin/api/chat/ws`.
  * Traffic reaches `microservices/orchestrator_service/src/api/routes.py::admin_chat_ws_stategraph`.
  * Without `mission_complex` payload, it delegates to `_run_chat_langgraph` which yields an object via `websocket.send_json(result)`.
* **Customer Ordinary Chat:**
  * Client connects to `/api/chat/ws`.
  * API Gateway `microservices/api_gateway/main.py::chat_ws_proxy` receives the request.
  * API Gateway resolves target to `ws://orchestrator-service:8006/api/chat/ws`.
  * Traffic reaches `microservices/orchestrator_service/src/api/routes.py::chat_ws_stategraph`.
  * Without `mission_complex` payload, it delegates to `_run_chat_langgraph` which yields an object via `websocket.send_json(result)`.
* **Admin Super Agent:**
  * Same ingress as Admin Ordinary Chat up to `admin_chat_ws_stategraph`.
  * Payload dictates divergence. If `mission_type == "mission_complex"`, execution routes to `handle_mission_complex_stream`.
* **Customer Super Agent:**
  * Same ingress as Customer Ordinary Chat up to `chat_ws_stategraph`.
  * Payload dictates divergence. If `mission_type == "mission_complex"`, execution routes to `handle_mission_complex_stream`.

**Exact First Divergence Point:**
The active path is TRULY **API Gateway -> orchestrator-service**. The divergence occurs strictly within `microservices/orchestrator_service/src/api/routes.py` at line ~148/194:
```python
            if (
                isinstance(metadata, dict) and metadata.get("mission_type") == "mission_complex"
            ) or mission_type == "mission_complex":
                async for chunk in handle_mission_complex_stream(objective, {}, user_id=user_id):
                    await websocket.send_text(chunk)
                continue
```

## 3. Confirmed Persistence Ownership Truth

* **Ordinary Chat:**
  * **Conversation Creation:** **UNKNOWN** natively in `orchestrator-service` websocket logic. `microservices/orchestrator_service/src/api/routes.py` `_run_chat_langgraph` receives `objective` and `context` but contains zero explicit calls to any persistence logic (`save_message`, `get_or_create_conversation`).
  * **User Message Save:** **UNKNOWN** via modern path.
  * **Assistant Message Save:** **UNKNOWN** via modern path.
  * **Assistant Error Save:** **UNKNOWN** via modern path.
  * *Note:* The Monolith handles persistence nicely in `app/services/boundaries/customer_chat_boundary_service.py` (`save_message`, `get_or_create_conversation`), but the live websocket traffic **bypasses the monolith entirely** based on API Gateway `_resolve_chat_ws_target`.

* **Super Agent:**
  * **Conversation Creation:** **UNKNOWN** for the chat representation.
  * **Mission Linkage:** `handle_mission_complex_stream` triggers `start_mission(session, objective, initiator_id, context, ...)`. The context dict receives `{"chat_context": True, **context}` but *crucially lacks any explicit `conversation_id` parameter*.
  * **User/Assistant Message Save:** **UNPROVEN ASSUMPTION / MISSING.** `handle_mission_complex_stream` generates strings to stream, but does not interact with any `CustomerConversation` or `CustomerMessage` persistence models. The UI reads from `/api/chat/latest` or `/api/conversations/X` which query the `CustomerConversation` tables. If the modern runtime doesn't write to these tables, the UI won't see the Super Agent history.

**Verdict:** Ordinary chat persistence ownership is ambiguously handled if we strictly look at the websocket path (`api_gateway` -> `orchestrator-service`). If the UI queries history, it queries the monolith APIs (`/api/chat/latest`), but the monolith endpoints for writing are bypassed.

## 4. WebSocket Event Contract Reality

* **Ordinary Chat Format:**
  * Uses `await websocket.send_json(result)` in `_run_chat_langgraph`.
  * Format:
    ```json
    {
        "status": "ok",
        "response": "<text>",
        "run_id": "<uuid>",
        "timeline": [...],
        "graph_mode": "stategraph",
        "route_id": "chat_ws_customer"
    }
    ```

* **Super Agent Format:**
  * Uses `await websocket.send_text(chunk)` inside `handle_mission_complex_stream`.
  * The `chunk` is a pre-serialized JSON string (NDJSON format because it ends with `\n` via `_json_event` helper).
  * Format:
    ```json
    {"type": "assistant_delta", "payload": {"content": "..."}}
    ```
    ```json
    {"type": "RUN_STARTED", "payload": {...}}
    ```

* **Contract Mismatch (HIGH-CONFIDENCE):**
  * The frontend UI may break if it expects a parsed JSON object (as emitted by ordinary chat `send_json()`) but receives a raw string chunk (`send_text()`) for Super Agent. The UI state machine would attempt to read `msg.type` on a string, resulting in undefined or error states.
  * Ordinary chat success and Super Agent failure are directly tied to these two distinct protocols (`stategraph dict` vs `NDJSON chunks`) being consumed by one UI.

## 5. Mission Dispatch Contract Reality

* **Root Payload Truth:** The WebSocket endpoint expects `mission_type` in the root payload OR inside the `metadata` object of the incoming JSON.
* **Metadata Payload Truth:** Handled equivalently. `metadata.get("mission_type") == "mission_complex"` or `mission_type == "mission_complex"`.
* **"conversation_id" Truth:** The `conversation_id` is parsed out (or ignored entirely) in `microservices/orchestrator_service/src/api/routes.py` `chat_ws_stategraph`. The `handle_mission_complex_stream(objective, {}, user_id=user_id)` signature explicitly drops `conversation_id`, passing an empty `{}` as context. Therefore, **CONFIRMED** `conversation_id` is silently dropped in the true runtime path.
* **Fallback Truth:** If `mission_type` is omitted or malformed, it silently falls through the `if` block and runs `_run_chat_langgraph(objective, {})`. This causes an ordinary chat response instead of a Super Agent dispatch.
* **Mission-Complex Routing Truth:** It is truly hit in the live path due to `API Gateway` routing correctly, but its internal behavior (NDJSON, dropping `conversation_id`) causes the subsequent failures in UI or persistence.

## 6. Failure Surface Map

* **"Dispatch Failed"**
  * **Source:** `handle_mission_complex_stream` in `microservices/orchestrator_service/src/services/overmind/utils/mission_complex.py` (line 125-131, exception handler during DB `start_mission`). Or `app/services/chat/handlers/strategy_handlers.py` in the legacy monolith `MissionComplexHandler.execute` (line 170).
  * **Condition:** Exception during `start_mission` (e.g. `start_mission` in monolith attempting to reach disabled `orchestrator_client`, OR DB session rollback/locking issue in microservice). In our mapped path, it's either a DB/Redis lock issue or a UI interpreting an NDJSON string error.
  * **Owner:** `orchestrator-service` (live path) OR `Monolith` (if routed there by proxy mismatch/test).

* **"No response received from AI service" / Empty-stream behavior**
  * **Source:** Frontend UI expectation.
  * **Condition:** UI sends `mission_complex`, receives `send_text` (raw string chunks instead of parsed JSON), causing the WS message handler in the browser to throw or ignore the unparseable structure `JSON.parse` if it expects an object directly. Or, the stream opens, yields `assistant_delta` string, and UI drops it because it isn't `msg.type === 'assistant_delta'`.
  * **Owner:** Frontend vs Orchestrator mismatch.

* **"assistant_error"**
  * **Source:** `microservices/orchestrator_service/src/services/overmind/utils/mission_complex.py` (lines 115, 126).
  * **Condition:** Yielded as NDJSON string `{"type": "assistant_error", ...}` when `mission_failed` event is caught, or when `start_mission` throws.
  * **Owner:** `orchestrator-service`.

* **Generic/Unknown UI Failure State (History Missing)**
  * **Source:** Frontend UI refresh.
  * **Condition:** User refreshes page, UI calls `/api/chat/latest`, which queries the `CustomerConversation` DB. Because `orchestrator-service`'s `handle_mission_complex_stream` dropped the `conversation_id` and never saved the message to the DB, the UI history loads empty (or missing the Super Agent execution).
  * **Owner:** `orchestrator-service` bypassing persistence.

## 7. Legacy Residual Risk Classification

* **Monolith WebSocket Endpoints (`app/api/routers/admin.py` & `app/api/routers/customer_chat.py`):** **SAFE RESIDUAL**. The API Gateway's `ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT` defaults to `0`, causing the `_resolve_chat_ws_target` to hardcode routing to `settings.ORCHESTRATOR_SERVICE_URL`. The monolith WS endpoints are never hit.
* **`MissionComplexHandler` (`app/services/chat/handlers/strategy_handlers.py`):** **DORMANT BUT REACHABLE**. If tests or a legacy fallback somehow route traffic to the monolith's `ChatOrchestrator`, this handler will trigger the `app/services/overmind/entrypoint.py` proxy to `orchestrator_client`, causing possible confusion or double-dispatch.
* **Old Orchestrator Bridge Clients (`app/infrastructure/clients/orchestrator_client.py`):** **DORMANT BUT REACHABLE**. Only used by the Monolith's `MissionComplexHandler`.
* **Old Persistence Owners (`CustomerChatBoundaryService`, `AdminChatBoundaryService`):** **UNKNOWN**. They are NOT used by the modern `orchestrator-service` websocket path, but they ARE still queried by the UI (`/api/chat/latest`, `/api/conversations`). This creates a fatal split-brain in persistence: the UI reads from the Monolith, but the WS runtime (Orchestrator Service) writes nowhere (or only to its local state).
* **Dormant Handlers (Strategy pattern `FileRead`, `CodeSearch` in `app`):** **SAFE RESIDUAL**. Unless legacy monolith chat endpoints are accessed, they will not execute.

## 8. Test Evidence vs Runtime Evidence

* **Tests Proving Ordinary Chat:** The `chat_ws_stategraph` in `microservices/orchestrator_service` receives `_run_chat_langgraph` which yields dicts, validating the successful chat path (assuming the UI correctly consumes `send_json`).
* **Tests Proving Persistence/History Works:** Tests like `tests/api/test_customer_chat_persistence.py` run against the Monolith (`app/api/routers/customer_chat.py`), creating a `ChatOrchestrator` instance and confirming it calls `save_message`. **This is FALSE CONFIDENCE.** The live API Gateway bypasses `app/api/routers/customer_chat.py` completely and routes WS traffic to `orchestrator-service` which lacks `save_message`.
* **Tests Proving Super Agent Routing:** Tests validating Gateway routing prove traffic goes to `orchestrator-service`.
* **Tests Not Proving Super Agent Success:** No test proves that the UI successfully parses the raw NDJSON strings (`send_text()`) emitted by `handle_mission_complex_stream`. Tests only assert that the string is emitted.
* **Legacy Persistence Tests:** Tests mocking the dispatcher in `app/services/boundaries/` create false confidence that persistence works for all traffic. The live runtime bypasses these boundaries for WS execution.

## 9. Highest-Confidence Root Cause

The root cause of the Super Agent failure while ordinary chat succeeds is a **simultaneous Protocol & Persistence Split-Brain inside the `orchestrator-service`**:

1. **Protocol Mismatch:** Ordinary chat emits serialized JSON objects (`send_json()`) containing `status`, `response`, `run_id`, etc. Super Agent (`handle_mission_complex_stream`) streams raw NDJSON string chunks (`send_text()`) expecting the UI to parse them individually. The UI state machine breaks when attempting to parse the disparate formats from the same `ws` endpoint.
2. **Persistence Bypass:** Ordinary chat history functions because the legacy monolith boundaries (`CustomerChatBoundaryService`) originally saved the messages. However, the current live API Gateway natively routes ALL WS traffic to `orchestrator-service`. The `orchestrator-service` `handle_mission_complex_stream` explicitly ignores `conversation_id` and does not persist messages to the `CustomerConversation` or `CustomerMessage` tables, resulting in empty history queries (`/api/chat/latest`) on the UI.

## 10. Remaining Unknowns

1. **How does the frontend parse WS events?**
   * *Missing:* We lack visibility into the React/JS frontend code consuming the WebSocket stream.
   * *Why insufficient evidence:* Without knowing if the frontend uses `JSON.parse(event.data)` or conditionally parses based on string matching, we can only infer it breaks on `send_text()` instead of `send_json()`.

2. **Is ordinary chat currently saving to `CustomerMessage`?**
   * *Missing:* The `_run_chat_langgraph` implementation in `microservices/orchestrator_service/src/api/routes.py` contains no `CustomerMessage` persistence.
   * *Why insufficient evidence:* If ordinary chat history truly works in production *right now*, either the `CustomerChatBoundaryService` is still processing it (which contradicts Gateway routing configuration) or another hidden event listener is saving it asynchronously.

## 11. Most Dangerous Unknown

* **Does the `orchestrator-service` websocket path (`_run_chat_langgraph`) actually save user/assistant history anywhere right now?**
  * *Why it is dangerous:* If we mistakenly "fix" Super Agent by converting `send_text` to `send_json`, the UI might render properly *in the moment*, but history will silently disappear for both ordinary chat and Super Agent. If we assume the Monolith still saves history (because the `CustomerChatBoundaryService` tests pass), we will deploy a broken split-brain to production where the Gateway routes chat execution to the microservice but the UI expects history from a bypassed monolith endpoint.
  * *False decision:* Refactoring the Super Agent JSON payload without fixing the fatal persistence decoupling.

## 12. Final Conclusion

We confidently know that the modern API Gateway routes all chat traffic to `orchestrator-service`, causing Super Agent and ordinary chat to share the identical WebSocket endpoint but diverge internally based on payload. We confidently know a JSON string versus JSON object mismatch exists (`send_text` vs `send_json`). We confidently know Super Agent execution drops `conversation_id`. However, we must concretely prove *how (and if)* ordinary chat persists messages in the new `_run_chat_langgraph` microservice path before safely implementing any final repair; otherwise, fixing the JSON stream will still leave the UI history entirely blank due to the `CustomerConversation` persistence bypass.
