# Executive Conclusion: Context Amnesia Root Cause
The fundamental cause of context amnesia is a **structural mismatch** between the input API layer (`api/routes.py`) and the orchestration entry point (`SupervisorNode`). The API initializes the state graph solely with `{"messages": [...]}` but omits the explicit `"query"` field. Consequently, `SupervisorNode` reads an empty query (`state.get("query", "")`), effectively blinding downstream nodes (like `GeneralKnowledgeNode`) to the actual user intent at step one. Memory fragmentation via Checkpointer or `thread_id` was disproved; LangGraph memory persists correctly across turns, but the core processing loop immediately discards the latest query context before routing.

---

# Diagnostic Matrix

| Issue | Status | Evidence | File/Function | How to Reproduce | Effect on Context |
|-------|--------|----------|---------------|------------------|-------------------|
| API omits "query" in inputs | **Confirmed** | `inputs = {"messages": graph_messages}` lacks `"query"` | `api/routes.py` line ~1792 | Send chat request to WS endpoint | Initial user intent is structurally absent from LangGraph input payload. |
| `SupervisorNode` fails to extract query | **Confirmed** | `query = str(state.get("query", "")).strip()` returns `""` when absent | `main.py` -> `SupervisorNode.__call__` | Trace node execution with only messages | Downstream nodes receive an empty intent and default to safety fallback strings. |
| Checkpointer session persistence | **Disproved** | Tests show state is properly fetched and appended upon valid `thread_id` | `main.py` -> `MemorySaver` | Run Turn 1 & Turn 2 with identical `thread_id` | N/A (Memory acts correctly) |
| DB History Injection (Split-brain) | **Disproved** | `_build_graph_messages_graph` gracefully avoids injecting full DB history if checkpoint hits | `api/routes.py` -> `_build_graph_messages_graph` | Trace reconnect with state vs no-state | N/A (Delta vs History logic is sound) |

---

# Remaining Unknowns
- None regarding the root cause of this specific context amnesia. The chain of failure is proven in runtime.

---

# Minimal Next Action
Patch `SupervisorNode` in `main.py` to extract the `query` field from the latest `HumanMessage` if `state.get("query")` is missing, ensuring the downstream chain receives the explicit user intent directly from the message stream. Do not blindly mutate history or touch the DB layer.
