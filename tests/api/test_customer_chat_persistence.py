from collections.abc import AsyncGenerator
from unittest.mock import patch

import jwt
import pytest
from fastapi.testclient import TestClient
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.domain.chat import CustomerConversation
from app.core.domain.models import CustomerMessage, MessageRole
from app.core.domain.user import User
from app.core.settings.base import get_settings
from app.services.chat.contracts import ChatDispatchRequest, ChatDispatchResult
from app.services.chat.dispatcher import ChatRoleDispatcher
from app.services.chat.orchestrator import ChatOrchestrator


async def _create_user_and_token(db_session: AsyncSession, email: str) -> str:
    """ينشئ مستخدم اختبار مباشرةً ويعيد رمز JWT صالحًا دون الاعتماد على خدمات خارجية."""

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
            "external_id": f"test-{email}",
            "full_name": "Student User",
            "email": email,
            "password_hash": "not-used-in-this-test",
            "is_admin": False,
            "is_active": True,
            "status": "active",
        },
    )
    await db_session.commit()

    user_id = int(result.lastrowid)
    return jwt.encode({"sub": str(user_id)}, get_settings().SECRET_KEY, algorithm="HS256")


def _consume_stream_until_terminal(websocket: object) -> list[dict[str, object]]:
    """يجمع أحداث البث حتى ظهور حدث نهائي أو رسالة خطأ."""

    messages: list[dict[str, object]] = []
    for _ in range(8):
        payload = websocket.receive_json()
        messages.append(payload)
        event_type = str(payload.get("type", ""))
        if event_type in {
            "assistant_final",
            "assistant_error",
            "assistant_fallback",
            "error",
            "complete",
        }:
            break
    return messages



@pytest.mark.asyncio
async def test_customer_chat_stream_delivers_final_message(
    test_app, db_session: AsyncSession
) -> None:
    async def _stream_events() -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "conversation_init", "payload": {"conversation_id": 1, "title": "t"}}
        yield {"type": "delta", "payload": {"content": "Hello learner"}}
        yield {"type": "complete", "payload": {"status": "done"}}

    async def mock_dispatch(**kwargs: object) -> ChatDispatchResult:
        return ChatDispatchResult(status_code=200, stream=_stream_events())

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with patch.object(ChatOrchestrator, "dispatch", side_effect=mock_dispatch):
            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test"):
                token = await _create_user_and_token(db_session, "student-chat@example.com")

            with TestClient(test_app) as client:
                with client.websocket_connect(f"/api/chat/ws?token={token}") as websocket:
                    websocket.send_json({"question": "Explain math vectors"})
                    messages = _consume_stream_until_terminal(websocket)
    finally:
        test_app.dependency_overrides.clear()

    assert any(message.get("type") == "status" for message in messages)
    assert any(message.get("type") == "delta" for message in messages)


@pytest.mark.asyncio
async def test_customer_chat_enforces_ownership(test_app, db_session: AsyncSession) -> None:
    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as ac:
            token_owner = await _create_user_and_token(db_session, "owner@example.com")
            token_other = await _create_user_and_token(db_session, "other@example.com")

            owner_user = (
                (await db_session.execute(select(User).where(User.email == "owner@example.com")))
                .scalars()
                .first()
            )
            assert owner_user is not None

            conversation = CustomerConversation(title="Vectors", user_id=owner_user.id)
            db_session.add(conversation)
            await db_session.flush()
            db_session.add(
                CustomerMessage(
                    conversation_id=conversation.id,
                    role=MessageRole.USER,
                    content="Explain vectors",
                )
            )
            await db_session.commit()

            detail_resp = await ac.get(
                f"/api/chat/conversations/{conversation.id}",
                headers={"Authorization": f"Bearer {token_other}"},
            )
            assert detail_resp.status_code == 404
            assert token_owner
    finally:
        test_app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_customer_chat_returns_error_on_stream_failure(
    test_app,
    db_session: AsyncSession,
) -> None:
    async def _failed_stream() -> AsyncGenerator[dict[str, object], None]:
        yield {"type": "conversation_init", "payload": {"conversation_id": 1, "title": "t"}}
        raise RuntimeError("stream failed")

    async def mock_dispatch(**kwargs: object) -> ChatDispatchResult:
        return ChatDispatchResult(status_code=200, stream=_failed_stream())

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with patch.object(ChatOrchestrator, "dispatch", side_effect=mock_dispatch):
            async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test"):
                token = await _create_user_and_token(db_session, "fallback@example.com")

            with TestClient(test_app) as client:
                with client.websocket_connect(f"/api/chat/ws?token={token}") as websocket:
                    websocket.send_json({"question": "Explain math vectors"})
                    messages = _consume_stream_until_terminal(websocket)
    finally:
        test_app.dependency_overrides.clear()

    assert any(message.get("type") == "error" for message in messages)


