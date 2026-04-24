# LangGraph Architectural Blueprint

## 1. Graph State (CRITICAL BACKBONE)

The system relies on two main state definitions.

### `AgentState` (defined in `microservices/orchestrator_service/src/services/overmind/graph/main.py`)
This is the primary state used by the unified graph.

```python
class AgentState(TypedDict):
    messages: Annotated[list[object], add]
    query: str
    intent: str
    filters: object
    retrieved_docs: list[object]
    reranked_docs: list[object]
    used_web: bool
    final_response: object
    tools_executed: bool
```

**Keys:**
- `messages` (list[object], default: `[]`, reducer: `add`): Persists and grows across nodes (used by LangGraph checkpointer).
- `query` (str): The current user query, potentially resolved with entities.
- `intent` (str): Extracted intent (`educational`, `admin`, `chat`, `general_knowledge`).
- `filters` (object/QueryFilters): Extracted search filters.
- `retrieved_docs` (list[object]): Documents from internal search.
- `reranked_docs` (list[object]): Documents after reranking.
- `used_web` (bool): Indicates if web search fallback was triggered.
- `final_response` (object): The final payload returned to the user.
- `tools_executed` (bool): Indicates if tools were successfully executed.

### `AdminExecutionState` (defined in `microservices/orchestrator_service/src/services/overmind/graph/admin.py`)
Used specifically by the `admin_graph`.

```python
class AdminExecutionState(TypedDict, total=False):
    query: str
    user_role: str
    is_admin: bool
    is_admin_user: bool
    scope: str
    access: str
    resolved_tool: str
    tool_result: str
    tool_name: str
    trust_score: float
    executed_at: str
    error: str
    final_response: dict
```

**Keys:**
- `query`, `user_role`, `is_admin`, `is_admin_user`, `scope`: Input state keys for authorization and context.
- `access`: Overwritten by `ValidateAccessNode`.
- `resolved_tool`: Written by `ResolveToolNode`.
- `tool_result`, `tool_name`, `trust_score`, `executed_at`, `error`: Written by `ExecuteToolNode`.
- `final_response`: Final constructed response by `RenderAnswerNode`.


## 2. State Transitions (MOST IMPORTANT)

### SupervisorNode
- **Reads:** `query`, `messages`
- **Writes:** `intent`, `query` (overwrites with resolved query if applicable)
- **Snapshot Before:** `{"query": "عاصمتها", "messages": [...]}`
- **Snapshot After:** `{"intent": "general_knowledge", "query": "عاصمة فرنسا"}`

### QueryRewriterNode
- **Reads:** `query`, `messages`
- **Writes:** `query` (overwrites if rewrite successful)
- **Snapshot Before:** `{"query": "التمرين السابق", "messages": [...]}`
- **Snapshot After:** `{"query": "التمرين الأول في بكالوريا 2024"}`

### QueryAnalyzerNode
- **Reads:** `query`, `messages`
- **Writes:** `filters`
- **Snapshot Before:** `{"query": "بكالوريا 2024 علوم طبيعية"}`
- **Snapshot After:** `{"filters": QueryFilters(year=2024, subject="علوم طبيعية", ...)}`

### InternalRetrieverNode
- **Reads:** `filters`
- **Writes:** `retrieved_docs`
- **Snapshot Before:** `{"filters": ...}`
- **Snapshot After:** `{"retrieved_docs": [LlamaDocument(...)]}`

### RerankerNode
- **Reads:** `retrieved_docs`, `filters`
- **Writes:** `reranked_docs`
- **Snapshot Before:** `{"retrieved_docs": [...]}`
- **Snapshot After:** `{"reranked_docs": [...]}`

### WebSearchFallbackNode
- **Reads:** `reranked_docs`, `filters`
- **Writes:** `reranked_docs`, `used_web`
- **Snapshot Before:** `{"reranked_docs": []}`
- **Snapshot After:** `{"reranked_docs": [LlamaDocument(...)], "used_web": True}`

### SynthesizerNode
- **Reads:** `reranked_docs`, `filters`, `query`, `messages`
- **Writes:** `final_response`, `messages` (appends)
- **Snapshot Before:** `{"reranked_docs": [...], "messages": [...]}`
- **Snapshot After:** `{"final_response": {...}, "messages": [..., AIMessage(...)]}`

