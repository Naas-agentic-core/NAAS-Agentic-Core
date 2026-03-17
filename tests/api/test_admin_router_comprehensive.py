"""Comprehensive tests for Admin router."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.api.routers.admin import (
    get_ai_client,
    get_current_user_id,
    get_db,
    router,
)
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


def test_chat_stream_ws_not_admin(app):
    client = TestClient(app)
    mock_actor = MagicMock(spec=User)
    mock_actor.is_active = True
    mock_actor.is_admin = False

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    app.dependency_overrides[get_db] = lambda: mock_db
    # Mock extract_websocket_auth to return a token
    with patch(
        "app.api.routers.admin.extract_websocket_auth",
        return_value=("valid_token", "json"),
    ):
        with patch("app.api.routers.admin.decode_user_id", return_value=1):
            with client.websocket_connect("/admin/api/chat/ws") as websocket:
                data = websocket.receive_json()
                assert data["type"] == "error"
                assert "Standard accounts" in data["payload"]["details"]


def test_chat_stream_ws_empty_question(app):
    client = TestClient(app)
    mock_actor = MagicMock(spec=User)
    mock_actor.is_active = True
    mock_actor.is_admin = True

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    app.dependency_overrides[get_db] = lambda: mock_db
    with patch(
        "app.api.routers.admin.extract_websocket_auth",
        return_value=("valid_token", "json"),
    ):
        with patch("app.api.routers.admin.decode_user_id", return_value=1):
            with client.websocket_connect("/admin/api/chat/ws") as websocket:
                websocket.send_json({"question": ""})
                data = websocket.receive_json()
                assert data["type"] == "error"
                assert "Question is required" in data["payload"]["details"]


def test_chat_stream_ws_orchestrator_error(app):
    client = TestClient(app)
    mock_actor = MagicMock(spec=User)
    mock_actor.is_active = True
    mock_actor.is_admin = True

    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    app.dependency_overrides[get_db] = lambda: mock_db

    def mock_dependency_factory():
        return MagicMock()

    app.dependency_overrides[get_ai_client] = mock_dependency_factory
    with patch(
        "app.api.routers.admin.extract_websocket_auth",
        return_value=("valid_token", "json"),
    ):
        with patch("app.api.routers.admin.decode_user_id", return_value=1):
            with patch(
                "app.api.routers.admin.orchestrator_client.chat_with_agent",
                side_effect=RuntimeError("Orchestrator error"),
            ):
                with client.websocket_connect("/admin/api/chat/ws") as websocket:
                    websocket.send_json({"question": "test"})
                    data = websocket.receive_json()
                    assert data["type"] == "error"
                    assert "Orchestrator error" in data["payload"]["details"]
