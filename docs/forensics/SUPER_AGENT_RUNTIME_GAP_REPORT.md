# SUPER AGENT RUNTIME GAP REPORT

## 1. Executive Summary

- **CONFIRMED:** Ordinary chat and Super Agent routes both land on `orchestrator-service` via API Gateway websocket proxies (`microservices/api_gateway/main.py`), completely bypassing the legacy monolith handlers (`app/api/routers/customer_chat.py`).
- **CONFIRMED:** The Super Agent route in `orchestrator-service` uses `handle_mission_complex_stream`, which yields naked JSON strings via `websocket.send_text()`, whereas ordinary chat uses `_run_chat_langgraph` and sends serialized objects via `websocket.send_json()`.
- **UNKNOWN:** Why persistence and history "now work" for ordinary chat, given that `chat_ws_stategraph` in `microservices/orchestrator_service/src/api/routes.py` contains zero persistence logic (no conversation creation or message saving). This contradicts the assertion that they work via the new path.
- **HIGH-CONFIDENCE:** The Super Agent UI failure is caused by a protocol mismatch. The frontend likely expects the structured `stategraph` event format emitted by `send_json()`, but `handle_mission_complex_stream` yields `send_text()` containing stringified JSON events representing `RUN_STARTED` and other `stategraph` canonical payloads.
- **UNKNOWN (Most Dangerous):** The exact component responsible for persistence on the modern WS path is missing from `orchestrator-service` code entirely. If ordinary chat persistence truly works, it must be intercepted or handled by another unexamined component, or the UI is using an HTTP fallback instead of the WebSocket.

## 2. Confirmed Runtime Truth

- **Exact current ordinary chat path:**
  `client` → `api_gateway` (`chat_ws_customer` proxy) → `orchestrator-service` (`/api/chat/ws`) → `chat_ws_stategraph` → `_run_chat_langgraph` → `websocket.send_json(result)`.
- **Exact current Super Agent path:**
  `client` → `api_gateway` (`chat_ws_customer` proxy) → `orchestrator-service` (`/api/chat/ws`) → `chat_ws_stategraph` → `handle_mission_complex_stream` → `websocket.send_text(chunk)`.
- **Exact divergence point:**
  In `microservices/orchestrator_service/src/api/routes.py` inside `chat_ws_stategraph` and `admin_chat_ws_stategraph` at line 151:
  ```python
  if (isinstance(metadata, dict) and metadata.get("mission_type") == "mission_complex") or mission_type == "mission_complex":
      async for chunk in handle_mission_complex_stream(...):
          await websocket.send_text(chunk)
  ```

## 3. Confirmed Persistence Truth

- **Who creates conversation:** `CustomerChatBoundaryService.get_or_create_conversation` via `CustomerChatPersistence` in the legacy monolith (`app/services/customer/chat_persistence.py`).
- **Who saves user message:** The legacy persistence layer (`CustomerChatBoundaryService`), but ONLY if the monolith WS routes are hit.
- **Who saves assistant message:** `CustomerChatStreamer._persist_response` in the legacy monolith.
- **Where mission linkage breaks or disappears:** The modern `orchestrator-service` routes (`chat_ws_stategraph`) **completely ignore** `conversation_id` from the payload and have no persistence code. If persistence is working, the UI must be using HTTP endpoints (not the WS) for history, and either falling back to legacy HTTP chat, or there is an unknown asynchronous persistence worker reading Redis events.

## 4. Confirmed Failure Surface Map

- **"Dispatch Failed" / 500 status code:**
  - *Source:* `app/api/routers/admin.py` or `app/api/routers/customer_chat.py`.
  - *Condition:* If traffic mistakenly hits the monolith, `orchestrator_client.create_mission()` is called. If the orchestrator HTTP bridge fails, the monolith emits this error.
- **"No response received from AI service" / "Unknown error":**
  - *Source:* `app/services/customer/chat_streamer.py`.
  - *Condition:* If `orchestrator.process()` throws an exception during fallback stream.
- **Timeout / empty-stream behavior:**
  - *Source:* Client-side / UI.
  - *Condition:* UI receives `send_text()` stringified chunks from `handle_mission_complex_stream` but expects `send_json()` objects like the `stategraph` result.
- **Assistant Error (`assistant_error`):**
  - *Source:* `microservices/orchestrator_service/src/services/overmind/utils/mission_complex.py`.
  - *Condition:* Emitted when `event_type == "mission_failed"` or an exception occurs in the stream.

## 5. Mission Contract Reality