### ChatFallbackNode
- **Reads:** `query`, `messages`
- **Writes:** `final_response`, `messages` (appends)
- **Snapshot Before:** `{"query": "مرحبا", "messages": [...]}`
- **Snapshot After:** `{"final_response": "أهلاً...", "messages": [..., AIMessage(...)]}`

### GeneralKnowledgeNode
- **Reads:** `query`, `messages`
- **Writes:** `final_response`, `messages` (appends)

### ToolExecutorNode
- **Reads:** `query`, `messages`
- **Writes:** `final_response`, `tools_executed`, `messages` (appends)

### AdminAgentNode (Sub-graph)
- **Reads:** All `AgentState` keys
- **Writes:** `final_response`, `tools_executed`, `messages` (appends)


## 3. Ingress & Egress (API BOUNDARY)

In `api/routes.py`:

**Request Parsing:**
- Requests come in via HTTP `POST /api/chat/messages`, `POST /agent/chat`, or WebSockets `/api/chat/ws`, `/admin/api/chat/ws`.
- Payload is parsed for `question` or `objective`, `conversation_id`, and `context`.
- History is fetched from the DB (or checkpointer) and merged with `client_context_messages`.
- Ambiguous queries are pre-augmented via `_augment_ambiguous_objective`.

**Input Schema to Graph:**
```python
inputs = {
    "query": prepared_objective,
    "messages": langchain_msgs,
}
```
If admin scope:
```python
inputs = {
    "query": prepared_objective,
    "messages": langchain_msgs,
    "is_admin": True,
    "user_role": "admin",
    "scope": "..."
}
```

**Egress Construction:**
- The graph streams events via `astream_events`.
- At `on_chain_end` for `LangGraph`, `event["data"].get("output")` provides the state.
- Extracted `final_response` is serialized.
- The user sees a stream frame:
  `{"type": "assistant_final", "payload": {"content": "...", "status": "ok", ...}}`


## 4. Nodes (EXECUTION UNITS)

| Node Name | File | Responsibility | LLM Usage | External Tools | Deterministic |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `SupervisorNode` | `main.py` | Detects intent & routes | YES (DSPy) | None | Stochastic (fallback deterministic) |
| `QueryRewriterNode` | `main.py` | Resolves pronouns using history | YES (DSPy) | None | Stochastic |
| `QueryAnalyzerNode` | `search.py` | Extracts search filters | YES (DSPy) | None | Stochastic |
| `InternalRetrieverNode` | `search.py` | Fetches from internal DB | NO | `research_client` | Deterministic |
| `RerankerNode` | `search.py` | Scores/sorts documents | NO | `FlagEmbeddingReranker` | Deterministic |
| `WebSearchFallbackNode` | `search.py` | Deep search if DB empty | NO | Tavily (`deep_research`) | Deterministic |
| `SynthesizerNode` | `search.py` | Generates final educational answer | YES (DSPy) | None | Stochastic |
| `ChatFallbackNode` | `main.py` | Handles greetings/small talk | YES (`ai_client`) | None | Stochastic |
| `GeneralKnowledgeNode` | `general_knowledge.py` | Answers factual questions | YES (`ai_client`) | None | Stochastic |
| `ToolExecutorNode` | `main.py` | Executes LangChain tool calls | NO | Admin tools | Deterministic |
| `AdminAgentNode` | `main.py` | Wraps `admin_graph` | NO | None | Deterministic |
| `ValidatorNode` | `main.py` | Verifies execution completeness | NO | None | Deterministic |

*(Admin Subgraph Nodes in `admin.py`: `DetectIntentNode`, `ValidateAccessNode`, `ResolveToolNode`, `ExecuteToolNode`, `RenderAnswerNode` - All deterministic).*


## 5. Edges & Routing (CONTROL FLOW)

**Execution Path:**
`START` → `supervisor` → conditional routing...

**Routing Logic (`route_intent` in `main.py`):**
- `educational` (or `search`) → `query_rewriter`
- `admin` → `admin_agent`
- `tool` → `tool_executor`
- `chat` → `chat_fallback`
- `general_knowledge` → `general_knowledge`

