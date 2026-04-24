# STRICT FORENSIC ARCHITECTURAL AUTOPSY: DUAL-TRACK ANALYSIS

## TRACK 1: THE DETERMINISTIC ADMIN TRACK (Python File Counter)

### 1. The Trigger (Routing)
- **File:** `microservices/orchestrator_service/src/services/overmind/graph/main.py`
- **Lines:** 158-165, 535-538
- **Snippet:**
```python
ADMIN_PATTERNS = [
    r"(كم|عدد|احسب|حساب|كمية)\s*(عدد)?\s*(ملفات|ملف|بايثون)",
    ...
]
...
        for pattern in ADMIN_PATTERNS:
            if re.search(pattern, query, re.IGNORECASE):
                emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
                return {"intent": "admin", "query": query}
```
- **Explanation:** The `SupervisorNode` directly intercepts queries matching `ADMIN_PATTERNS` using a deterministic `re.search`. When it sees "كم عدد ملفات بايثون", it forcefully returns the `"admin"` intent, skipping any LLM classification.

### 2. The Implementation
- **File:** `microservices/orchestrator_service/src/contracts/admin_tools.py`
- **Lines:** 37-48
- **Snippet:**
```python
def _count_python_files_sync(root_dir: str) -> int:
    count = 0
    excluded_dirs = {".venv", "__pycache__", "site-packages", "node_modules", ".git"}
    for _, dirnames, filenames in os.walk(root_dir):
        dirnames[:] = [d for d in dirnames if d not in excluded_dirs]
        for f in filenames:
            if f.endswith(".py"):
                count += 1
    return count
```
- **Explanation:** This function recursively walks the directory tree starting from `root_dir`. The statement `dirnames[:] = [d for d in dirnames if d not in excluded_dirs]` modifies the `dirnames` list in-place, which correctly instructs `os.walk` to prune (skip) the excluded directories like `.venv` and `node_modules`.

### 3. The Monolith Fallback
- **File:** `app/services/capabilities/file_intelligence.py`
- **Lines:** 86-93
- **Snippet:**
```python
def build_file_count_command(extension: str | None = None) -> str:
    """يبني أمرًا موحدًا وآمنًا لعدّ الملفات مع استبعاد المسارات الثقيلة."""
    extension_filter = f" -name '*.{extension}'" if extension else ""
    return (
        "find . "
        "\\( -path './.git' -o -path './.venv' -o -path './venv' -o "
        "-path './node_modules' -o -path '*/__pycache__' -o "
        "-path '*/.pytest_cache' -o -path '*/.mypy_cache' \\) -prune -o "
        f"-type f{extension_filter} -print | wc -l"
    )
```
- **Explanation:** This fallback builds a shell command using `find` to count files. It uses `-prune` to efficiently skip excluded directories, mimicking the `dirnames[:]` pruning logic found in the modern tool implementation.


## TRACK 2: THE GENERATIVE EDUCATIONAL TRACK (Bac 2024 Photocopier)

### 1. The Panic Trigger
- **File:** `microservices/orchestrator_service/src/services/overmind/utils/intent_detector.py`
- **Lines:** 84-88 (also in `app/services/chat/intent_registry.py`)
- **Snippet:**
```python
            (
                r"((أ|ا)ريد|بدي|i want|need|show|أعطني|هات|give me)?\s*(.*)(20[1-2][0-9]|bac|بكالوريا|subject|topic|lesson|درس|موضوع|تمارين|تمرين|exam|exercise|exercises|question|احتمالات|دوال|متتاليات|probability|functions|sequences)(.+)?",
                ChatIntent.CONTENT_RETRIEVAL,
                self._extract_query_optional,
            ),
```
- **Explanation:** The regex greedily matches keywords like `تمرين` or `احتمالات` forcing the intent to `CONTENT_RETRIEVAL` (which routes to the educational/search graph), bypassing the generative capabilities for general conversation.

### 2. The Poisoned Prompt
- **File:** `microservices/orchestrator_service/src/services/overmind/agents/orchestrator.py`
- **Lines:** 499-501 (also in `app/services/chat/agents/orchestrator.py`, lines 442-444)
- **Snippet:**
```python
            "\n\nEXAMPLES:"
            "\n- 'تمرين أعداد مركبة' -> {'q': 'complex numbers'}"
            "\n- 'احتمالات بكالوريا 2024' -> {'q': 'probability', 'year': 2024, 'level': 'baccalaureate'}"
```
- **Explanation:** A few-shot example in the system prompt explicitly maps the query "احتمالات بكالوريا 2024" to specific extraction parameters. This biases the LLM into recognizing this specific string and strongly associating it with the query parameters used for retrieval.

### 3. The Knowledge Source
- **File:** `data/knowledge/bac_2024_probability.md`
- **Lines:** 1-89 (entire file)
- **Snippet:**
```markdown
---
title: تمرين الاحتمالات بكالوريا 2024 شعبة علوم تجريبية الموضوع الاول التمرين الأول
subject: Mathematics
grade: 3AS
...
```
- **Explanation:** A hardcoded markdown file containing the full text and solution for the Bac 2024 probability exercise. Due to vector space dominance (lack of other files), queries mapped to the educational track almost exclusively retrieve this single file.

### 4. The Photocopier Node
- **File:** `microservices/orchestrator_service/src/services/overmind/graph/search.py`
- **Lines:** 386-389
- **Snippet:**
```python
            try:
                prediction = await anyio.to_thread.run_sync(
                    lambda: self.generator(
                        context=raw_doc_text, conversation=conversation_text, query=query
                    )
                )
                text_val = getattr(prediction, "response", raw_doc_text).strip()
            except Exception as e:
                logger.error(f"Synthesizer LLM generation failed: {e}")
                text_val = raw_doc_text
```
- **Explanation:** Inside `SynthesizerNode`, if the DSPy generation fails (or is bypassed), the `except` block catches the exception and forcefully sets `text_val = raw_doc_text`. This literally acts as a photocopier, returning the raw text of the retrieved markdown file (`bac_2024_probability.md`) verbatim instead of synthesizing a response.


## TRACK 3: MOCK & HARDCODED DATA DETECTION (SECURITY AUDIT)

### 1. `MockGeniusAI`
- **File:** `tests/verify_bac_math_kagent.py`
- **Lines:** 31-77
- **Snippet:**
```python
class MockGeniusAI(AIClient):
...
        elif "Synthesize final answer" in prompt or "Overmind Super Reasoner" in system_prompt:
            res.content = (
                "## Baccalauréat Algérie 2024 - Mathématiques (Probabilités)\n\n"
...
                "La probabilité d'obtenir deux boules de couleurs différentes est **31/60**."
            )
```
- **Explanation:** A mock AI client hardcodes the complete solution and exact verbiage to the Bac 2024 probability problem, faking the reasoning process entirely for the test.