@pytest.mark.asyncio
async def test_customer_chat_persists_conversation_and_messages(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من أن مسار WebSocket الحقيقي يحفظ المحادثة ورسائل المستخدم/المساعد."""

    async def mock_process(self, **kwargs: object) -> AsyncGenerator[str, None]:
        yield "Persisted assistant answer"

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with patch.object(ChatOrchestrator, "process", new=mock_process):
            token = await _create_user_and_token(db_session, "persist@example.com")

            with TestClient(test_app) as client:
                with client.websocket_connect(f"/api/chat/ws?token={token}") as websocket:
                    websocket.send_json({"question": "Explain vectors"})
                    events = _consume_stream_until_terminal(websocket)

        user = (
            (await db_session.execute(select(User).where(User.email == "persist@example.com")))
            .scalars()
            .one()
        )
        conversation = (
            (
                await db_session.execute(
                    select(CustomerConversation).where(CustomerConversation.user_id == user.id)
                )
            )
            .scalars()
            .one()
        )
        messages = (
            (
                await db_session.execute(
                    select(CustomerMessage)
                    .where(CustomerMessage.conversation_id == conversation.id)
                    .order_by(CustomerMessage.id)
                )
            )
            .scalars()
            .all()
        )
    finally:
        test_app.dependency_overrides.clear()

    assert any(event.get("type") == "conversation_init" for event in events)
    assert len(messages) == 2
    assert messages[0].role == MessageRole.USER
    assert messages[0].content == "Explain vectors"
    assert messages[1].role == MessageRole.ASSISTANT
    assert "Persisted assistant answer" in messages[1].content


@pytest.mark.asyncio
async def test_customer_chat_history_endpoint_reads_persisted_websocket_messages(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من أن واجهة التاريخ تقرأ رسائل WebSocket المحفوظة فعلياً."""

    async def mock_process(self, **kwargs: object) -> AsyncGenerator[str, None]:
        yield "History visible answer"

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with patch.object(ChatOrchestrator, "process", new=mock_process):
            token = await _create_user_and_token(db_session, "history-visible@example.com")

            with TestClient(test_app) as client:
                with client.websocket_connect(f"/api/chat/ws?token={token}") as websocket:
                    websocket.send_json({"question": "اشرح تمرين المتجهات في البكالوريا"})
                    _consume_stream_until_terminal(websocket)

            user = (
                (
                    await db_session.execute(
                        select(User).where(User.email == "history-visible@example.com")
                    )
                )
                .scalars()
                .one()
            )
            conversation = (
                (
                    await db_session.execute(
                        select(CustomerConversation).where(CustomerConversation.user_id == user.id)
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
                    f"/api/chat/conversations/{conversation.id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
    finally:
        test_app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    messages = payload.get("messages", [])
    assert any(msg.get("role") == "user" for msg in messages)
    assert any(msg.get("role") == "assistant" for msg in messages)
    assert any(msg.get("content") for msg in messages if msg.get("role") == "assistant")


@pytest.mark.asyncio
async def test_customer_chat_dispatch_receives_mission_metadata_and_conversation_id(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من تمرير mission_type ومعرّف المحادثة إلى حد التفريع المركزي."""

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
            token = await _create_user_and_token(db_session, "mission-meta@example.com")

            with TestClient(test_app) as client:
                with client.websocket_connect(f"/api/chat/ws?token={token}") as websocket:
                    websocket.send_json(
                        {
                            "question": "Run mission",
                            "conversation_id": 42,
                            "mission_type": "mission_complex",
                        }
                    )
                    _consume_stream_until_terminal(websocket)
    finally:
        test_app.dependency_overrides.clear()

    assert captured.get("conversation_id") == 42
    metadata = captured.get("metadata")
    assert isinstance(metadata, dict)
    assert metadata.get("mission_type") == "mission_complex"


@pytest.mark.asyncio
async def test_customer_websocket_persists_fallback_message_on_stream_failure(
    test_app,
    db_session: AsyncSession,
) -> None:
    """يتحقق من حفظ رسالة fallback في التاريخ عند فشل بث العميل."""

    async def failing_process(self, **kwargs: object) -> AsyncGenerator[str, None]:
        if False:
            yield "unused"
        raise RuntimeError("customer stream failed")

    async def override_get_db() -> AsyncGenerator[AsyncSession, None]:
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    try:
        with patch.object(ChatOrchestrator, "process", new=failing_process):
            token = await _create_user_and_token(db_session, "customer-fail@example.com")

            with TestClient(test_app) as client:
                with client.websocket_connect(f"/api/chat/ws?token={token}") as websocket:
                    websocket.send_json({"question": "اشرح المتجهات"})
                    events = _consume_stream_until_terminal(websocket)

            user = (
                (await db_session.execute(select(User).where(User.email == "customer-fail@example.com")))
                .scalars()
                .one()
            )
            conversation = (
                (
                    await db_session.execute(
                        select(CustomerConversation).where(CustomerConversation.user_id == user.id)
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
                    f"/api/chat/conversations/{conversation.id}",
                    headers={"Authorization": f"Bearer {token}"},
                )
    finally:
        test_app.dependency_overrides.clear()

    assert any(event.get("type") == "complete" for event in events)
    assert response.status_code == 200
    payload = response.json()
    messages = payload.get("messages", [])
    assert any(msg.get("role") == "user" for msg in messages)
    assert any(msg.get("role") == "assistant" for msg in messages)
    assert any(
        "تعذر الوصول إلى خدمة الذكاء الاصطناعي" in str(msg.get("content", ""))
        for msg in messages
        if msg.get("role") == "assistant"
    )
