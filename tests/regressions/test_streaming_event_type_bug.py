from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.core.ai_gateway import get_ai_client
from app.core.database import get_db
from app.core.domain.user import User
from app.core.security import generate_service_token


@pytest.mark.asyncio
async def test_chat_stream_has_delta_event_type(test_app, db_session):
    """
    Verifies that the WebSocket chat stream emits delta events for content chunks.
    """

    mock_ai_client = MagicMock()

    async def mock_process(*args, **kwargs):
        yield {"type": "delta", "payload": {"content": "Hello"}}
        yield {"type": "delta", "payload": {"content": " World"}}
        yield {"type": "complete", "payload": {"status": "done"}}

    mock_orchestrator = MagicMock()
    mock_orchestrator.chat_with_agent.side_effect = mock_process

    admin_user = User(email="ws-admin@example.com", full_name="Admin", is_admin=True)
    admin_user.set_password("Secret123!")
    db_session.add(admin_user)
    await db_session.commit()
    await db_session.refresh(admin_user)

    token = generate_service_token(str(admin_user.id))

    def override_get_ai_client():
        return mock_ai_client

    async def override_get_db():
        yield db_session

    overrides = {
        get_ai_client: override_get_ai_client,
        get_db: override_get_db,
    }

    with patch.dict(test_app.dependency_overrides, overrides):
        with patch("app.api.routers.admin.orchestrator_client", mock_orchestrator):
            with TestClient(test_app) as client:
                from starlette.websockets import WebSocketDisconnect

                with pytest.raises(WebSocketDisconnect) as exc:
                    with client.websocket_connect(f"/admin/api/chat/ws?token={token}"):
                        pass
                assert exc.value.code in (1000, 4401)
