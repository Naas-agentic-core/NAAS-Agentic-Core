"""Extra tests for Admin router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, WebSocketDisconnect
from fastapi.testclient import TestClient

from app.api.routers.admin import router
from app.deps.auth import ADMIN_ROLE
from app.infrastructure.clients.user_client import user_client


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.mark.asyncio
async def test_get_admin_user_count_success(client):
    from app.deps.auth import CurrentUser, get_current_user

    mock_user_obj = MagicMock()
    mock_user_obj.id = 1
    mock_user_obj.is_admin = True
    current_user = CurrentUser(user=mock_user_obj, roles=[ADMIN_ROLE], permissions=set())

    client.app.dependency_overrides[get_current_user] = lambda: current_user

    with patch.object(user_client, "get_user_count", AsyncMock(return_value=100)):
        response = client.get("/admin/users/count")
        assert response.status_code == 200
        assert response.json()["count"] == 100


@pytest.mark.asyncio
async def test_get_admin_user_count_failure(client):
    from app.deps.auth import CurrentUser, get_current_user

    mock_user_obj = MagicMock()
    mock_user_obj.id = 1
    mock_user_obj.is_admin = True
    current_user = CurrentUser(user=mock_user_obj, roles=[ADMIN_ROLE], permissions=set())

    client.app.dependency_overrides[get_current_user] = lambda: current_user

    with patch.object(
        user_client, "get_user_count", AsyncMock(side_effect=Exception("Service Down"))
    ):
        response = client.get("/admin/users/count")
        assert response.status_code == 503
        assert "User Service unavailable" in response.json()["detail"]


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_admin_ws_auth_fail(app):
    client = TestClient(app)
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/admin/api/chat/ws"):
            pass
    assert exc.value.code == 4401


# WebSocket testing in FastAPI TestClient is synchronous-looking but handles async.
# Testing the full stream might be complex, so let's at least cover the auth failure paths.
