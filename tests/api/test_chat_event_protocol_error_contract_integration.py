"""اختبارات تكاملية لعقد الأخطاء الموحّد في قنوات WebSocket."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.routers.admin import get_db as get_admin_db
from app.api.routers.customer_chat import get_db as get_customer_db


def _make_session_factory(mock_actor):
    """Return an async-context-manager factory that yields a mock DB with the given actor.

    Both WS handlers call ``async_session_factory()`` *directly* (not via
    ``Depends``), so ``dependency_overrides`` has no effect on them.  Patching
    the module-level ``async_session_factory`` with this factory ensures the
    handler sees the correct mock actor instead of the real bootstrap admin.
    """
    mock_db = AsyncMock()
    mock_db.get = AsyncMock(return_value=mock_actor)
    mock_db.expunge = MagicMock()

    @asynccontextmanager
    async def _factory(*_args, **_kwargs):
        yield mock_db

    return _factory


@pytest.mark.asyncio
async def test_customer_ws_admin_actor_emits_assistant_error_when_flag_enabled(test_app) -> None:
    """يتحقق من أن منع حساب admin على قناة العملاء يُرسل assistant_error بالعقد الموحّد."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=True)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

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

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        with patch(
            "app.api.routers.admin.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.admin.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.admin.async_session_factory",
                    _make_session_factory(mock_actor),
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

    test_app.dependency_overrides[get_admin_db] = lambda: mock_db

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
    """يتحقق من تحويل فشل dispatch في قناة العملاء إلى assistant_error موحّد.

    The boundary service raises HTTPException during the persistence phase of
    dispatch, which is caught by the WS handler and converted to assistant_error
    before any conversation_init is emitted.
    """
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=False)

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        with patch(
            "app.api.routers.customer_chat.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.customer_chat.async_session_factory",
                    _make_session_factory(mock_actor),
                ):
                    with patch(
                        "app.api.routers.customer_chat.CustomerChatBoundaryService"
                    ) as mock_svc:
                        mock_svc.return_value.get_or_create_conversation = AsyncMock(
                            side_effect=HTTPException(status_code=422, detail="dispatch failed")
                        )
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
    """يتحقق من تحويل فشل dispatch في قناة الإدارة إلى assistant_error موحّد.

    The boundary service raises HTTPException during the persistence phase of
    dispatch, which is caught by the WS handler and converted to assistant_error
    before any conversation_init is emitted.
    """
    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        with patch(
            "app.api.routers.admin.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.admin.decode_user_id", return_value=1):
                with patch("app.api.routers.admin.AdminChatBoundaryService") as mock_admin_svc:
                    mock_admin_svc.return_value.get_or_create_conversation = AsyncMock(
                        side_effect=HTTPException(status_code=409, detail="admin dispatch failed")
                    )
                    with TestClient(test_app) as client:
                        with client.websocket_connect("/admin/api/chat/ws") as websocket:
                            websocket.send_json({"question": "hello"})
                            payload = websocket.receive_json()

    assert payload["type"] == "assistant_error"
    assert payload["contract_version"] == "v1"
    assert payload["payload"]["status_code"] == 409
    assert payload["payload"]["details"] == "admin dispatch failed"
