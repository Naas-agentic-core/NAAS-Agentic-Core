# تشخيص تشتت السياق بين مسارات manual agent و LangGraph

**التاريخ:** 2026-04-28  
**الحالة:** مُنجز — patches مطبقة، اختبارات تمر

---

## 1. خريطة المسارات الفعلية

```
Client WebSocket
    │
    ├─► app/api/routers/customer_chat.py  (monolith WS /ws)
    │       │  يحفظ رسالة في DB، يجلب history، يدمج client_context
    │       └─► orchestrator_client.chat_with_agent()
    │               │  HTTP POST → /agent/chat
    │               └─► OrchestratorAgent.run()  ← لا checkpointer
    │
    └─► microservices/orchestrator_service/src/api/routes.py
            ├─► /api/chat/ws  → _stream_chat_langgraph() → app_graph.astream_events()  ← checkpointer
            └─► /agent/chat   → OrchestratorAgent.run()  ← لا checkpointer
```

### المسار الكامل لكل نوع

| المسار | Entrypoint | Routing | State Building | Graph Invocation | Persistence |
|--------|-----------|---------|----------------|-----------------|-------------|
| **monolith customer WS** | `customer_chat.py /ws` | `orchestrator_client.chat_with_agent()` | DB history + client_context merge | `OrchestratorAgent.run()` | monolith DB + orchestrator DB |
| **monolith admin WS** | `admin.py /api/chat/ws` | `orchestrator_client.chat_with_agent()` | DB history + client_context merge | `OrchestratorAgent.run()` | monolith DB + orchestrator DB |
| **orchestrator customer WS** | `routes.py /api/chat/ws` | `_stream_chat_langgraph()` | DB history + checkpointer probe | `app_graph.astream_events()` | orchestrator DB + checkpointer |
| **orchestrator admin WS** | `routes.py /admin/api/chat/ws` | `_stream_chat_langgraph()` | DB history + checkpointer probe | `admin_app.astream_events()` | orchestrator DB + checkpointer |
| **HTTP /agent/chat** | `routes.py /agent/chat` | `OrchestratorAgent.run()` مباشرة | `history_messages` من الطلب فقط | `agent.run()` | orchestrator DB |

---

## 2. الإجابات الحاسمة

| السؤال | الإجابة المثبتة بالكود |
|--------|----------------------|
| هل manual agent يمر عبر LangGraph؟ | **لا.** `/agent/chat` يستدعي `OrchestratorAgent.run()` مباشرة — لا graph، لا checkpointer |
| هل chat العادية تختلف عن admin chat؟ | **لا فرق جوهري** — نفس `_stream_chat_langgraph()`، الفرق فقط في `chat_scope` و `admin_payload` |
| هل يوجد أكثر من source of truth؟ | **نعم — ثلاثة:** DB في monolith + DB في orchestrator + checkpointer (Postgres أو MemorySaver) |
| هل gateway يمرر history كاملة؟ | **نعم** — يمرر `history_messages` كاملاً في كل طلب عبر HTTP body |
| هل session_id يتحول إلى thread_id؟ | **لا.** `session_id` للـ diagnostic logging فقط. `thread_id = u{user_id}:c{conversation_id}` |
| هل graph يُعاد بناؤه لكل request؟ | **لا.** يُبنى مرة واحدة في `lifespan()` ويُخزن في `app.state.app_graph` |
| هل checkpointer يعمل في مسار monolith؟ | **لا.** monolith يصل للـ orchestrator عبر HTTP `/agent/chat` الذي لا يستخدم checkpointer |

---

## 3. تحليل state management

### thread_id

```python
# البناء الحتمي — نفس المدخلات → نفس النتيجة دائماً
thread_id = f"u{user_id}:c{conversation_id}"

# مثال: user_id=42, conversation_id=100 → "u42:c100"
```

- `thread_id` يتغير عند تغيير `conversation_id` → checkpointer state جديد
- `session_id` لا يؤثر على `thread_id` — يُستخدم فقط في `_emit_identity_diagnostic_log()`
- reconnect بنفس `conversation_id` → نفس `thread_id` → نفس checkpointer state ✅

### checkpointer

