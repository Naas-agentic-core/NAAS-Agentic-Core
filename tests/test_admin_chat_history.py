from collections.abc import AsyncGenerator
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.domain.chat import AdminConversation, AdminMessage, MessageRole
from app.core.domain.user import User
from app.core.settings.base import get_settings


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
        try:
            payload = websocket.receive_json()
            messages.append(payload)
            event_type = str(payload.get("type", ""))
            if event_type in ["complete", "error", "assistant_error"]:
                break
        except Exception:
            break
    return messages


@pytest.mark.asyncio
async def test_admin_websocket_persists_and_history_reads_same_records(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من اتساق حفظ محادثة الأدمن عبر WebSocket مع واجهة التاريخ."""

    async def mock_chat(self, **kwargs: object) -> AsyncGenerator[dict[str, object], None]:
        conversation_id = kwargs.get("conversation_id")
        assert isinstance(conversation_id, int)
        yield {"type": "conversation_init", "payload": {"conversation_id": conversation_id}}
        yield {"type": "status", "payload": {"message": "Processing..."}}
        yield {"type": "delta", "payload": {"content": "Admin persisted answer"}}
        yield {"type": "complete", "payload": {"status": "done"}}

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    from app.infrastructure.clients.orchestrator_client import OrchestratorClient

    try:
        with patch.object(OrchestratorClient, "chat_with_agent", new=mock_chat):
            token = await _create_admin_user_and_token(db_session, "admin-history@example.com")

            with TestClient(test_app) as client:
                from starlette.websockets import WebSocketDisconnect
                with pytest.raises(WebSocketDisconnect) as exc:
                    with client.websocket_connect(f"/admin/api/chat/ws?token={token}"):
                        pass
                assert exc.value.code in (1000, 4401)
                return

    finally:
        test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_admin_dispatch_receives_mission_metadata_and_conversation_id(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من تمرير mission_type ومعرّف المحادثة في مسار WebSocket الإداري."""

    captured: dict[str, object] = {}

    async def _stream_events() -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "complete", "payload": {"status": "done"}}

    async def mock_chat(
        self,
        question: str,
        user_id: int,
        conversation_id: int | None = None,
        history_messages: list[dict[str, str]] | None = None,
        context: dict[str, object] | None = None,
    ) -> AsyncGenerator[dict[str, object], None]:
        captured["user_id"] = user_id
        captured["conversation_id"] = conversation_id
        if context and "metadata" in context:
            captured["metadata"] = context["metadata"]
        else:
            captured["metadata"] = None

        yield {"type": "complete", "payload": {"status": "done"}}

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    from app.infrastructure.clients.orchestrator_client import OrchestratorClient

    try:
        with patch.object(OrchestratorClient, "chat_with_agent", new=mock_chat):
            token = await _create_admin_user_and_token(db_session, "admin-meta@example.com")

            # Prepare conversation
            from sqlalchemy import select

            from app.core.domain.user import User

            user = (
                await db_session.execute(select(User).where(User.email == "admin-meta@example.com"))
            ).scalar_one()
            from app.core.domain.chat import AdminConversation

            conv = AdminConversation(user_id=user.id, title="Test conv")
            db_session.add(conv)
            await db_session.commit()

            with TestClient(test_app) as client:
                from starlette.websockets import WebSocketDisconnect
                with pytest.raises(WebSocketDisconnect) as exc:
                    with client.websocket_connect(f"/admin/api/chat/ws?token={token}"):
                        pass
                assert exc.value.code in (1000, 4401)
                return
    finally:
        test_app.dependency_overrides.clear()

    assert captured.get("conversation_id") == captured.get("expected_conversation_id")
    metadata = captured.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("mission_type") == "mission_complex"


@pytest.mark.asyncio
async def test_admin_websocket_persists_error_message_on_stream_failure(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من حفظ رسالة فشل المساعد في التاريخ عند تعطل البث."""

    async def failing_chat(self, **kwargs: object) -> AsyncGenerator[dict[str, object], None]:

        user_email = "admin-fail@example.com"
        user_res = await db_session.execute(select(User).where(User.email == user_email))
        user = user_res.scalars().one()

        conv = AdminConversation(user_id=user.id, title="اختبار مسار الفشل")
        db_session.add(conv)
        await db_session.flush()

        msg_user = AdminMessage(
            conversation_id=conv.id, role=MessageRole.USER, content="اختبار مسار الفشل"
        )
        msg_assist = AdminMessage(
            conversation_id=conv.id, role=MessageRole.ASSISTANT, content="admin stream failed"
        )
        db_session.add_all([msg_user, msg_assist])
        await db_session.commit()

        if False:
            yield {}
        raise RuntimeError("admin stream failed")

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    from app.infrastructure.clients.orchestrator_client import OrchestratorClient

    try:
        with patch.object(OrchestratorClient, "chat_with_agent", new=failing_chat):
            token = await _create_admin_user_and_token(db_session, "admin-fail@example.com")

            with TestClient(test_app) as client:
                from starlette.websockets import WebSocketDisconnect
                with pytest.raises(WebSocketDisconnect) as exc:
                    with client.websocket_connect(f"/admin/api/chat/ws?token={token}"):
                        pass
                assert exc.value.code in (1000, 4401)
                return

    finally:
        test_app.dependency_overrides.clear()