**Search Path Flow:**
`query_rewriter` → `query_analyzer` → `retriever` → `reranker` → `check_results` (conditional)
- `check_results` logic:
  - If `len(reranked_docs) > 0` → `found` → `synthesizer`
  - If `intent == "educational"` and no docs → `web_fallback` → `web_fallback` → `synthesizer`
  - Else → `general_knowledge` → `general_knowledge`

**Completion Flow:**
- `admin_agent` → `validator`
- `tool_executor` → `validator`
- `chat_fallback` → `validator`
- `synthesizer` → `validator`
- `general_knowledge` (No direct edge defined to validator, ends natively)
- `validator` → `check_quality` (conditional)
  - Always returns `"pass"` → `END`


## 6. Failure Analysis (CRITICAL)

- ⚠️ **HIGH** | `routes.py`: Context Hydration Failure. If `_augment_ambiguous_objective` or database read fails, graph enters with partial context, causing **context blindness** and hallucination.
- ⚠️ **HIGH** | `search.py`: DSPy Serialization. If `SynthesizerNode` LLM call fails, it falls back to hardcoded `text_val = "عذراً، تعذر صياغة الشرح..."` or raw document text. JSON parsing in history formatting can also silently swallow errors.
- ⚠️ **CRITICAL** | `search.py`: Missing `TAVILY_API_KEY`. If web search is needed but the key is missing, it silently skips and `SynthesizerNode` receives empty docs, resulting in `"لا توجد تفاصيل متاحة."` schema lock.
- ⚠️ **MEDIUM** | `main.py`: `emergency_intent_guard` regex overlap. Broad patterns like `(كم|عدد)` could wrongly hijack general knowledge questions into the admin path if not properly contained.
- ⚠️ **MEDIUM** | `main.py`: State Overwrite. `QueryRewriterNode` overwrites `query`. If the rewrite is poor, the original query intent is permanently lost to downstream nodes.


## 7. LLM Dependency Map

- `SupervisorNode`: DSPy (`IntentClassifier` via OpenRouter). Risk: Misclassification due to poor history formatting.
- `QueryRewriterNode`: DSPy (`QueryRewriterSignature`). Risk: Dropping user constraints during rewrite.
- `QueryAnalyzerNode`: DSPy (`AnalyzeQuery`). Risk: Hallucinating `year` or `exercise_num` when none exist.
- `SynthesizerNode`: DSPy (`EducationalSynthesizer`). Risk: Ignoring constraints (e.g., "no solution") if prompt adherence is weak.
- `ChatFallbackNode` & `GeneralKnowledgeNode`: Use `get_ai_client().send_message` (direct LLM). Risk: Hallucination of facts if context is sparse.


## 8. Performance & Bottleneck Map

- **Sequential Flow:** Search nodes run strictly sequentially (`analyzer` → `retriever` → `reranker` → `synthesizer`).
- **Slow Nodes:**
  - `retriever` & `web_fallback` (I/O bound, network latency).
  - `synthesizer` (LLM Generation, high token count bottleneck).
  - `SupervisorNode` (LLM call for intent blocks initial routing).
- **Parallel Execution:** Not utilized natively in the core search path.


## 9. Injection Points (SAFE INSERTION ZONES)

- **Context Engine (Pre-processing):**
  - **Location:** In `main.py` before `create_unified_graph` or as a new node before `supervisor`. Alternatively, in `api/routes.py` inside `_stream_chat_langgraph` right before constructing `inputs`.
  - **Reasoning:** Need to hydrate and sanitize history *before* intent classification to ensure accurate routing.

- **Governance (Action Control):**
  - **Location:** In `admin.py`, modifying `ValidateAccessNode`.
  - **Reasoning:** Perfect chokepoint to intercept and deny tool executions based on deterministic rules or RBAC before `ResolveToolNode`.

- **Evaluator (Post-response Validation):**
  - **Location:** In `main.py`, replacing the dummy `check_quality` function after `ValidatorNode`.
  - **Reasoning:** `ValidatorNode` aggregates all final states. An evaluator here can inspect `final_response` and either pass it to `END` or loop back to `supervisor` for self-correction.
