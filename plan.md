1. **Fix Gateway Session Continuity**:
   - The Gateway loses session continuity when it dynamically builds upstream WS URLs because it strips the `session_id` out of the URL proxy connection. We need to explicitly append `session_id=<session_id>` to `target_url` in `microservices/api_gateway/main.py`. This fixes the root cause of sticky routing failures.

2. **Fix Dead Code / Incorrect Import in `main.py`**:
   - Update `create_unified_graph` in `microservices/orchestrator_service/src/services/overmind/graph/main.py` to use the local `SupervisorNode` defined in `main.py` (which contains proper pronoun resolution `_resolve_query_from_history`) instead of importing it from `.supervisor`. I will remove the `ImportedSupervisorNode` alias entirely.

3. **Fix Context Amnesia in `GeneralKnowledgeNode`**:
   - Update `microservices/orchestrator_service/src/services/overmind/graph/general_knowledge.py` to import `format_conversation_history` from `.main` instead of `.supervisor`. The version in `.supervisor` severely truncates history to 6 messages, while `.main` correctly formats the full context window.

4. **Fix Raw Message Overrides (Query Destruction)**:
   - In both `GeneralKnowledgeNode` (`microservices/orchestrator_service/src/services/overmind/graph/general_knowledge.py`) and `ChatFallbackNode` (`microservices/orchestrator_service/src/services/overmind/graph/main.py`), remove the code blocks that overwrite the resolved `query` with the raw `messages[-1].content` if it thinks it's empty. This destroys the resolved query (where pronouns were fixed by the supervisor).

5. **Fix Manual Agent Context Handling**:
   - Update `microservices/orchestrator_service/src/api/routes.py` to pass dictionary-formatted history to `OrchestratorAgent` by using `_build_graph_messages_manual(hydrated_messages)` instead of passing LangChain objects directly, which causes context amnesia for manual agents.

6. **Complete pre-commit steps**:
   - Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.

7. **Submit the change**.
