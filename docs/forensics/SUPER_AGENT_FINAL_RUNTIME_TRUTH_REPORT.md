# SUPER AGENT FINAL RUNTIME TRUTH REPORT

## 1. Executive Summary

*   **CONFIRMED:** The API Gateway natively and exclusively routes `/api/chat/ws` and `/admin/api/chat/ws` to `orchestrator-service` via WebSocket proxy (`microservices/api_gateway/main.py`). The legacy monolith fallback is completely removed from the API Gateway code.
*   **CONFIRMED:** "Dispatch Failed" originates exclusively from the Monolith (`MissionComplexHandler`), triggered only when local clients bypass the API Gateway or tests mock the legacy path.
*   **CONFIRMED:** `orchestrator-service` uses `_is_mission_complex` to fork execution. Ordinary chat uses `_run_chat_langgraph` (returning a single JSON dictionary). Super Agent uses `_stream_mission_complex_events` (yielding multiple NDJSON/WebSocket delta events).
*   **CONFIRMED:** The Super Agent path in `orchestrator-service` explicitly persists the assistant message (`_persist_assistant_message`) and the user message (`_ensure_conversation`).
*   **HIGH-CONFIDENCE:** Ordinary chat in `orchestrator-service` (`_run_chat_langgraph`) does **not** persist the conversation or messages to the SQL database. It relies entirely on LangGraph's internal state mechanism, leading to a persistence split-brain.
*   **HIGH-CONFIDENCE:** The UI expects a streaming delta contract (`assistant_delta`, `RUN_STARTED`), but ordinary chat returns a single `{"status": "ok", "response": ...}` block. The UI either handles this gracefully for ordinary chat, or ordinary chat works by accident.
*   **REMAINING AMBIGUITY:** Why does ordinary chat appear to have persistent history in the UI if `_run_chat_langgraph` does not write to the `customer_conversations` / `admin_conversations` tables? Do HTTP endpoints like `/api/chat/conversations` (which still point to Monolith in some configurations, or route to Orchestrator HTTP endpoints) fetch from a database that isn't updated by the modern WS path?
*   **REMAINING AMBIGUITY:** Does the UI correctly parse the Super Agent events emitted by `handle_mission_complex_stream`, or does the stream terminate prematurely without matching the exact `assistant_final` expectation?

## 2. Confirmed Live Control-Plane Truth

*   **Admin Ordinary Chat:** `API Gateway (/admin/api/chat/ws)` -> `orchestrator-service (admin_chat_ws_stategraph)` -> `_run_chat_langgraph()`.
*   **Customer Ordinary Chat:** `API Gateway (/api/chat/ws)` -> `orchestrator-service (chat_ws_stategraph)` -> `_run_chat_langgraph()`.
*   **Admin Super Agent:** `API Gateway (/admin/api/chat/ws)` -> `orchestrator-service (admin_chat_ws_stategraph)` -> `_stream_mission_complex_events()` -> `handle_mission_complex_stream()`.
*   **Customer Super Agent:** `API Gateway (/api/chat/ws)` -> `orchestrator-service (chat_ws_stategraph)` -> `_stream_mission_complex_events()` -> `handle_mission_complex_stream()`.
*   **First Divergence Point:** Inside `microservices/orchestrator_service/src/api/routes.py`, within the `chat_ws_stategraph` and `admin_chat_ws_stategraph` functions: `if _is_mission_complex(incoming):`.

## 3. Confirmed Persistence Ownership Truth

*   **Conversation Creation (Super Agent):** Owned by `_ensure_conversation` in `orchestrator-service/src/api/routes.py`. It explicitly inserts into `admin_conversations` / `customer_conversations`.
*   **User-Message Save (Super Agent):** Owned by `_ensure_conversation` in `orchestrator-service/src/api/routes.py`.
*   **Assistant-Message Save (Super Agent):** Owned by `_persist_assistant_message` in `orchestrator-service/src/api/routes.py`.
*   **Assistant-Error Save (Super Agent):** Handled inline as WebSocket events (`"type": "assistant_error"`); the final error content is optionally persisted via `_persist_assistant_message` if stream breaks.
*   **Mission Linkage (Super Agent):** Owned by `_persist_assistant_message` via `UPDATE admin_conversations SET linked_mission_id=:mission_id`.
*   **Persistence Ownership Truth (Ordinary Chat):** **FALSE CONFIDENCE / UNPROVEN ASSUMPTION**. `_run_chat_langgraph` does not call `_ensure_conversation` or `_persist_assistant_message`. Unless LangGraph implicitly writes to SQLModel tables, ordinary chat persistence is broken or happening asynchronously out-of-band.

