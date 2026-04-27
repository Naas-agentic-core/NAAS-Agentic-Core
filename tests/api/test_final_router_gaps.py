"""Tests for final remaining gaps in API routers."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException, WebSocketDisconnect
from fastapi.testclient import TestClient

from app.api.routers.customer_chat import get_db
from app.api.routers.customer_chat import router as customer_router
from app.api.routers.ws_auth import (
    _extract_token_from_protocols,
    _parse_protocol_header,
    extract_websocket_auth,
)
from app.core.domain.user import User


@pytest.fixture
def customer_app():
    app = FastAPI()
    app.include_router(customer_router)
    return app


# --- Customer Chat Tests ---
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
def test_customer_ws_auth_fail(customer_app):
    client = TestClient(customer_app)
    with patch("app.api.routers.customer_chat.extract_websocket_auth", return_value=(None, None)):
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/api/chat/ws"):
                pass  # Already closed by server


@pytest.mark.skip(reason="Legacy monolith WS route disabled")
def test_customer_ws_decode_fail(customer_app):
    client = TestClient(customer_app)
    with patch(
        "app.api.routers.customer_chat.extract_websocket_auth", return_value=("token", "jwt")
    ):
        with patch("app.api.routers.customer_chat.decode_user_id", side_effect=HTTPException(401)):
            with pytest.raises(WebSocketDisconnect):
                with client.websocket_connect("/api/chat/ws"):
                    pass


@pytest.mark.skip(reason="Legacy monolith WS route disabled")
def test_customer_ws_admin(customer_app):
    client = TestClient(customer_app)
    mock_user = MagicMock(spec=User)
    mock_user.is_active = True
    mock_user.is_admin = True
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_user
    customer_app.dependency_overrides[get_db] = lambda: mock_db

    with patch(
        "app.api.routers.customer_chat.extract_websocket_auth", return_value=("token", "jwt")
    ):
        with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
            import pytest
            from starlette.websockets import WebSocketDisconnect

            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect("/api/chat/ws"):
                    pass
            assert exc.value.code == 4401


@pytest.mark.skip(reason="Legacy monolith WS route disabled")
def test_customer_ws_empty_question(customer_app):
    client = TestClient(customer_app)
    mock_user = MagicMock(spec=User)
    mock_user.is_active = True
    mock_user.is_admin = False
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_user
    customer_app.dependency_overrides[get_db] = lambda: mock_db

    with patch(
        "app.api.routers.customer_chat.extract_websocket_auth", return_value=("token", "jwt")
    ):
        with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
            import pytest
            from starlette.websockets import WebSocketDisconnect

            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect("/api/chat/ws"):
                    pass
            assert exc.value.code == 4401


# --- WS Auth Tests ---
def test_parse_protocol_header():
    assert _parse_protocol_header("jwt, token") == ["jwt", "token"]
    assert _parse_protocol_header("") == []


def test_extract_token_from_protocols():
    assert _extract_token_from_protocols(["jwt"]) is None
    assert _extract_token_from_protocols(["other"]) is None


def test_extract_websocket_auth_fallback_prod():
    mock_ws = MagicMock()
    mock_ws.headers = {}
    mock_ws.query_params = {"token": "fallback"}

    with patch("app.api.routers.ws_auth.get_settings") as mock_settings:
        mock_settings.return_value.ENVIRONMENT = "production"
        token, _proto = extract_websocket_auth(mock_ws)
        assert token is None


def test_extract_websocket_auth_success():
    mock_ws = MagicMock()
    mock_ws.headers = {"sec-websocket-protocol": "jwt, my_secret_token"}

    token, proto = extract_websocket_auth(mock_ws)
    assert token == "my_secret_token"
    assert proto == "jwt"
