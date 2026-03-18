"""اختبارات تكاملية لسلوك راية بروتوكول أحداث الدردشة عبر قنوات WebSocket."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routers.admin import get_db as get_admin_db
from app.api.routers.customer_chat import get_db as get_customer_db


async def _stream_single_delta() -> AsyncGenerator[dict[str, object], None]:
    """يبث حدثًا واحدًا بصيغة delta لاختبار التطبيع."""
    yield {"type": "delta", "payload": {"content": "chunk"}}


@pytest.mark.asyncio
async def test_customer_ws_legacy_protocol_when_flag_disabled(test_app) -> None:
    """يتحقق من بقاء مخطط legacy في قناة العملاء عند تعطيل الراية."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=False)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    test_app.dependency_overrides[get_customer_db] = lambda: mock_db

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "0"}, clear=False):
        with patch(
            "app.api.routers.customer_chat.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.customer_chat.orchestrator_client.chat_with_agent",
                    return_value=_stream_single_delta(),
                ):
                    with TestClient(test_app) as client:
                        with client.websocket_connect("/api/chat/ws") as websocket:
                            websocket.send_json({"question": "hello"})
                            delta_event = websocket.receive_json()

    assert delta_event["type"] == "delta"
    assert delta_event["payload"]["content"] == "chunk"
    assert "contract_version" not in delta_event


@pytest.mark.asyncio
async def test_customer_ws_unified_protocol_when_flag_enabled(test_app) -> None:
    """يتحقق من تفعيل العقد الموحّد في قناة العملاء عند تشغيل الراية."""
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
                    return_value=_stream_single_delta(),
                ):
                    with TestClient(test_app) as client:
                        with client.websocket_connect("/api/chat/ws") as websocket:
                            websocket.send_json({"question": "hello"})
                            delta_event = websocket.receive_json()

    assert delta_event["type"] == "assistant_delta"
    assert delta_event["contract_version"] == "v1"
    assert delta_event["payload"]["content"] == "chunk"


@pytest.mark.asyncio
async def test_admin_ws_legacy_protocol_when_flag_disabled(test_app) -> None:
    """يتحقق من بقاء مخطط legacy في قناة الإدارة عند تعطيل الراية."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=True)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    test_app.dependency_overrides[get_admin_db] = lambda: mock_db

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "0"}, clear=False):
        with patch(
            "app.api.routers.admin.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.admin.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.admin.orchestrator_client.chat_with_agent",
                    return_value=_stream_single_delta(),
                ):
                    with TestClient(test_app) as client:
                        with client.websocket_connect("/admin/api/chat/ws") as websocket:
                            websocket.send_json({"question": "hello"})
                            delta_event = websocket.receive_json()

    assert delta_event["type"] == "delta"
    assert delta_event["payload"]["content"] == "chunk"
    assert "contract_version" not in delta_event


@pytest.mark.asyncio
async def test_admin_ws_unified_protocol_when_flag_enabled(test_app) -> None:
    """يتحقق من تفعيل العقد الموحّد في قناة الإدارة عند تشغيل الراية."""
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
                with patch(
                    "app.api.routers.admin.orchestrator_client.chat_with_agent",
                    return_value=_stream_single_delta(),
                ):
                    with TestClient(test_app) as client:
                        with client.websocket_connect("/admin/api/chat/ws") as websocket:
                            websocket.send_json({"question": "hello"})
                            delta_event = websocket.receive_json()

    assert delta_event["type"] == "assistant_delta"
    assert delta_event["contract_version"] == "v1"
    assert delta_event["payload"]["content"] == "chunk"