- **Root payload:** `mission_type` is checked at the root (`payload.get("mission_type")`).
- **Metadata payload:** `mission_type` is also valid inside metadata (`metadata.get("mission_type")`).
- **Conversation ID handling:** The `orchestrator-service` WS endpoint (`chat_ws_stategraph`) accepts `conversation_id` in the `ChatRequest` model but completely drops it during `_extract_chat_objective` and never passes it to LangGraph or `handle_mission_complex_stream`.
- **Normalization truth:** The UI may send `{ "objective": "..." }` or `{ "question": "..." }`. Both are normalized to `objective` via `_extract_chat_objective()`.
- **Fallback truth:** If `mission_type` is not exactly `"mission_complex"`, the orchestrator immediately falls back to `_run_chat_langgraph` (ordinary chat).

## 6. WebSocket Event Contract Reality

- **Ordinary chat events:** Emits a single consolidated JSON object containing `{"status": "ok", "response": "...", "run_id": "...", "timeline": [...], "graph_mode": "stategraph", "route_id": "..."}`.
- **Super-agent events:** Emits a stream of text chunks (NDJSON) containing `{"type": "assistant_delta", ...}`, `{"type": "RUN_STARTED", ...}`, and `{"type": "assistant_final", ...}`.
- **Mismatch:** The UI receives a single JSON object for ordinary chat but receives NDJSON string chunks for Super Agent. The legacy monolith (`strategy_handlers.py`) used to yield JSON dictionaries which were serialized by FastAPI's `send_json()`. The new microservice yields `json.dumps() + "\n"` via `send_text()`.

## 7. Legacy Intercept / Split-Brain Risk Classification

- **Legacy websocket endpoints (`app/api/routers/customer_chat.py` & `admin.py`):** REACHABLE but DORMANT. API Gateway proxies `/api/chat/ws` away from them.
- **`MissionComplexHandler` (`app/services/chat/handlers/strategy_handlers.py`):** REACHABLE. It exists in the monolith and will execute if the proxy fails or if accessed directly bypassing the gateway.
- **`orchestrator_client.create_mission()`:** REACHABLE. Can still execute if the monolith's `MissionComplexHandler` is triggered.
- **Overall Split-Brain Risk:** ACTIVE. The monolith still holds the persistence code (`CustomerChatPersistence`), while the orchestrator holds the execution code.

## 8. Test Evidence Map

- **Ordinary Chat:** Passing tests likely cover the `_run_chat_langgraph` response format.
- **Persistence:** Tests likely assert against the legacy monolith boundary (`app/services/boundaries/customer_chat_boundary_service.py`), creating false confidence.
- **Super Agent Routing:** Tests prove `metadata` parsing routes to `handle_mission_complex_stream`.
- **Unproven facts:** No test currently proves that `orchestrator-service`'s `chat_ws_stategraph` actually persists messages to the database.
- **False-confidence zones:** Persistence tests are mocking the dispatcher but testing the monolith, completely unaware that the live API Gateway bypasses the monolith's persistence layer entirely.

## 9. Highest-Confidence Root Cause

- **Protocol Mismatch (Serialization):** Ordinary chat works because `_run_chat_langgraph` returns a dict sent via `send_json()`. Super Agent fails because `handle_mission_complex_stream` yields strings sent via `send_text()`. The UI is likely failing to parse the NDJSON stream.
- **Persistence Disconnect:** The `orchestrator-service` has zero code to save messages in its WS endpoints. If the UI expects a `conversation_id` to link the mission history, it gets dropped silently.

## 10. Remaining Unknowns

1. **How is ordinary chat history persisting?** The microservice WS endpoint `chat_ws_stategraph` contains no database session or persistence calls. If history works in the UI, it must be using a completely different HTTP endpoint or a background redis sync that was not found in the examined files.
2. **What exactly does the UI expect for Super Agent WS events?** We know it receives NDJSON text chunks, but it's unknown if the UI strictly expects `send_json()` objects or if it expects a different set of `type` keys than `assistant_delta`.
3. **Is `conversation_id` required for UI linkage?** The orchestrator service discards `conversation_id` from the WS payload. If the UI relies on it for history rendering, this explains why the DB history looks like ordinary chat or fails to link.

## 11. Most Dangerous Unknown

- **The Phantom Persistence Mechanism:** We do not know how ordinary chat is successfully saving to the database. Since `orchestrator-service`'s WS handler drops the `conversation_id` and does not write to DB, there is an unmapped mechanism (or HTTP fallback) creating the illusion of working persistence, masking a catastrophic split-brain state.

## 12. Conclusion

We know exactly where the routing diverges, how the payload is parsed, and the distinct protocol difference between ordinary chat (`send_json`) and Super Agent (`send_text` NDJSON) in the `orchestrator-service`. We know the legacy monolith handlers are bypassed by the API Gateway. However, we still do NOT know how ordinary chat persistence is physically occurring, because the modern WebSocket code path we traced executes entirely in-memory without invoking any database persistence or conversation linkage.