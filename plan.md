1. **Delete Legacy WebSocket Endpoints in Monolith:**
   - In `app/api/routers/admin.py`, delete `chat_stream_ws` and its route `@router.websocket("/api/chat/ws")`.
   - In `app/api/routers/customer_chat.py`, delete `chat_stream_ws` and its route `@router.websocket("/ws")`.
   - Ensure to clean up any related unused imports in these files.

2. **Delete `MissionComplexHandler`:**
   - In `app/services/chat/handlers/strategy_handlers.py`, delete the `MissionComplexHandler` class completely.

3. **Remove references to `MissionComplexHandler`:**
   - In `app/services/chat/orchestrator.py`, remove `MissionComplexHandler` from the imports and the default handlers list.
   - In `tests/unit/test_orchestrator_unit.py` (if applicable), clean up any mock references that rely on `MissionComplexHandler`.
   - In any other identified files (like `app/services/overmind/planning/deep_indexer.py`), remove references/comments involving `MissionComplexHandler`.

4. **Verify Microservices Orchestrator Configuration:**
   - Confirm that `microservices/orchestrator_service/src/api/routes.py` properly handles both `/api/chat/ws` and `/admin/api/chat/ws` paths and routes "المهمة الخارقة" using LangGraph. It is already doing so based on `chat_ws_stategraph` and `admin_chat_ws_stategraph`.

5. **Complete pre-commit steps to ensure proper testing, verification, review, and reflection are done.**
   - Run tests and linting.
   - Verify frontend functionality and take screenshots.

6. **Submit:**
   - Submit the changes using a meaningful branch name and commit message.
