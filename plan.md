1. **Phase 1 — Context Engine (Pre-LLM Control)**
   - In `routes.py`, `_augment_ambiguous_objective` will be modified.
   - It will deterministically extract an entity from history and rewrite ambiguous queries (e.g., "عاصمتها") without calling an LLM.
   - The query will only be rewritten if an entity is found. Otherwise, the original query will be kept.

2. **Phase 2 — Validation Layer (Post-LLM Control)**
   - In `main.py`, `check_quality` edge will be modified.
   - It will check if `final_response` is invalid (e.g., "لم أفهم", "يرجى التوضيح", empty, generic fallback).
   - If invalid, it will reroute to a retry mechanism or `general_knowledge` node (returning "fail" or "retry").

3. **Phase 3 — Governance (Safe Execution)**
   - In `admin.py`, `ValidateAccessNode` will be updated to include an explicit allowlist for tools based on `ADMIN_TOOL_CONTRACT`.
   - It will block unknown tool calls and prevent unsafe execution.

4. **Phase 4 — State Safety (Critical Fix)**
   - In `SupervisorNode` (`main.py`), state safety will be added: `if "original_query" not in state: state["original_query"] = state.get("query", "")`.
   - This ensures the original intent is never lost.

5. **Testing**
   - Tests will be added/modified in `test_routing.py` or a new file to verify context resolution, failure recovery, and no regression in the admin flow.

6. **Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.**
   - Call `pre_commit_instructions` and follow its instructions to complete pre-commit steps.

7. **Submit the change.**
   - Use the `submit` tool with a short, descriptive branch name and commit message.
