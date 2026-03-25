import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy.ext.asyncio import AsyncSession

from microservices.conversation_service.main import app

def make_mock_db(exists=False):
    mock_result = MagicMock()          # NOT AsyncMock
    mock_result.scalar.return_value = 1 if exists else None
    mock_result.mappings.return_value.first.return_value = (
        {"id": 9999, "user_id": 1, "title": "test",
         "created_at": None, "updated_at": None,
         "metadata": None}
        if exists else None
    )
    mock_result.mappings.return_value.all.return_value = []

    # To avoid the 'coroutine' object does not support the asynchronous context manager protocol error,
    # we use a MagicMock for the return value of mock_db.begin (which makes it NOT a coroutine)
    mock_db = MagicMock() # Changed to MagicMock from AsyncMock so its methods aren't automatically coroutines
    mock_db.execute = AsyncMock(return_value=mock_result)

    mock_begin_cm = MagicMock()
    mock_begin_cm.__aenter__ = AsyncMock(return_value=mock_db)
    mock_begin_cm.__aexit__ = AsyncMock(return_value=None)
    mock_db.begin.return_value = mock_begin_cm

    return mock_db

def test_import_new_conversation_returns_imported():
    client = TestClient(app)
    mock_session = make_mock_db(exists=False)

    payload = {
        "conversation_id": 100,
        "user_id": 42,
        "idempotency_key": "100:42",
        "max_messages": 50,
        "conversation_metadata": {"title": "Test conversation"},
        "messages": [
            {"role": "user", "content": "hello"}
        ]
    }

    from microservices.conversation_service.database import get_conv_db_session
    app.dependency_overrides[get_conv_db_session] = lambda: mock_session
    response = client.post("/api/v1/conversations/import", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "imported"
    assert data["conversation_id"] == 100
    assert data["messages_imported"] == 1


def test_import_twice_returns_already_exists():
    client = TestClient(app)
    mock_session = make_mock_db(exists=True)

    payload = {
        "conversation_id": 100,
        "user_id": 42,
        "idempotency_key": "100:42",
        "max_messages": 50,
        "conversation_metadata": {"title": "Test conversation"},
        "messages": [
            {"role": "user", "content": "hello"}
        ]
    }

    from microservices.conversation_service.database import get_conv_db_session
    app.dependency_overrides[get_conv_db_session] = lambda: mock_session
    response = client.post("/api/v1/conversations/import", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "already_exists"
    assert data["conversation_id"] == 100
    assert data["messages_imported"] == 0


def test_import_wrong_user_id_returns_not_found():
    client = TestClient(app)
    mock_session = make_mock_db(exists=False)

    payload = {
        "conversation_id": 100,
        "user_id": 99,
        "idempotency_key": "100:99",
        "max_messages": 50,
        "conversation_metadata": {},
        "messages": []
    }

    from microservices.conversation_service.database import get_conv_db_session
    app.dependency_overrides[get_conv_db_session] = lambda: mock_session
    response = client.post("/api/v1/conversations/import", json=payload)

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "not_found_in_source"
    assert data["conversation_id"] == 100
    assert data["messages_imported"] == 0