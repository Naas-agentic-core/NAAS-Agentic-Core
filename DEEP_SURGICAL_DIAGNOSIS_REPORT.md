# Executive Conclusion: Context Amnesia Root Cause
The context amnesia issue originates at the **API layer boundary (`api/routes.py`)**. The orchestrator WebSocket route (`_stream_chat_langgraph`) initializes the LangGraph state using only `inputs = {"messages": graph_messages}`, explicitly omitting the `"query"` field.
As a result, when the execution hits `SupervisorNode`, the statement `query = str(state.get("query", "")).strip()` returns an empty string. The core intent of the user is discarded immediately before routing, forcing fallback intent classifications and downstream context blindness.

---

# Diagnostic Matrix

| Issue | Status | Evidence | File/Function | How to Reproduce | Effect on Context |
|-------|--------|----------|---------------|------------------|-------------------|
| API omits "query" in `inputs` | **Confirmed** | Runtime trace confirms `inputs` keys are `['messages']`. Line ~1792 in `routes.py`: `inputs: dict[str, object] = {"messages": graph_messages}`. | `api/routes.py` -> `_stream_chat_langgraph` | Trace API request into graph. | Structural erasure of intent. |
| `SupervisorNode` loses context | **Confirmed** | Runtime state snapshot: `state.get('query')` evaluates to `None` inside graph. Downstream nodes receive empty string. | `main.py` -> `SupervisorNode.__call__` | Read internal `AgentState`. | Fallbacks triggered ("عمى السياق"). |
| Manual vs LangGraph disparity | **Confirmed** | Manual agent receives `_build_graph_messages_manual` (dicts), while LangGraph relies on checkpointers + message objects without proper `query` field. | `api/routes.py` | Compare `_stream_chat_manual` vs LangGraph. | Manual preserves intent differently. |
| Memory Checkpointer Failure | **Disproved** | Checkpointer HITs successfully preserve turn-by-turn history. Memory operates correctly when intent isn't zeroed out. | `main.py` -> MemorySaver | Trace Q1 -> Q2. | None (Memory architecture is sound). |
| DB History Injection (Split-brain) | **Disproved** | `_build_graph_messages_graph` safely handles Delta vs Full History logic upon reconnects. | `api/routes.py` -> `_build_graph_messages_graph` | Trace Reconnect / `session_id`. | None (Hydration architecture is sound). |

---

# Route & Execution Map
- **Gateway**: Proxies `/api/chat/ws` directly to orchestrator.
- **Monolith WS**: Legacy dormant code. Gateway bypasses it.
- **Orchestrator WS**: `_stream_chat_langgraph` executes successfully but fails to provide the `query` field to the graph state.
- **`thread_id`**: Persists correctly across standard reconnects.
- **SSOT**: The Checkpointer is the active SSOT. DB is an archive.

---

# Remaining Unknowns
- None. The diagnostic traces perfectly align with the exact point of context failure.

---

# Minimal Next Action
Patch `_stream_chat_langgraph` in `api/routes.py` to include the `query` field during `inputs` initialization: `inputs: dict[str, object] = {"messages": graph_messages, "query": prepared_objective}`.
