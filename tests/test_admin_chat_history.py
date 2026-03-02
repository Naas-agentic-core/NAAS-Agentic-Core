from collections.abc import AsyncGenerator
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.domain.chat import AdminConversation, AdminMessage, MessageRole
from app.core.domain.user import User
from app.core.settings.base import get_settings
from app.services.chat.contracts import ChatDispatchRequest, ChatDispatchResult
from app.services.chat.dispatcher import ChatRoleDispatcher
from app.services.chat.orchestrator import ChatOrchestrator


async def _create_admin_user_and_token(db_session: AsyncSession, email: str) -> str:
    """ينشئ مستخدم إدارة للاختبار ويعيد رمز JWT صالحاً لمسار WebSocket وHTTP."""

    insert_statement = text(
        """
        INSERT INTO users (
            external_id,
            full_name,
            email,
            password_hash,
            is_admin,
            is_active,
            status
        )
        VALUES (:external_id, :full_name, :email, :password_hash, :is_admin, :is_active, :status)
        """
    )
    result = await db_session.execute(
        insert_statement,
        {
            "external_id": f"test-admin-{email}",
            "full_name": "Admin User",
            "email": email,
            "password_hash": "not-used-in-this-test",
            "is_admin": True,
            "is_active": True,
            "status": "active",
        },
    )
    await db_session.commit()

    user_id = int(result.lastrowid)
    payload = {
        "sub": str(user_id),
        "email": email,
        "is_admin": True,
        "role": "admin",
    }
    return jwt.encode(payload, get_settings().SECRET_KEY, algorithm="HS256")


def _consume_stream_until_terminal(websocket: object) -> list[dict[str, object]]:
    """يجمع أحداث البث الإداري حتى ظهور complete مع السماح بمرور error قبله."""

    messages: list[dict[str, object]] = []
    for _ in range(12):
        payload = websocket.receive_json()
        messages.append(payload)
        event_type = str(payload.get("type", ""))
        if event_type == "complete":
            break
    return messages


@pytest.mark.asyncio
async def test_admin_websocket_persists_and_history_reads_same_records(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من اتساق حفظ محادثة الأدمن عبر WebSocket مع واجهة التاريخ."""

    async def mock_process(self, **kwargs: object) -> AsyncGenerator[str, None]:
        yield "Admin persisted answer"

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with patch.object(ChatOrchestrator, "process", new=mock_process):
            token = await _create_admin_user_and_token(db_session, "admin-history@example.com")

            with TestClient(test_app) as client:
                with client.websocket_connect(f"/admin/api/chat/ws?token={token}") as websocket:
                    websocket.send_json({"question": "حلّل هذه المهمة"})
                    events = _consume_stream_until_terminal(websocket)

            user = (
                (
                    await db_session.execute(
                        select(User).where(User.email == "admin-history@example.com")
                    )
                )
                .scalars()
                .one()
            )
            conversation = (
                (
                    await db_session.execute(
                        select(AdminConversation).where(AdminConversation.user_id == user.id)
                    )
                )
                .scalars()
                .one()
            )
            messages = (
                (
                    await db_session.execute(
                        select(AdminMessage)
                        .where(AdminMessage.conversation_id == conversation.id)
                        .order_by(AdminMessage.id)
                    )
                )
                .scalars()
                .all()
            )

            async with AsyncClient(
                transport=ASGITransport(app=test_app),
                base_url="http://test",
            ) as ac:
                response = await ac.get(
                    f"/admin/api/conversations/{conversation.id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
    finally:
        test_app.dependency_overrides.clear()

    assert any(event.get("type") == "status" for event in events)
    assert any(event.get("type") == "conversation_init" for event in events)
    assert any(event.get("type") == "complete" for event in events)
    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER
    assert messages[1].role == MessageRole.ASSISTANT
    assert "Admin persisted answer" in messages[1].content

    assert response.status_code == 200
    payload = response.json()
    history_messages = payload.get("messages", [])
    assert any(msg.get("role") == "user" for msg in history_messages)
    assert any(msg.get("role") == "assistant" for msg in history_messages)
    assert any("Admin persisted answer" in str(msg.get("content", "")) for msg in history_messages)


@pytest.mark.asyncio
async def test_admin_dispatch_receives_mission_metadata_and_conversation_id(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من تمرير mission_type ومعرّف المحادثة في مسار WebSocket الإداري."""

    captured: dict[str, object] = {}

    async def _stream_events() -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "complete", "payload": {"status": "done"}}

    async def mock_dispatch(
        *,
        user: User,
        request: ChatDispatchRequest,
        dispatcher: ChatRoleDispatcher,
    ) -> ChatDispatchResult:
        captured["user_id"] = user.id
        captured["conversation_id"] = getattr(request, "conversation_id", None)
        captured["metadata"] = getattr(request, "metadata", None)
        return ChatDispatchResult(status_code=200, stream=_stream_events())

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with patch.object(ChatOrchestrator, "dispatch", side_effect=mock_dispatch):
            token = await _create_admin_user_and_token(db_session, "admin-meta@example.com")

            with TestClient(test_app) as client:
                with client.websocket_connect(f"/admin/api/chat/ws?token={token}") as websocket:
                    websocket.send_json(
                        {
                            "question": "Run admin mission",
                            "conversation_id": 77,
                            "mission_type": "mission_complex",
                        }
                    )
                    _consume_stream_until_terminal(websocket)
    finally:
        test_app.dependency_overrides.clear()

    assert captured.get("conversation_id") == 77
    metadata = captured.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("mission_type") == "mission_complex"


@pytest.mark.asyncio
async def test_admin_websocket_persists_error_message_on_stream_failure(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من حفظ رسالة فشل المساعد في التاريخ عند تعطل البث."""

    async def failing_process(self, **kwargs: object) -> AsyncGenerator[str, None]:
        if False:
            yield "unused"
        raise RuntimeError("admin stream failed")

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with patch.object(ChatOrchestrator, "process", new=failing_process):
            token = await _create_admin_user_and_token(db_session, "admin-fail@example.com")

            with TestClient(test_app) as client:
                with client.websocket_connect(f"/admin/api/chat/ws?token={token}") as websocket:
                    websocket.send_json({"question": "اختبار مسار الفشل"})
                    events = _consume_stream_until_terminal(websocket)

            user = (
                (
                    await db_session.execute(
                        select(User).where(User.email == "admin-fail@example.com")
                    )
                )
                .scalars()
                .one()
            )
            conversation = (
                (
                    await db_session.execute(
                        select(AdminConversation).where(AdminConversation.user_id == user.id)
                    )
                )
                .scalars()
                .one()
            )

            async with AsyncClient(
                transport=ASGITransport(app=test_app),
                base_url="http://test",
            ) as ac:
                response = await ac.get(
                    f"/admin/api/conversations/{conversation.id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
    finally:
        test_app.dependency_overrides.clear()

    assert any(event.get("type") == "status" for event in events)
    assert any(event.get("type") == "error" for event in events)
    assert any(event.get("type") == "complete" for event in events)

    assert response.status_code == 200
    payload = response.json()
    history_messages = payload.get("messages", [])
    assert any(msg.get("role") == "user" for msg in history_messages)
    assert any(msg.get("role") == "assistant" for msg in history_messages)
    assert any("admin stream failed" in str(msg.get("content", "")) for msg in history_messages)