## 4. WebSocket Event Contract Reality

*   **Ordinary Chat Event Format:** Emits exactly one un-streamed JSON object per message via `websocket.send_json(result)`. The payload is `{"status": "ok", "response": "<text>", "run_id": "...", "timeline": [...]}`.
*   **Super Agent Event Format:** Emits multiple streaming JSON objects via `websocket.send_json(event)`. Events include `{"type": "conversation_init", ...}`, `{"type": "RUN_STARTED", ...}`, `{"type": "assistant_delta", ...}`, `{"type": "assistant_final", ...}`.
*   **Exact Mismatch:** Ordinary chat does not use `"type"` or `"payload"` schema. Super Agent strictly uses the Canonical Event FSM schema (`type`/`payload`). If the UI shares one state machine for both, it is impossible for both to succeed seamlessly without a massive shim on the frontend.

## 5. Mission Dispatch Contract Reality

*   **Exact Root Payload Truth:** `_is_mission_complex` accepts `mission_type` at the root of the incoming WebSocket JSON.
*   **Exact Metadata Payload Truth:** `_is_mission_complex` also accepts `mission_type` nested inside a `metadata` dictionary. Both are valid.
*   **Exact "conversation_id" Truth:** Super Agent extracts `conversation_id` from the root payload. If missing, it creates a new one via `_ensure_conversation`. Inside `handle_mission_complex_stream()`, the `conversation_id` is passed inside the context.
*   **Exact Fallback Truth:** If `_is_mission_complex` evaluates to `False` (due to missing or misspelled `mission_type`), the request falls back silently to `_run_chat_langgraph` (ordinary chat).
*   **Exact Mission-Complex Routing Truth:** Live WS traffic definitively reaches `_stream_mission_complex_events` if the payload is correct, because the Gateway strictly proxies WS traffic to Orchestrator.

## 6. Failure Surface Map

*   **"Dispatch Failed"**
    *   **Source:** `app/services/chat/handlers/strategy_handlers.py` (`MissionComplexHandler.execute()`).
    *   **Trigger Condition:** HTTP bridge `orchestrator_client.create_mission()` fails.
    *   **Owner:** Legacy Monolith. (This implies connections hitting this error are bypassing the API Gateway or local dev environments are misconfigured).
*   **"No response received from AI service"**
    *   **Source:** `app/services/admin/chat_streamer.py` and `app/services/customer/chat_streamer.py`.
    *   **Trigger Condition:** AI stream completes without yielding chunks.
    *   **Owner:** Legacy Monolith boundary services.
*   **Empty-stream / Hanged UI**
    *   **Source:** `orchestrator-service` (`_stream_mission_complex_events`).
    *   **Trigger Condition:** If the `handle_mission_complex_stream` yields no terminal events (`assistant_final`), the frontend state machine hangs waiting for it.
    *   **Owner:** Modern Orchestrator.
*   **"assistant_error"**
    *   **Source:** `orchestrator-service` (`microservices/orchestrator_service/src/services/overmind/utils/mission_complex.py`).
    *   **Trigger Condition:** Event bus timeout, or mission system failure (e.g., `mission_failed` event from Redis).
    *   **Owner:** Modern Orchestrator.

## 7. Legacy Residual Risk Classification

