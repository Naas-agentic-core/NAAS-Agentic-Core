report = """
═══════════════════════════════════════════════════════════
تقرير التشريح الجنائي — E-TAALEEM PRODUCTION
═══════════════════════════════════════════════════════════

## 1. Executive Diagnosis
The catastrophic failure is a severe multi-layer collapse spanning state memory, retrieval composition, and intent routing.
1. **The Context Deafness (Stateless Facade)**: The API facade (`routes.py`) accepts `conversation_id`, but compatibility logic routinely forces missing or stripped IDs, leading the system to fallback to a new `conversation_id` or just pass flattened history that blows up the context window.
2. **Constraint Violation (Generator Bypass)**: The system lacks a post-retrieval Generator Node that uses an LLM. `SynthesizerNode` explicitly bypasses generation and maps raw chunk text directly to the response JSON: `text_val = reranked[0].text; response_json = { "التمرين": text_val }`. This means active constraints like "Question 1 only" are mathematically ignored.
3. **Ghost Response (Empty Chat Catch-All)**: Follow-up constraints ("ماذا يطلب السؤال رقم 2") and greetings ("السلام عليكم") either fall out of the `ADMIN_PATTERNS` regex router and into `ChatFallbackNode` which fails to use context, or get swallowed.
4. **The Constant-Function Retriever (Chunk Granularity)**: The vectors stored in Supabase represent entire exercises. Since there is no LLM generator to filter them, any query regarding the exercise simply returns the entire chunk.

## 2. Real Execution Path
1. `microservices/orchestrator_service/src/api/routes.py` -> `chat_ws_stategraph` / `admin_chat_ws_stategraph`
2. `routes.py` -> `_ensure_conversation`
3. `microservices/orchestrator_service/src/services/overmind/graph/main.py` -> `SupervisorNode.__call__`
4. `microservices/orchestrator_service/src/services/overmind/graph/search.py` -> `QueryAnalyzerNode`
5. `search.py` -> `InternalRetrieverNode`
6. `search.py` -> `SynthesizerNode` (for educational requests)
7. `main.py` -> `ChatFallbackNode` (for chat/fallback)

## 3. Evidence Matrix

| Failure Layer | Observed Symptom | Code Evidence | Confidence | Why It Matters |
| :--- | :--- | :--- | :--- | :--- |
| **Answer Composition** | "السؤال الأول فقط" returns the full exercise. | `SynthesizerNode` (`search.py:285`) assigns `text_val = reranked[0].text` without calling an LLM. | High | Output shaping and constraints are physically bypassed by design. |
| **Flattened History** | "ماذا يطلب السؤال رقم 2" fails context. | `main.py:188` and `search.py:66` use `"\n".join(recent_messages)` to jam historical JSONs into string prompts. | High | Context is poorly flattened, causing LLM blindness to turn-based tracking. |
| **Router Extraction** | Tool requests work while conversation fails. | `SupervisorNode` (`main.py`) uses `emergency_intent_guard` with regex `ADMIN_PATTERNS` to force tool requests, bypassing DSPy LLM. | High | Explains why tool queries succeed despite general graph memory failure. |
| **Memory Ownership** | System acts stateless across multiple turns. | `routes.py` manages DB, but facades often strip `conversation_id`, causing `_ensure_conversation` to create a new one every turn. | High | Explains total amnesia on subsequent requests. |

## 4. Detailed Root Cause Analysis

### Stateless nodes & Flattened history
While `state.get("messages", [])` exists, it is aggressively flattened via `"\n".join(recent_messages)` in both `QueryAnalyzerNode` and `ChatFallbackNode`. Since assistant responses are raw JSON strings, the system prompt becomes a massive block of malformed text, destroying the LLM's attention mechanism for specific questions.

### Active constraint failure & Retrieval granularity failure
When the user asks "اعطني السؤال الأول فقط بدون حل", the retrieval engine retrieves the whole chunk. Crucially, there is no LLM to slice the text. `SynthesizerNode` simply maps `reranked[0].text` to the output JSON. The system acts as a pure search engine, rendering active user constraints meaningless.

### Router/supervisor failure
Tool requests function perfectly because `emergency_intent_guard` matches explicit regex patterns (`ADMIN_PATTERNS`). However, general chat and follow-ups are routed dynamically by `IntentClassifier`, which struggles to categorize out-of-context follow-ups ("ماذا يطلب السؤال رقم 2") when the history is a massive flattened JSON block.

### Output / finalization failure
In multiple places, if a RAG query fails, fallback nodes return "؟" or generic empty strings. The lack of proper exception handling and the rigid JSON output format causes ghost responses.

## 5. Specific Explanation of the Client Incident
1. **User asks for exercise**: "اعطني تمرين الاحتمالات بكالوريا شعبة علوم تجريبية"
2. **System retrieves full exercise**: `InternalRetrieverNode` finds the chunk. `SynthesizerNode` directly copies `chunk.text` to output without an LLM filter.
3. **User asks "question 1 only"**: "لقد طلبت السؤال الأول فقط و ليس كامل التمرين"
4. **System repeats full exercise**: The system retrieves the exact same chunk. Since there is no generator, `SynthesizerNode` blindly copies the same full text again.
5. **User asks "what does question 2 ask?"**: "ماذا يطلب السؤال رقم 2"
6. **System says it needs the text**: The history is flattened into a giant text block. The `QueryAnalyzerNode` fails to extract context, falls back to an empty filter, and the `ChatFallbackNode` safely responds "يرجى تزويدي بنص السؤال..." because it cannot parse the flattened JSON history to find the text.

## 6. Ranked Root Causes
1. **Synthesizer Bypass (Highest Confidence)**: Hardcoded `text_val = reranked[0].text` instead of LLM generation physically prevents the system from obeying constraints.
2. **Memory Flattening (Highest Confidence)**: `"\n".join(...)` on complex JSON payloads destroys the LLM context window.
3. **Split-Brain Memory (High Confidence)**: Dropped `conversation_id`s force the system to treat follow-ups as isolated interactions.

## 7. Diagnostic Unknowns
- Exact size and content of vectors in the Supabase DB cannot be confirmed due to lack of environment credentials during this diagnostic run, though it is highly probable exercises are single large chunks.

السبب الجذري #1 (الأكثر تدميراً):
  عدم وجود عقدة توليد (Generator) بعد الاسترجاع.
  الأثر: النظام ينسخ النص المسترجع الخام مباشرة إلى المستخدم ويتجاهل أي قيود مثل "فقط" أو "بدون حل".
  الدليل: SynthesizerNode في search.py (السطر 298) يستخدم `text_val = reranked[0].text` بلا LLM.
  الخطورة: 🔴 حرجة

السبب الجذري #2:
  تسطيح الذاكرة (Flattened History).
  الأثر: تدمير السياق وجعل النظام أعمى عن الإشارات المرجعية.
  الدليل: "\n".join(recent_messages) في main.py و search.py.
  الخطورة: 🔴 حرجة

سلسلة الأسباب (Causal Chain):
  غياب المولد (Generator Bypass) → يُسبب → فشل تطبيق القيود (Constraint Violation)
  تسطيح الذاكرة (Flattened History) → يُسبب → فقدان السياق (Context Deafness)
  السبب 1 + السبب 2 → يُسببان معاً → الشلل الإدراكي وتكرار نفس التمرين حرفياً.

الأثر على المستخدم النهائي:
  - الطالب يكرر نفس السؤال 80 مرة بدون فائدة.
  - الطالب يطلب "السؤال الأول فقط" ويحصل على التمرين كاملاً.
  - الطالب يقول "السلام عليكم" ويحصل على رد غامض أو فارغ بسبب التوجيه الخاطئ.

درجة تعقيد الإصلاح: متوسطة — أخطاء معمارية تتطلب إضافة عقدة Generator وتعديل كيفية تمرير الذاكرة (messages) بدلاً من التسطيح.
═══════════════════════════════════════════════════════════
"""
print(report)
