# LangGraph Extension Guide — local_graph.py

> How to safely extend the CogniForge LangGraph engine.
> File: `app/services/chat/local_graph.py`
> Version: LangGraph 1.1.10 + MemorySaver

---

## Current Architecture

```
Entry: run_local_graph(question, conversation_id, history_messages)
         ↓
  LocalChatState (TypedDict)
         ↓
  ┌──────────────────────┐
  │   supervisor_node    │  — classifies intent
  └──────────┬───────────┘
             │ intent: "educational" | "general" | "chat"
             ▼
  ┌──────────────────────┐
  │     chat_node        │  — calls OpenRouter LLM
  └──────────┬───────────┘
             ▼
            END

Memory: MemorySaver (in-memory, per conversation_id as thread_id)
LLM: OpenRouter via app.core.ai_gateway.get_ai_client()
```

---

## State Definition

```python
from typing import TypedDict, Optional

class LocalChatState(TypedDict):
    question: str                    # user's message
    intent: str                      # classified intent
    history_messages: list[dict]     # previous messages [{role, content}]
    final_response: str              # output — what gets returned to user

# When adding a field, also update:
# 1. The TypedDict above
# 2. Any node that reads/writes the field
# 3. The initial state in run_local_graph()
```

---

## Adding a New Node

### Pattern 1 — Simple Processing Node

```python
async def my_new_node(state: LocalChatState) -> dict:
    """
    وصف ما يفعله هذا العقدة.
    يجب أن تُرجع dict مع المفاتيح التي تغيرت فقط.
    """
    question = state["question"]
    intent = state["intent"]

    # Your logic here
    processed = f"Processed: {question}"

    return {"final_response": processed}
```

### Pattern 2 — Node with LLM Call

```python
async def llm_node(state: LocalChatState) -> dict:
    from app.core.ai_gateway import get_ai_client

    client = get_ai_client()

    system_prompt = """أنت مساعد تعليمي للطلاب الجزائريين.
    أجب بالعربية أو الفرنسية حسب سؤال الطالب."""

    messages = [
        {"role": "system", "content": system_prompt},
        *state["history_messages"],
        {"role": "user", "content": state["question"]},
    ]

    response = await client.chat.completions.create(
        model="anthropic/claude-3-haiku",
        messages=messages,
        max_tokens=1024,
        temperature=0.7,
    )

    return {"final_response": response.choices[0].message.content}
```

### Pattern 3 — Routing Node (Conditional)

```python
def routing_node(state: LocalChatState) -> str:
    """
    Routing functions return a string — the name of the next node.
    NOT async — must be synchronous.
    """
    intent = state.get("intent", "general")

    if intent == "educational":
        return "educational_node"
    elif intent == "math":
        return "math_node"
    else:
        return "general_node"
```

---

## Wiring New Nodes Into the Graph

```python
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

# After defining your nodes:

graph = StateGraph(LocalChatState)

# Add existing nodes
graph.add_node("supervisor", supervisor_node)
graph.add_node("chat", chat_node)

# Add your new node
graph.add_node("my_new_node", my_new_node)

# Set entry point
graph.set_entry_point("supervisor")

# Add edges — linear
graph.add_edge("supervisor", "chat")
graph.add_edge("chat", END)

# OR — conditional routing
graph.add_conditional_edges(
    "supervisor",           # from
    routing_node,           # function that returns next node name
    {
        "educational_node": "educational_node",
        "math_node": "math_node",
        "general_node": "chat",
    }
)
graph.add_edge("educational_node", END)
graph.add_edge("math_node", END)

# Compile with memory
memory = MemorySaver()
compiled_graph = graph.compile(checkpointer=memory)
```

---

## MemorySaver — Thread Management

```python
# Thread ID = conversation_id — each conversation has its own memory
# This is already handled in run_local_graph()

config = {"configurable": {"thread_id": conversation_id}}

result = await compiled_graph.ainvoke(
    {
        "question": question,
        "intent": "",
        "history_messages": history_messages,
        "final_response": "",
    },
    config=config,
)

# The graph REMEMBERS previous messages for the same thread_id
# Different conversation_ids = completely separate memory
```

