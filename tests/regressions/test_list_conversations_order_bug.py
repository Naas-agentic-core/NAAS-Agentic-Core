from datetime import datetime

import pytest

from app.core.domain.models import AdminConversation


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_list_conversations_deterministic_order(
    client, db_session, admin_user, admin_auth_headers
):
    """
    Verifies that list_conversations correctly returns the conversations with a deterministic order
    when timestamps are identical, by sorting by ID as a secondary key.
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
    response = client.get("/admin/api/conversations", headers=admin_auth_headers)
    assert response.status_code == 200
    data = response.json()

    # We expect descending order of creation (newest first).
    # Since timestamps are equal, we expect secondary sort by ID desc.
    # So conv2 should be first, then conv1.

    assert len(data) >= 2

    # Filter for our test conversations in case there are others
    test_convs = [c for c in data if c["id"] in (conv1.id, conv2.id)]

    assert len(test_convs) == 2
    assert test_convs[0]["id"] == conv2.id, (
        f"Expected conversation {conv2.id} first (newer ID), but got {test_convs[0]['id']}"
    )
    assert test_convs[1]["id"] == conv1.id