*   **Monolith websocket endpoints (`app/api/routers/admin.py` & `customer_chat.py`):** DORMANT BUT REACHABLE. They still exist in code, but API Gateway does not route to them. Local UI devs hitting port 8000 directly will hit them.
*   **"MissionComplexHandler":** DORMANT BUT REACHABLE. Executed only if monolith WS endpoints are hit.
*   **Old orchestrator bridge clients (`orchestrator_client.py`):** CONFIRMED ACTIVE RISK. Used by `MissionComplexHandler` and potentially other HTTP endpoints.
*   **Old persistence owners (`AdminChatBoundaryService`, `CustomerChatBoundaryService`):** CONFIRMED ACTIVE RISK. Legacy HTTP endpoints (`/api/chat/conversations` via `chat_http_proxy` in gateway pointing to Orchestrator? No, Gateway points `/api/chat/{path}` HTTP to Orchestrator, but Orchestrator's `chat_messages_endpoint` might not be compatible. Wait, if API Gateway points `/api/conversations` to Monolith or Orchestrator?). The HTTP persistence read paths are highly risky.

## 8. Test Evidence vs Runtime Evidence

*   **Proves ordinary chat works:** `tests/integration/test_unified_control_plane.py` (assumed based on name) likely proves basic chat flow, but tests mocking `_run_chat_langgraph` or database sessions obscure the lack of persistence.
*   **Proves persistence works:** Legacy tests test `ChatBoundaryService`, providing FALSE CONFIDENCE because that service is bypassed by the live API Gateway WS path.
*   **Proves Super Agent routing works:** `test_mission_complex_stream.py` strictly tests `handle_mission_complex_stream` logic, proving the microservice logic is sound *if reached*.
*   **Unproven / False Confidence:** Any test that asserts ordinary chat persistence using the monolith DB session, because the live WS path (`_run_chat_langgraph`) does not appear to execute SQL queries to save messages.

## 9. Highest-Confidence Root Cause

**ROOT CAUSE HIGH-CONFIDENCE BUT NOT FULLY PROVEN:**
The "Super Agent Failure" observed in the live environment is actually two distinct phenomena mixed together:
1.  **Local/Bypass Connections (The "Dispatch Failed" error):** Developers or UI instances connecting directly to the Monolith (Port 8000) trigger `MissionComplexHandler`, which hard-fails because the internal network bridge is disabled.
2.  **Live/Proxy Connections (The UI State Machine Hang):** Connections passing through the API Gateway correctly reach `orchestrator-service`. However, the Super Agent emits Canonical Event FSM payloads (`RUN_STARTED`, `assistant_delta`), while ordinary chat has trained the UI to accept a massive un-streamed JSON blob (`status: ok, response: ...`). The UI fails to process the Super Agent stream, resulting in a silent failure or hanging state, despite the backend successfully dispatching the mission.

## 10. Remaining Unknowns

1.  **Ordinary Chat Persistence Mystery:** If `_run_chat_langgraph` doesn't write to `customer_conversations` / `admin_messages`, where does the UI read chat history from upon page refresh? Does LangGraph natively persist to the SQL DB, or is ordinary chat history completely broken in production?
2.  **HTTP Read Path Routing:** Where do `/api/conversations` GET requests actually go? The API Gateway `chat_http_proxy` proxies `/api/chat/{path}` to Orchestrator, but `app/api/routers/admin.py` defines `/api/conversations`. Are read requests still hitting the monolith while write requests hit Orchestrator?
3.  **UI Event Consumption Reality:** What exactly does the frontend code expect from the WS? If it expects the `assistant_delta` schema, why does the ordinary chat schema (`{status: ok, response: ...}`) render successfully?

## 11. Most Dangerous Unknown

**The Disconnect Between Ordinary Chat Execution and Database Persistence.**
If we modify Super Agent persistence to "match" ordinary chat, we might be matching a completely broken or ephemeral state mechanism. If ordinary chat history is currently broken in live production (because it bypasses `ChatBoundaryService` and `_run_chat_langgraph` saves nothing), then any architectural repair based on the assumption that "ordinary chat works perfectly" will fundamentally corrupt the user experience and database integrity.

## 12. Final Conclusion

We now know with absolute confidence that the live API Gateway strictly isolates WebSocket traffic to the `orchestrator-service`, effectively deprecating the Monolith's WS endpoints and its hardcoded `"Dispatch Failed"` error. The execution paths for ordinary chat and Super Agent diverge natively inside `orchestrator-service`. However, before any final repair strategy is safe, we must prove exactly how ordinary chat persists its history (if at all) under `_run_chat_langgraph`, and we must reconcile the violently conflicting WebSocket event schemas (monolithic JSON vs. streamed canonical events) that the UI is currently being forced to consume.