---

## Intent Classification Patterns

```python
def classify_intent(question: str) -> str:
    """
    Classify the educational intent of a question.
    Returns: "educational" | "math" | "science" | "general" | "chat"
    """
    q_lower = question.lower()

    # Math keywords (Arabic + French + Latin)
    math_keywords = [
        "معادلة", "حساب", "رياضيات", "جبر", "هندسة",
        "مشتقة", "تكامل", "نهاية", "مصفوفة",
        "équation", "calcul", "mathématiques", "dérivée",
        "solve", "calculate", "equation", "integral"
    ]

    # Physics keywords
    physics_keywords = [
        "فيزياء", "قوة", "طاقة", "حركة", "كهرباء",
        "physique", "force", "énergie", "vitesse",
        "physics", "velocity", "acceleration"
    ]

    # BAC-specific keywords
    bac_keywords = [
        "باك", "بكالوريا", "امتحان", "تمرين",
        "bac", "baccalauréat", "examen", "exercice"
    ]

    # Greeting/chat patterns (short messages)
    if len(question.strip()) < 20 and any(
        w in q_lower for w in ["مرحبا", "سلام", "bonjour", "hello", "hi", "كيف حالك"]
    ):
        return "chat"

    if any(kw in q_lower for kw in math_keywords):
        return "educational"
    if any(kw in q_lower for kw in physics_keywords):
        return "educational"
    if any(kw in q_lower for kw in bac_keywords):
        return "educational"

    return "general"
```

---

## Testing a Graph Flow

```python
import asyncio
from app.services.chat.local_graph import run_local_graph

async def test_graph():
    # Test 1 — simple question
    result = await run_local_graph(
        question="ما هي عاصمة فرنسا؟",
        conversation_id="test-conv-001",
        history_messages=[],
    )
    print("Result:", result)
    assert result and len(result) > 0

    # Test 2 — follow-up (memory test)
    result2 = await run_local_graph(
        question="وما هي أهم معالمها؟",
        conversation_id="test-conv-001",  # same thread = has memory of Q1
        history_messages=[],
    )
    print("Follow-up:", result2)
    # Should mention Paris context from Q1

    # Test 3 — different conversation (isolated memory)
    result3 = await run_local_graph(
        question="أين تقع الجزائر؟",
        conversation_id="test-conv-002",  # different thread = no memory
        history_messages=[],
    )
    print("New conversation:", result3)

asyncio.run(test_graph())
```

---

## Adding Retrieval (RAG) Node

```python
async def bac_retrieval_node(state: LocalChatState) -> dict:
    """
    Retrieves relevant BAC exercises from knowledge_nodes table.
    Augments the question with retrieved context.
    """
    from app.core.database import get_async_session
    from sqlalchemy import select, text

    question = state["question"]

    async for db in get_async_session():
        # Simple text search — upgrade to vector search with pgvector
        result = await db.execute(
            text("""
                SELECT content FROM knowledge_nodes
                WHERE content ILIKE :pattern
                LIMIT 3
            """),
            {"pattern": f"%{question[:50]}%"}
        )
        rows = result.fetchall()

    if rows:
        context = "\n\n".join(row[0] for row in rows)
        augmented = f"معلومات ذات صلة:\n{context}\n\nالسؤال: {question}"
        return {"question": augmented}

    return {}  # no change — pass through to chat node
```

---

## Common LangGraph Errors

| Error | Cause | Fix |
|---|---|---|
| `KeyError: 'field_name'` | State field missing in initial invoke | Add field with default to initial state dict |
| `InvalidUpdateError` | Node returned non-dict | Ensure node returns `dict`, not the full state |
| Graph hangs | Missing `add_edge` to END | Every terminal node needs `add_edge("node", END)` |
| Memory not persisting | Different thread_id per message | Use `conversation_id` consistently as thread_id |
| `RuntimeError: no running event loop` | Sync call in async context | Use `asyncio.run()` in tests, `await` in app code |
