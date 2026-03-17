"""اختبارات إضافية لمسارات المسؤول بعد إيقاف WS المونوليثي."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.admin import router
from app.deps.auth import ADMIN_ROLE
from app.infrastructure.clients.user_client import user_client


@pytest.fixture
def app() -> FastAPI:
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.mark.asyncio
async def test_get_admin_user_count_success(client: TestClient) -> None:
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
async def test_get_admin_user_count_failure(client: TestClient) -> None:
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


def test_admin_ws_path_is_decommissioned(client: TestClient) -> None:
    """يتحقق من تعطيل WS المحلي للإدارة ومنع مسار split-brain."""

    response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404
