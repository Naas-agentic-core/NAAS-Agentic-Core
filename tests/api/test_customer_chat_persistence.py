"""اختبارات سلوكية لواجهات تاريخ دردشة العملاء بعد إزالة WS المحلي."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from sqlalchemy import select

from app.core.domain.chat import CustomerConversation, CustomerMessage
from app.core.domain.user import User


@pytest.mark.asyncio
async def test_customer_chat_history_endpoints_return_seeded_conversation(
    test_app,
    db_session: AsyncSession,
    register_and_login_test_user,
) -> None:
    """يتحقق من أن واجهات التاريخ تعيد بيانات محادثة عميل محفوظة فعليًا."""

    token = await register_and_login_test_user(db_session, "history-seeded@example.com")

    user = (
        (await db_session.execute(select(User).where(User.email == "history-seeded@example.com")))
        .scalars()
        .one()
    )

    conversation = CustomerConversation(user_id=user.id, title="محادثة اختبار")
    db_session.add(conversation)
    await db_session.flush()

    db_session.add(
        CustomerMessage(
            conversation_id=conversation.id,
            role="user",
            content="كيف أتعلم الجبر؟",
        )
    )
    await db_session.commit()

    headers = {"Authorization": f"Bearer {token}"}
    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        latest_response = await client.get("/api/chat/latest", headers=headers)
        list_response = await client.get("/api/chat/conversations", headers=headers)

    assert latest_response.status_code == 200
    assert list_response.status_code == 200

    latest_payload = latest_response.json()
    list_payload = list_response.json()

    assert int(latest_payload["conversation_id"]) == int(conversation.id)
    assert isinstance(list_payload, list)
    assert any(int(item["conversation_id"]) == int(conversation.id) for item in list_payload)


def test_customer_chat_ws_path_is_decommissioned(test_app) -> None:
    """يتحقق من إلغاء WS المحلي للعملاء لمنع split-brain."""

    from fastapi.testclient import TestClient

    with TestClient(test_app) as client:
        response = client.get("/api/chat/ws")

    assert response.status_code == 404
