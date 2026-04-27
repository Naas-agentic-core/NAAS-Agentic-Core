from datetime import datetime

import pytest

from app.core.domain.models import AdminConversation


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_get_latest_chat_deterministic_order(
    client, db_session, admin_user, admin_auth_headers
):
    """
    Verifies that get_latest_chat correctly returns the conversation with the higher ID
    when timestamps are identical, ensuring deterministic ordering.
    """
    # Create two conversations with the exact same timestamp
    fixed_time = datetime.utcnow()

    # Create first conversation (ID 1)
    conv1 = AdminConversation(
        user_id=admin_user.id, title="First Conversation", created_at=fixed_time
    )
    db_session.add(conv1)
    await db_session.commit()
    await db_session.refresh(conv1)

    # Create second conversation (ID 2)
    conv2 = AdminConversation(
        user_id=admin_user.id, title="Second Conversation", created_at=fixed_time
    )
    db_session.add(conv2)
    await db_session.commit()
    await db_session.refresh(conv2)

    # Verify IDs are as expected
    assert conv1.id < conv2.id
    assert conv1.created_at == conv2.created_at

    # Call the endpoint via TestClient
    response = client.get("/admin/api/chat/latest", headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.json()

    # Assert that the returned conversation is the second one (higher ID)
    assert data["conversation_id"] == conv2.id, (
        f"Expected conversation {conv2.id} but got {data['conversation_id']}"
    )
