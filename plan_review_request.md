# 1. EXECUTION PATH MAP
1. **Frontend / Client** calls WebSocket endpoint (`chat_ws_stategraph` / `admin_chat_ws_stategraph` in `api/routes.py`).
2. **Conversation Manager** (`_ensure_conversation` in `api/routes.py`) fetches conversation state from DB (`messages` list) but **DOES NOT return it to the route**. It syncs with the separate conversation microservice, then returns only the `conversation_id`.
3. **Route** then calls `_stream_chat_langgraph(..., objective, ...)` without history messages.
4. **_stream_chat_langgraph** injects `{"query": objective, "messages": [HumanMessage(content=objective)]}` into the graph, effectively dropping all history!
5. **Supervisor Node** in `services/overmind/graph/main.py` classifies the single query to a string-based intent (e.g. `chat` or `search`).
6. **ChatFallbackNode** handles `chat` using `dspy.Predict`.
7. **QueryAnalyzerNode** handles `search` using `dspy.Predict` but receives the `query` without the history `messages` parameter in the `await asyncio.wait_for(anyio.to_thread.run_sync(lambda: self.analyzer(raw_query=query)), ...)` call!

# 2. FORENSIC FINDINGS
- **Stateless nodes:** CONFIRMED. `_stream_chat_langgraph` receives only `objective` (the last query) and initializes `messages` list with a single `HumanMessage(content=objective)`. History loaded in `_ensure_conversation` is completely discarded.
- **Backend-owned memory:** CONFIRMED. It is handled through the DB, but dropped before Graph execution.
- **Router null-drop:** KILLED. `SupervisorNode` has default intent `"search"` or `"chat"` based on simple fallbacks.
- **Retrieval truth:** `QueryAnalyzerNode` analyzes the `raw_query` alone, completely ignoring the `messages` history. Hence, if query is "وماذا عن السؤال الثاني؟", it resolves to missing subject/year.


# 3. CODE PATCHES
- In `microservices/orchestrator_service/src/api/routes.py`, `_ensure_conversation` needs to return a tuple `(conversation_id, messages_list)`.
- In `microservices/orchestrator_service/src/api/routes.py`, we construct the `HumanMessage` / `AIMessage` objects and pass them to `_stream_chat_langgraph`.
- In `microservices/orchestrator_service/src/services/overmind/graph/search.py`, `QueryAnalyzerNode` must concatenate the history messages with the `raw_query` so `dspy` understands the context.


# 4. MEMORY MUST BE STRUCTURED
We will modify `_ensure_conversation` to return `tuple[int, list[dict]]` representing `(conversation_id, history_messages)`.
We will modify `_stream_chat_langgraph` and `_run_chat_langgraph` to accept this `history_messages` and construct the full LangGraph `messages` payload `[HumanMessage(..), AIMessage(..), ...]` to pass as `inputs` to the `app_graph`.

# 5. RETRIEVAL MUST USE REAL QUERY
We will modify `QueryAnalyzerNode` in `microservices/orchestrator_service/src/services/overmind/graph/search.py` to use both the history context and the original query when sending strings to DSPy `analyzer`. Alternatively, DSPy `Predict` handles the query better if we pass a merged context string!

# 6. ROUTER MUST NEVER DROP CONVERSATION
In `SupervisorNode` (`services/overmind/graph/main.py`), there's an `except Exception: pass` logic, which falls through to a rudimentary `intent = "search"`, or `chat` fallback.
Wait, let's verify if `empty_allowed` is possible. Let's check `_serialize_stream_frame`. If empty strings are yielded, the stream shows blank. Also, if there's an exception, it might send `assistant_error`.

Please let me know if this sounds acceptable!