```
عند startup (lifespan):
    active_checkpointer = get_checkpointer() or _memory_saver
    app.state.app_graph = create_unified_graph(checkpointer=active_checkpointer)

عند كل طلب WS:
    config = {"configurable": {"thread_id": "u{uid}:c{cid}"}}
    app_graph.astream_events(inputs, config=config)
```

- `AsyncPostgresSaver` إذا كانت DB متاحة → persistence حقيقية بين restarts
- `MemorySaver` singleton (module-level) → persistence داخل نفس العملية فقط
- `/agent/chat` لا يستخدم أياً منهما

### inputs["messages"] — الفرق الجوهري

```python
# مسار LangGraph (مع checkpointer نشط):
inputs = {"messages": [HumanMessage(content=objective)]}  # delta فقط

# مسار LangGraph (بدون checkpointer أو بدون حالة محفوظة):
inputs = {"messages": [HumanMessage("Q1"), AIMessage("A1"), HumanMessage("Q2")]}  # كامل

# مسار manual OrchestratorAgent:
messages = [{"role": "user", "content": "Q1"}, {"role": "assistant", "content": "A1"}, ...]
agent.run(objective, context=context, history_messages=messages)
```

---

## 4. تحليل history injection

### المصادر

```
DB (orchestrator) ──► _ensure_conversation() ──► history_messages
                                                        │
                                                        ▼
                              _merge_history_with_client_context()
                                                        │
                                                        ▼
                              _build_graph_messages_graph() أو _build_graph_messages_manual()
```

### سلوك `_merge_history_with_client_context`

| الحالة | monolith (قبل patch) | monolith (بعد patch) | orchestrator |
|--------|---------------------|---------------------|-------------|
| `client_context = []` | يُعيد `persisted` | يُعيد `persisted` | يُعيد `persisted` |
| `persisted = []` | يُعيد `[]` | يُعيد `[]` | يُعيد `[]` |
| `client` لا يتداخل مع `persisted` | **يضيف كل client** ⚠️ | يُعيد `persisted` فقط ✅ | يُعيد `persisted` فقط ✅ |
| `client` يتداخل جزئياً (partial tail) | **يضيف كل client** ⚠️ | يُعيد `persisted` فقط | يُعيد `persisted` فقط |
| `client` يتداخل كاملاً | يضيف الجديد | يضيف الجديد ✅ | يضيف الجديد ✅ |

---

## 5. الـ Bugs المثبتة

### Bug 1 — Context Leakage في monolith (مُصلح ✅)

**الملفات:** `app/api/routers/customer_chat.py`، `app/api/routers/admin.py`

**السلوك قبل الإصلاح:**
```python
# كانت تضيف كل client_context بدون فحص تداخل
merged_history = list(persisted_history)
for message in client_context:
    if message not in merged_history:
        merged_history.append(message)
```

**المشكلة:** إذا أرسل العميل `client_context` يحتوي رسائل من محادثة أخرى، تُضاف كلها للـ history المرسل للـ orchestrator.

**الإصلاح:**
```python
# يكشف التداخل بين persisted_tail[-3:] و client_context
# يضيف فقط الرسائل الجديدة المتداخلة
persisted_tail = persisted_history[-3:] if len(persisted_history) >= 3 else persisted_history
overlap_index: int | None = None
for start in range(len(client_context) - len(persisted_tail), -1, -1):
    if client_context[start : start + len(persisted_tail)] == persisted_tail:
        overlap_index = start + len(persisted_tail)
        break
if overlap_index is None:
    return persisted_history
```

---

### Bug 2 — Partial Tail Overlap Detection (موثق، غير مُصلح)

**الملف:** `microservices/orchestrator_service/src/api/context_utils.py`

**المشكلة:** إذا أرسل العميل `client_context` يبدأ من منتصف `persisted_tail` (وليس من أوله)، يفشل الكشف ويُعاد `persisted` فقط — الرسائل الجديدة تُفقد.

**مثال:**
```python
persisted = [Q1, A1, Q2]
persisted_tail = [Q1, A1, Q2]  # آخر 3

# client يبدأ من A1 وليس Q1 → لا تطابق
client = [A1, Q2, A2_new]  # A2_new لن تُضاف
```

