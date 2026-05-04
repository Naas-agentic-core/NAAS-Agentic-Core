"""اختبارات تكاملية لعقد الأخطاء الموحّد في قنوات WebSocket."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routers.admin import get_db as get_admin_db
from app.api.routers.customer_chat import get_db as get_customer_db


@pytest.mark.asyncio
async def test_customer_ws_admin_actor_emits_assistant_error_when_flag_enabled(test_app) -> None:
    """يتحقق من أن منع حساب admin على قناة العملاء يُرسل assistant_error بالعقد الموحّد."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=True)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor
    mock_db.expunge = lambda _actor: None

    test_app.dependency_overrides[get_customer_db] = lambda: mock_db

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        with patch(
            "app.api.routers.customer_chat.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
                with TestClient(test_app) as client:
                    with client.websocket_connect("/api/chat/ws") as websocket:
                        payload = websocket.receive_json()

    assert payload["type"] == "assistant_error"
    assert payload["contract_version"] == "v1"
    assert payload["payload"]["status_code"] == 403
    assert "Admin accounts" in payload["payload"]["details"]


@pytest.mark.asyncio
async def test_admin_ws_non_admin_actor_emits_assistant_error_when_flag_enabled(test_app) -> None:
    """يتحقق من أن منع الحساب العادي على قناة الإدارة يُرسل assistant_error بالعقد الموحّد."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=False)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor
    mock_db.expunge = lambda _actor: None

    class _MockSessionContext:
        def __init__(self, db: AsyncMock) -> None:
            self._db = db

        async def __aenter__(self) -> AsyncMock:
            return self._db

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        with patch(
            "app.api.routers.admin.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.admin.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.admin.async_session_factory",
                    return_value=_MockSessionContext(mock_db),
                ):
                    with TestClient(test_app) as client:
                        with client.websocket_connect("/admin/api/chat/ws") as websocket:
                            payload = websocket.receive_json()

    assert payload["type"] == "assistant_error"
    assert payload["contract_version"] == "v1"
    assert payload["payload"]["status_code"] == 403
    assert "Standard accounts" in payload["payload"]["details"]


@pytest.mark.asyncio
async def test_admin_ws_empty_question_emits_assistant_error_when_flag_enabled(test_app) -> None:
    """يتحقق من أن خطأ السؤال الفارغ في قناة الإدارة يُرسل assistant_error بالعقد الموحّد."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=True)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor
    mock_db.expunge = lambda _actor: None

    class _MockSessionContext:
        def __init__(self, db: AsyncMock) -> None:
            self._db = db

        async def __aenter__(self) -> AsyncMock:
            return self._db

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        with patch(
            "app.api.routers.admin.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.admin.decode_user_id", return_value=1):
                with TestClient(test_app) as client:
                    with client.websocket_connect("/admin/api/chat/ws") as websocket:
                        websocket.send_json({"question": ""})
                        payload = websocket.receive_json()

    assert payload["type"] == "assistant_error"
    assert payload["contract_version"] == "v1"
    assert payload["payload"]["details"] == "Question is required."


@pytest.mark.asyncio
async def test_customer_ws_dispatch_http_exception_emits_assistant_error_when_flag_enabled(
    test_app,
) -> None:
    """يتحقق من تحويل فشل dispatch في قناة العملاء إلى assistant_error موحّد."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=False)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    test_app.dependency_overrides[get_customer_db] = lambda: mock_db

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        with patch(
            "app.api.routers.customer_chat.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.customer_chat.orchestrator_client.chat_with_agent",
                    side_effect=HTTPException(status_code=422, detail="dispatch failed"),
                ):
                    with TestClient(test_app) as client:
                        with client.websocket_connect("/api/chat/ws") as websocket:
                            websocket.send_json({"question": "hello"})
                            payload = websocket.receive_json()

    assert payload["type"] == "assistant_error"
    assert payload["contract_version"] == "v1"
    assert payload["payload"]["status_code"] == 422
    assert payload["payload"]["details"] == "dispatch failed"


@pytest.mark.asyncio
async def test_admin_ws_dispatch_http_exception_emits_assistant_error_when_flag_enabled(
    test_app,
) -> None:
    """يتحقق من تحويل فشل dispatch في قناة الإدارة إلى assistant_error موحّد."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=True)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor
    mock_db.expunge = lambda _actor: None

    class _MockSessionContext:
        def __init__(self, db: AsyncMock) -> None:
            self._db = db

        async def __aenter__(self) -> AsyncMock:
            return self._db

        async def __aexit__(self, exc_type, exc, tb) -> None:
            return None

    test_app.dependency_overrides[get_admin_db] = lambda: mock_db

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        with patch(
            "app.api.routers.admin.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.admin.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.admin.async_session_factory",
                    return_value=_MockSessionContext(mock_db),
                ):
                    with patch(
                        "app.api.routers.admin.orchestrator_client.chat_with_agent",
                        side_effect=HTTPException(status_code=409, detail="admin dispatch failed"),
                    ):
                        with TestClient(test_app) as client:
                            with client.websocket_connect("/admin/api/chat/ws") as websocket:
                                websocket.send_json({"question": "hello"})
                                payload = websocket.receive_json()

    assert payload["type"] == "assistant_error"
    assert payload["contract_version"] == "v1"
    assert payload["payload"]["status_code"] == 409
    assert payload["payload"]["details"] == "admin dispatch failed"
