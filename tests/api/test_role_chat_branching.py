import jwt
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.settings.base import get_settings


@pytest.mark.asyncio
async def test_admin_blocked_from_customer_chat(test_app, db_session: AsyncSession) -> None:
    """يتأكد من أن حسابات الإدارة لا يمكنها استخدام قناة دردشة العملاء."""

    async def override_get_db():
        yield db_session

    test_app.dependency_overrides[get_db] = override_get_db

    insert_result = await db_session.execute(
        text(
            """
            INSERT INTO users (external_id, full_name, email, password_hash, is_admin, is_active, status)
            VALUES (:external_id, :full_name, :email, :password_hash, :is_admin, :is_active, :status)
            """
        ),
        {
            "external_id": "admin-branch",
            "full_name": "Admin",
            "email": "admin_branch@example.com",
            "password_hash": "unused",
            "is_admin": True,
            "is_active": True,
            "status": "active",
        },
    )
    await db_session.commit()
    token = jwt.encode(
        {
            "sub": str(int(insert_result.lastrowid)),
            "email": "admin_branch@example.com",
            "is_admin": True,
            "role": "admin",
        },
        get_settings().SECRET_KEY,
        algorithm="HS256",
    )

    try:
        with TestClient(test_app) as client:
            from starlette.websockets import WebSocketDisconnect
            with pytest.raises(WebSocketDisconnect) as exc:
                with client.websocket_connect(f"/api/chat/ws?token={token}"):
                    pass
            assert exc.value.code in (1000, 4401)
    finally:
        test_app.dependency_overrides.clear()
