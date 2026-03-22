"""Comprehensive tests for Admin router."""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routers.admin import (
    get_current_user_id,
    router,
)
from app.core.database import get_db
from app.core.domain.user import User


@pytest.fixture
def app():
    app = FastAPI()
    app.include_router(router)
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


@pytest.fixture
def mock_db():
    return AsyncMock()


def test_get_actor_user_not_found(client, mock_db):
    client.app.dependency_overrides[get_db] = lambda: mock_db
    client.app.dependency_overrides[get_current_user_id] = lambda: 999
    mock_db.get.return_value = None

    response = client.get("/admin/api/chat/latest")
    assert response.status_code == 401
    assert "User not found" in response.json()["detail"]


def test_get_actor_user_inactive(client, mock_db):
    client.app.dependency_overrides[get_db] = lambda: mock_db
    client.app.dependency_overrides[get_current_user_id] = lambda: 1

    user = MagicMock(spec=User)
    user.is_active = False
    mock_db.get.return_value = user

    response = client.get("/admin/api/chat/latest")
    assert response.status_code == 403
    assert "User inactive" in response.json()["detail"]


def test_get_latest_chat_not_admin(client, mock_db):
    client.app.dependency_overrides[get_db] = lambda: mock_db
    client.app.dependency_overrides[get_current_user_id] = lambda: 1

    user = MagicMock(spec=User)
    user.is_active = True
    user.is_admin = False
    mock_db.get.return_value = user
    # Mock refresh and expunge
    mock_db.refresh = AsyncMock()
    mock_db.expunge = MagicMock()

    response = client.get("/admin/api/chat/latest")
    assert response.status_code == 403
    assert "Admin access required" in response.json()["detail"]
