"""اختبارات تكاملية لسلوك راية بروتوكول أحداث الدردشة عبر قنوات WebSocket."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.api.routers.admin import get_db as get_admin_db
from app.api.routers.customer_chat import get_db as get_customer_db


async def _stream_single_delta() -> AsyncGenerator[dict[str, object], None]:
    """يبث حدثًا واحدًا بصيغة delta لاختبار التطبيع."""
    yield {"type": "delta", "payload": {"content": "chunk"}}


async def _stream_contextual_response(
    *, history_messages: list[dict[str, str]] | None = None
) -> AsyncGenerator[dict[str, object], None]:
    """يبني رداً يعتمد صراحةً على التاريخ الممرَّر لاختبار استمرارية السياق سلوكياً."""
    history = history_messages or []
    previous_assistant = ""
    for item in reversed(history):
        if item.get("role") == "assistant":
            previous_assistant = item.get("content", "")
            break

    content = f"CONTEXT_OK::{previous_assistant}" if previous_assistant else "CONTEXT_MISSING"
    yield {"type": "assistant_final", "payload": {"content": content}}
    yield {"type": "complete", "payload": {}}


def _mock_async_session_context(mock_actor: SimpleNamespace) -> MagicMock:
    """ينشئ مدير سياق لجلسة قاعدة البيانات يحاكي جلب المستخدم وفصل الكيان."""
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor
    mock_db.expunge = MagicMock()
    manager = MagicMock()
    manager.__aenter__.return_value = mock_db
    manager.__aexit__.return_value = None
    return manager


def _drain_until_complete(websocket, *, max_events: int = 20) -> list[dict[str, object]]:
    """يقرأ أحداث websocket حتى complete لضمان اختبار دورة الرسالة كاملة."""
    events: list[dict[str, object]] = []
    for _ in range(max_events):
        payload = websocket.receive_json()
        events.append(payload)
        if payload.get("type") == "complete":
            break
    return events


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_customer_ws_legacy_protocol_when_flag_disabled(test_app) -> None:
    """يتحقق من بقاء مخطط legacy في قناة العملاء عند تعطيل الراية."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=False)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    test_app.dependency_overrides[get_customer_db] = lambda: mock_db

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "0"}, clear=False):
        customer_service = AsyncMock()
        customer_service.get_or_create_conversation.return_value = SimpleNamespace(id=11)
        customer_service.save_message.return_value = None
        with patch(
            "app.api.routers.customer_chat.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.customer_chat.async_session_factory",
                    return_value=_mock_async_session_context(mock_actor),
                ):
                    with patch(
                        "app.api.routers.customer_chat.CustomerChatBoundaryService",
                        return_value=customer_service,
                    ):
                        with patch(
                            "app.api.routers.customer_chat.orchestrator_client.chat_with_agent",
                            return_value=_stream_single_delta(),
                        ):
                            with TestClient(test_app) as client:
                                with client.websocket_connect("/api/chat/ws") as websocket:
                                    websocket.send_json({"question": "hello"})
                                    _conversation_init = websocket.receive_json()
                                    delta_event = websocket.receive_json()

    assert delta_event["type"] == "delta"
    assert delta_event["payload"]["content"] == "chunk"
    assert "contract_version" not in delta_event


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_customer_ws_unified_protocol_when_flag_enabled(test_app) -> None:
    """يتحقق من تفعيل العقد الموحّد في قناة العملاء عند تشغيل الراية."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=False)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    test_app.dependency_overrides[get_customer_db] = lambda: mock_db

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        customer_service = AsyncMock()
        customer_service.get_or_create_conversation.return_value = SimpleNamespace(id=12)
        customer_service.save_message.return_value = None
        with patch(
            "app.api.routers.customer_chat.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.customer_chat.async_session_factory",
                    return_value=_mock_async_session_context(mock_actor),
                ):
                    with patch(
                        "app.api.routers.customer_chat.CustomerChatBoundaryService",
                        return_value=customer_service,
                    ):
                        with patch(
                            "app.api.routers.customer_chat.orchestrator_client.chat_with_agent",
                            return_value=_stream_single_delta(),
                        ):
                            with TestClient(test_app) as client:
                                with client.websocket_connect("/api/chat/ws") as websocket:
                                    websocket.send_json({"question": "hello"})
                                    _conversation_init = websocket.receive_json()
                                    delta_event = websocket.receive_json()

    assert delta_event["type"] == "assistant_delta"
    assert delta_event["contract_version"] == "v1"
    assert delta_event["payload"]["content"] == "chunk"


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_admin_ws_legacy_protocol_when_flag_disabled(test_app) -> None:
    """يتحقق من بقاء مخطط legacy في قناة الإدارة عند تعطيل الراية."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=True)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    test_app.dependency_overrides[get_admin_db] = lambda: mock_db

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "0"}, clear=False):
        admin_service = AsyncMock()
        admin_service.get_or_create_conversation.return_value = SimpleNamespace(id=21)
        admin_service.save_message.return_value = None
        with patch(
            "app.api.routers.admin.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.admin.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.admin.async_session_factory",
                    return_value=_mock_async_session_context(mock_actor),
                ):
                    with patch(
                        "app.api.routers.admin.AdminChatBoundaryService",
                        return_value=admin_service,
                    ):
                        with patch(
                            "app.api.routers.admin.orchestrator_client.chat_with_agent",
                            return_value=_stream_single_delta(),
                        ):
                            with TestClient(test_app) as client:
                                with client.websocket_connect("/admin/api/chat/ws") as websocket:
                                    websocket.send_json({"question": "hello"})
                                    _conversation_init = websocket.receive_json()
                                    delta_event = websocket.receive_json()

    assert delta_event["type"] == "delta"
    assert delta_event["payload"]["content"] == "chunk"
    assert "contract_version" not in delta_event


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_admin_ws_unified_protocol_when_flag_enabled(test_app) -> None:
    """يتحقق من تفعيل العقد الموحّد في قناة الإدارة عند تشغيل الراية."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=True)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor

    test_app.dependency_overrides[get_admin_db] = lambda: mock_db

    with patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"}, clear=False):
        admin_service = AsyncMock()
        admin_service.get_or_create_conversation.return_value = SimpleNamespace(id=22)
        admin_service.save_message.return_value = None
        with patch(
            "app.api.routers.admin.extract_websocket_auth",
            return_value=("valid_token", "json"),
        ):
            with patch("app.api.routers.admin.decode_user_id", return_value=1):
                with patch(
                    "app.api.routers.admin.async_session_factory",
                    return_value=_mock_async_session_context(mock_actor),
                ):
                    with patch(
                        "app.api.routers.admin.AdminChatBoundaryService",
                        return_value=admin_service,
                    ):
                        with patch(
                            "app.api.routers.admin.orchestrator_client.chat_with_agent",
                            return_value=_stream_single_delta(),
                        ):
                            with TestClient(test_app) as client:
                                with client.websocket_connect("/admin/api/chat/ws") as websocket:
                                    websocket.send_json({"question": "hello"})
                                    _conversation_init = websocket.receive_json()
                                    delta_event = websocket.receive_json()

    assert delta_event["type"] == "assistant_delta"
    assert delta_event["contract_version"] == "v1"
    assert delta_event["payload"]["content"] == "chunk"


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_customer_ws_forwards_recent_history_messages_to_orchestrator(test_app) -> None:
    """يتحقق من تمرير سجل الرسائل الحديثة إلى Orchestrator لضمان استمرارية السياق."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=False)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor
    test_app.dependency_overrides[get_customer_db] = lambda: mock_db

    customer_service = AsyncMock()
    customer_service.get_or_create_conversation.return_value = SimpleNamespace(id=31)
    customer_service.save_message.return_value = None
    customer_service.get_chat_history.return_value = [
        {"role": "user", "content": "السؤال السابق"},
        {"role": "assistant", "content": "الإجابة السابقة"},
        {"role": "user", "content": "اشرح الإجابة السابقة"},
    ]

    chat_with_agent_mock = MagicMock(return_value=_stream_single_delta())

    with patch(
        "app.api.routers.customer_chat.extract_websocket_auth",
        return_value=("valid_token", "json"),
    ):
        with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
            with patch(
                "app.api.routers.customer_chat.async_session_factory",
                return_value=_mock_async_session_context(mock_actor),
            ):
                with patch(
                    "app.api.routers.customer_chat.CustomerChatBoundaryService",
                    return_value=customer_service,
                ):
                    with patch(
                        "app.api.routers.customer_chat.orchestrator_client.chat_with_agent",
                        chat_with_agent_mock,
                    ):
                        with TestClient(test_app) as client:
                            with client.websocket_connect("/api/chat/ws") as websocket:
                                websocket.send_json({"question": "اشرح الإجابة السابقة"})
                                _conversation_init = websocket.receive_json()
                                _delta_event = websocket.receive_json()

    forwarded_history = chat_with_agent_mock.call_args.kwargs["history_messages"]
    assert forwarded_history == customer_service.get_chat_history.return_value


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_admin_ws_forwards_recent_history_messages_to_orchestrator(test_app) -> None:
    """يتحقق من تمرير سجل الإدارة الحديث حتى لا تُعامل الأسئلة كجلسات منفصلة."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=True)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor
    test_app.dependency_overrides[get_admin_db] = lambda: mock_db

    admin_service = AsyncMock()
    admin_service.get_or_create_conversation.return_value = SimpleNamespace(id=41)
    admin_service.save_message.return_value = None
    admin_service.get_chat_history.return_value = [
        {"role": "user", "content": "first"},
        {"role": "assistant", "content": "previous answer"},
        {"role": "user", "content": "explain previous answer"},
    ]

    chat_with_agent_mock = MagicMock(return_value=_stream_single_delta())

    with patch(
        "app.api.routers.admin.extract_websocket_auth",
        return_value=("valid_token", "json"),
    ):
        with patch("app.api.routers.admin.decode_user_id", return_value=1):
            with patch(
                "app.api.routers.admin.async_session_factory",
                return_value=_mock_async_session_context(mock_actor),
            ):
                with patch(
                    "app.api.routers.admin.AdminChatBoundaryService",
                    return_value=admin_service,
                ):
                    with patch(
                        "app.api.routers.admin.orchestrator_client.chat_with_agent",
                        chat_with_agent_mock,
                    ):
                        with TestClient(test_app) as client:
                            with client.websocket_connect("/admin/api/chat/ws") as websocket:
                                websocket.send_json({"question": "explain previous answer"})
                                _conversation_init = websocket.receive_json()
                                _delta_event = websocket.receive_json()

    forwarded_history = chat_with_agent_mock.call_args.kwargs["history_messages"]
    assert forwarded_history == admin_service.get_chat_history.return_value


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_customer_ws_followup_uses_previous_answer_context_behaviorally(test_app) -> None:
    """يتحقق سلوكياً أن سؤال المتابعة يستفيد من الإجابة السابقة داخل نفس المحادثة."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=False)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor
    test_app.dependency_overrides[get_customer_db] = lambda: mock_db

    customer_service = AsyncMock()
    customer_service.get_or_create_conversation.return_value = SimpleNamespace(id=51)
    customer_service.save_message.return_value = None
    customer_service.get_chat_history.side_effect = [
        [{"role": "user", "content": "السؤال الأول"}],
        [
            {"role": "user", "content": "السؤال الأول"},
            {"role": "assistant", "content": "الإجابة الأولى"},
            {"role": "user", "content": "اشرح الإجابة السابقة"},
        ],
    ]

    def _chat_with_agent_side_effect(**kwargs):
        return _stream_contextual_response(history_messages=kwargs.get("history_messages"))

    chat_with_agent_mock = MagicMock(side_effect=_chat_with_agent_side_effect)

    with patch(
        "app.api.routers.customer_chat.extract_websocket_auth",
        return_value=("valid_token", "json"),
    ):
        with patch("app.api.routers.customer_chat.decode_user_id", return_value=1):
            with patch(
                "app.api.routers.customer_chat.async_session_factory",
                return_value=_mock_async_session_context(mock_actor),
            ):
                with patch(
                    "app.api.routers.customer_chat.CustomerChatBoundaryService",
                    return_value=customer_service,
                ):
                    with patch(
                        "app.api.routers.customer_chat.orchestrator_client.chat_with_agent",
                        chat_with_agent_mock,
                    ):
                        with TestClient(test_app) as client:
                            with client.websocket_connect("/api/chat/ws") as websocket:
                                websocket.send_json({"question": "السؤال الأول"})
                                first_init = websocket.receive_json()
                                _first_events = _drain_until_complete(websocket)

                                websocket.send_json(
                                    {
                                        "question": "اشرح الإجابة السابقة",
                                        "conversation_id": first_init["payload"]["conversation_id"],
                                    }
                                )
                                _second_init = websocket.receive_json()
                                _second_turn_events = _drain_until_complete(websocket)

    assert len(chat_with_agent_mock.call_args_list) == 2
    first_history = chat_with_agent_mock.call_args_list[0].kwargs["history_messages"]
    second_history = chat_with_agent_mock.call_args_list[1].kwargs["history_messages"]

    assert all(item.get("role") != "assistant" for item in first_history)
    assert any(
        item.get("role") == "assistant" and item.get("content") == "الإجابة الأولى"
        for item in second_history
    )


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_admin_ws_followup_uses_previous_answer_context_behaviorally(test_app) -> None:
    """يتحقق سلوكياً أن سؤال المتابعة الإداري يستفيد من الإجابة السابقة داخل نفس المحادثة."""
    mock_actor = SimpleNamespace(id=1, is_active=True, is_admin=True)
    mock_db = AsyncMock()
    mock_db.get.return_value = mock_actor
    test_app.dependency_overrides[get_admin_db] = lambda: mock_db

    admin_service = AsyncMock()
    admin_service.get_or_create_conversation.return_value = SimpleNamespace(id=61)
    admin_service.save_message.return_value = None
    admin_service.get_chat_history.side_effect = [
        [{"role": "user", "content": "admin-first"}],
        [
            {"role": "user", "content": "admin-first"},
            {"role": "assistant", "content": "admin-previous-answer"},
            {"role": "user", "content": "explain previous admin answer"},
        ],
    ]

    def _chat_with_agent_side_effect(**kwargs):
        return _stream_contextual_response(history_messages=kwargs.get("history_messages"))

    chat_with_agent_mock = MagicMock(side_effect=_chat_with_agent_side_effect)

    with patch(
        "app.api.routers.admin.extract_websocket_auth",
        return_value=("valid_token", "json"),
    ):
        with patch("app.api.routers.admin.decode_user_id", return_value=1):
            with patch(
                "app.api.routers.admin.async_session_factory",
                return_value=_mock_async_session_context(mock_actor),
            ):
                with patch(
                    "app.api.routers.admin.AdminChatBoundaryService",
                    return_value=admin_service,
                ):
                    with patch(
                        "app.api.routers.admin.orchestrator_client.chat_with_agent",
                        chat_with_agent_mock,
                    ):
                        with TestClient(test_app) as client:
                            with client.websocket_connect("/admin/api/chat/ws") as websocket:
                                websocket.send_json({"question": "admin-first"})
                                first_init = websocket.receive_json()
                                _first_events = _drain_until_complete(websocket)

                                websocket.send_json(
                                    {
                                        "question": "explain previous admin answer",
                                        "conversation_id": first_init["payload"]["conversation_id"],
                                    }
                                )
                                _second_init = websocket.receive_json()
                                _second_turn_events = _drain_until_complete(websocket)

    assert len(chat_with_agent_mock.call_args_list) == 2
    first_history = chat_with_agent_mock.call_args_list[0].kwargs["history_messages"]
    second_history = chat_with_agent_mock.call_args_list[1].kwargs["history_messages"]

    assert all(item.get("role") != "assistant" for item in first_history)
    assert any(
        item.get("role") == "assistant" and item.get("content") == "admin-previous-answer"
        for item in second_history
    )
