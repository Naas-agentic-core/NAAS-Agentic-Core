import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_standard_login_returns_chat_landing(async_client: AsyncClient, db_session) -> None:
    from sqlalchemy import text

    # Cleanup before test to avoid 400 Bad Request (Duplicate Email)
    await db_session.execute(text("DELETE FROM users WHERE email = 'student@example.com'"))
    await db_session.commit()

    register_payload = {
        "full_name": "Student User",
        "email": "student@example.com",
        "password": "Secret123!",
    }
    register_resp = await async_client.post("/api/security/register", json=register_payload)
    # Handle case where user might still exist despite cleanup attempt (e.g. race condition or session isolation)
    if register_resp.status_code == 400 and "already exists" in register_resp.text:
        pass
    else:
        assert register_resp.status_code == 200

    login_resp = await async_client.post(
        "/api/security/login",
        json={"email": "student@example.com", "password": "Secret123!"},
    )
    assert login_resp.status_code == 200
    payload = login_resp.json()

    assert payload.get("landing_path") == "/app/chat"


@pytest.mark.asyncio
@pytest.mark.skip(reason="Legacy monolith WS route disabled")
async def test_standard_user_cannot_access_admin_chat(async_client: AsyncClient) -> None:
    register_payload = {
        "full_name": "Student User",
        "email": "student2@example.com",
        "password": "Secret123!",
    }
    register_resp = await async_client.post("/api/security/register", json=register_payload)
    assert register_resp.status_code == 200

    login_resp = await async_client.post(
        "/api/security/login",
        json={"email": "student2@example.com", "password": "Secret123!"},
    )
    assert login_resp.status_code == 200
    token = login_resp.json()["access_token"]

    chat_resp = await async_client.get(
        "/admin/api/chat/latest",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert chat_resp.status_code == 403
