---
name: langgraph-agent-patterns
description: Patterns for building LangGraph agent graphs in this project. Use when working on orchestrator_service, planning_agent, or reasoning_agent — any file that imports from langgraph.
---

# LangGraph Agent Patterns

> **Project context:** LangGraph is used in `microservices/orchestrator_service/`,
> `microservices/planning_agent/`, and `microservices/reasoning_agent/`.
> The canonical graph blueprint is in `LangGraph_Architectural_Blueprint.md` at the repo root.
> Read that file for the full node/edge map before modifying any graph.

---

## State Definitions

### Primary graph — `AgentState`

Defined in `microservices/orchestrator_service/src/services/overmind/graph/main.py`.

```python
from operator import add
from typing import Annotated, TypedDict


class AgentState(TypedDict):
    """الحالة الرئيسية للرسم البياني الموحد."""
    messages: Annotated[list[object], add]  # يتراكم عبر العقد — مطلوب للـ checkpointer
    query: str
    intent: str
    filters: object
    retrieved_docs: list[object]
    reranked_docs: list[object]
    used_web: bool
    final_response: object
    tools_executed: bool
```

Key rules:
- `messages` **must** use `Annotated[list[object], add]` — the `add` reducer is required by the LangGraph checkpointer to accumulate history across invocations.
- `QueryRewriterNode` overwrites `query`. If the rewrite is poor, the original is permanently lost to downstream nodes — guard rewrites carefully.

### Admin subgraph — `AdminExecutionState`

Defined in `microservices/orchestrator_service/src/services/overmind/graph/admin.py`.

```python
class AdminExecutionState(TypedDict, total=False):
    """حالة الرسم البياني الإداري."""
    query: str
    user_role: str
    is_admin: bool
    is_admin_user: bool
    scope: str
    access: str           # written by ValidateAccessNode
    resolved_tool: str    # written by ResolveToolNode
    tool_result: str
    tool_name: str
    trust_score: float
    executed_at: str
    error: str
    final_response: dict[str, object]
```

Use `total=False` for admin state — most keys are written progressively by successive nodes.

---

## Node Pattern

Each node is a pure async function that returns only the keys it updates:

```python
async def classify_intent(state: AgentState) -> dict[str, object]:
    """يصنّف نية المستخدم ويُعيد مفتاح intent فقط."""
    intent = await _classifier.classify(state["query"])
    return {"intent": intent}
```

Rules:
- Return a **partial** state dict — only the keys this node writes.
- Never mutate `state` in place.
- Always `async` — synchronous nodes block the event loop.
- Docstrings must be in Arabic (project standard).

---

## Graph Assembly

```python
from langgraph.graph import END, StateGraph


def create_graph() -> object:
    """يبني الرسم البياني الموحد ويُعيد التطبيق المُجمَّع."""
    graph = StateGraph(AgentState)

    graph.add_node("supervisor", supervisor_node)
    graph.add_node("query_rewriter", query_rewriter_node)
    graph.add_node("synthesizer", synthesizer_node)

    graph.set_entry_point("supervisor")
    graph.add_conditional_edges("supervisor", route_intent)
    graph.add_edge("query_rewriter", "synthesizer")
    graph.add_edge("synthesizer", END)

    return graph.compile()


# Compile once at module level — do not compile per request
app = create_graph()
```

---

## Routing (Conditional Edges)

```python
def route_intent(state: AgentState) -> str:
    """يُحدد المسار بناءً على النية المُصنَّفة."""
    intent = state.get("intent", "chat")
    if intent in ("educational", "search"):
        return "query_rewriter"
    if intent == "admin":
        return "admin_agent"
    if intent == "general_knowledge":
        return "general_knowledge"
    return "chat_fallback"
```

The routing function receives the full state and returns a node name string. Keep routing logic deterministic — no LLM calls inside routing functions.

---

## Ingress / Egress (API Boundary)

**Input schema** passed to the graph from `api/routes.py`:

```python
inputs = {
    "query": prepared_objective,
    "messages": langchain_msgs,   # list[BaseMessage]
}
# Admin scope adds:
inputs["is_admin"] = True
inputs["user_role"] = "admin"
inputs["scope"] = scope_value
```

**Streaming output** — use `astream_events`:

```python
async for event in app.astream_events(inputs, config=config, version="v1"):
    if event["event"] == "on_chain_end" and event["name"] == "LangGraph":
        output = event["data"].get("output", {})
        final_response = output.get("final_response")
```

---

## Node Reference

| Node | File | Writes | Uses LLM |
|------|------|--------|----------|
| `SupervisorNode` | `main.py` | `intent`, `query` | Yes (DSPy) |
| `QueryRewriterNode` | `main.py` | `query` | Yes (DSPy) |
| `QueryAnalyzerNode` | `search.py` | `filters` | Yes (DSPy) |
| `InternalRetrieverNode` | `search.py` | `retrieved_docs` | No |
| `RerankerNode` | `search.py` | `reranked_docs` | No |
| `WebSearchFallbackNode` | `search.py` | `reranked_docs`, `used_web` | No |
| `SynthesizerNode` | `search.py` | `final_response`, `messages` | Yes (DSPy) |
| `ChatFallbackNode` | `main.py` | `final_response`, `messages` | Yes |
| `GeneralKnowledgeNode` | `general_knowledge.py` | `final_response`, `messages` | Yes |
| `ToolExecutorNode` | `main.py` | `final_response`, `tools_executed`, `messages` | No |
| `AdminAgentNode` | `main.py` | `final_response`, `tools_executed`, `messages` | No |

---

## Known Failure Modes

These are documented in `LangGraph_Architectural_Blueprint.md §6` — be aware when modifying:

| Risk | Location | Description |
|------|----------|-------------|
| Context blindness | `routes.py` | History hydration failure before graph entry causes hallucination |
| Silent web search skip | `search.py` | Missing `TAVILY_API_KEY` silently skips fallback; synthesizer receives empty docs |
| Query overwrite loss | `main.py` | `QueryRewriterNode` permanently overwrites `query`; poor rewrite loses original intent |
| Admin path hijack | `main.py` | Broad regex in `emergency_intent_guard` can misroute general questions to admin path |

---

## Anti-patterns

- **Do not** use `global` state inside nodes — pass everything through `AgentState`.
- **Do not** call other microservices directly from nodes — use `httpx.AsyncClient` with `X-Correlation-ID` (see AGENTS.md Inter-Service Communication).
- **Do not** compile the graph per request — compile once at module/startup level, invoke per request.
- **Do not** add LLM calls inside routing functions — routing must be deterministic.
- **Do not** add new keys to `AgentState` without updating `LangGraph_Architectural_Blueprint.md`.
