"""اختبارات سلوكية لتاريخ دردشة الإدارة بعد إيقاف WS المحلي."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.chat import AdminConversation, AdminMessage


def test_admin_websocket_surface_is_decommissioned(test_app) -> None:
    """يتحقق من أن WS الإداري المحلي غير متاح."""

    from fastapi.testclient import TestClient

    with TestClient(test_app) as client:
        response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_admin_history_http_endpoints_return_seeded_conversation(
    test_app,
    db_session: AsyncSession,
    admin_user,
    admin_auth_headers,
) -> None:
    """يتحقق من أن واجهات تاريخ الإدارة تعيد بيانات محادثة محفوظة فعليًا."""

    conversation = AdminConversation(user_id=admin_user.id, title="جلسة إدارية")
    db_session.add(conversation)
    await db_session.flush()

    db_session.add(
        AdminMessage(
            conversation_id=conversation.id,
            role="user",
            content="أعطني تقرير النظام",
        )
    )
    await db_session.commit()

    async with AsyncClient(transport=ASGITransport(app=test_app), base_url="http://test") as client:
        latest_response = await client.get("/admin/api/chat/latest", headers=admin_auth_headers)
        list_response = await client.get("/admin/api/conversations", headers=admin_auth_headers)

    assert latest_response.status_code == 200
    assert list_response.status_code == 200

    latest_payload = latest_response.json()
    list_payload = list_response.json()

    assert int(latest_payload["conversation_id"]) == int(conversation.id)
    assert isinstance(list_payload, list)
    assert any(int(item["conversation_id"]) == int(conversation.id) for item in list_payload)