**الأثر:** context loss في حالة partial client sync — ليس تسريباً لكنه فقدان للرسائل الجديدة.

---

### Bug 3 — Context Loss في أول رسالة (سلوك متعمد، موثق)

**جميع implementations** تُعيد `[]` عند `persisted=[]` حتى لو `client_context` يحتوي رسائل.

**السبب المتعمد:** يمنع تسريب محادثات أخرى عند بدء محادثة جديدة.

**الأثر:** أول رسالة في محادثة جديدة لا تستفيد من `client_context` — السياق يبدأ من الصفر.

---

## 6. السبب الجذري للـ fragmentation

**Symptom:** كل رسالة تبدأ من الصفر في مسار monolith.

**Root cause:** مسار monolith → `/agent/chat` → `OrchestratorAgent.run()` يعتمد **كلياً** على `history_messages` المحقونة من العميل. لا يوجد checkpointer في هذا المسار.

```
monolith WS
    │
    ├── يحفظ رسالة في DB ✅
    ├── يجلب history من DB ✅
    ├── يدمج client_context (كان معطوباً، مُصلح الآن) ✅
    └── يرسل history عبر HTTP إلى /agent/chat
            │
            └── OrchestratorAgent.run(history_messages=history)
                    │
                    └── لا checkpointer — السياق يعيش فقط في هذا الطلب
```

مسار WebSocket المباشر للـ orchestrator (`/api/chat/ws`) يملك checkpointer ويحتفظ بالسياق ذاتياً بين الطلبات.

**الفرق العملي:**

| | monolith → /agent/chat | orchestrator /api/chat/ws |
|--|----------------------|--------------------------|
| السياق بين الطلبات | يعتمد على history_messages المرسلة | checkpointer يحفظه ذاتياً |
| reconnect بنفس session | يحتاج إعادة إرسال history | يستعيد من checkpointer تلقائياً |
| أول رسالة في محادثة جديدة | لا سياق | لا سياق (checkpointer فارغ) |
| الرسالة الثانية فصاعداً | سياق موجود إذا أرسل العميل history | سياق موجود دائماً |

---

## 7. الـ Patches المطبقة

### `app/api/routers/customer_chat.py`

استبدال `_merge_history_with_client_context` بمنطق overlap-based مطابق لـ `orchestrator/context_utils.py`.

### `app/api/routers/admin.py`

نفس الـ patch — الدالتان الآن متطابقتان في المنطق مع `orchestrator/context_utils.py`.

---

## 8. الاختبارات

**الملف:** `tests/unit/test_context_fragmentation.py`  
**النتيجة:** 38/38 ✅

| المجموعة | عدد الاختبارات | ما تثبته |
|---------|--------------|---------|
| `TestMergeHistoryMonolith` | 4 | سلوك monolith بعد الـ patch |
| `TestMergeHistoryOrchestrator` | 4 | سلوك orchestrator + توثيق partial tail bug |
| `TestMergeHistoryDivergence` | 1 | إثبات أن كلا الـ implementations متطابقتان بعد الـ patch |
| `TestBuildGraphMessagesGraph` | 4 | سلوك LangGraph مع/بدون checkpointer |
| `TestBuildGraphMessagesManual` | 4 | سلوك manual agent + إثبات format مختلف |
| `TestThreadIdResolution` | 10 | ثبات thread_id + عزل المستخدمين |
| `TestExtractClientContextMessages` | 4 | تصفية client_context |
| `TestPathDivergenceProof` | 7 | إثبات الفرق الجوهري بين المسارين |

---

## 9. ما لم يُصلح (قرار متعمد)

1. **Partial tail overlap** في `context_utils.py` — الإصلاح يتطلب تغيير منطق الكشف لدعم partial matches، وهو تغيير أكبر يحتاج ADR منفصل.

2. **Context loss في أول رسالة** — سلوك متعمد لمنع تسريب المحادثات. الحل الصحيح هو أن يرسل العميل `client_context` فارغاً في أول رسالة.

3. **مسار /agent/chat بدون checkpointer** — هذا تصميم معماري. الحل الكامل هو توجيه monolith للـ WebSocket endpoint مباشرة بدلاً من HTTP `/agent/chat`، لكنه تغيير كبير يحتاج ADR منفصل.
