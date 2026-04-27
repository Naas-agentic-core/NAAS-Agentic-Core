import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_login_bug_reproduction(async_client: AsyncClient):
    # 1. Register a user
    register_payload = {
        "full_name": "Test User",
        "email": "test_bug@example.com",
        "password": "password123",
    }

    response = await async_client.post("/api/security/register", json=register_payload)
    assert response.status_code == 200, f"Registration failed: {response.text}"

    # 2. Login with the user
    login_payload = {"email": "test_bug@example.com", "password": "password123"}

    # This should succeed with 200 OK.
    # If the bug (AttributeError: 'AppSettings' object has no attribute 'SECRET_key') is present,
    # this will fail with 500 Internal Server Error.
    response = await async_client.post("/api/security/login", json=login_payload)
    assert response.status_code == 200, f"Login failed: {response.text}"

    data = response.json()
    # The response was flattened to support frontend requirements.
    # Verify the flat structure: { access_token: "...", status: "success", ... }
    assert data["status"] == "success"
    assert "access_token" in data
