"""طبقة الاستمرارية الخاصة بالمصادقة وإدارة المستخدمين."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.user import User

logger = logging.getLogger(__name__)


class AuthPersistence:
    """يوفر عمليات الوصول للبيانات الخاصة بالتسجيل وتسجيل الدخول."""

    def __init__(self, db: AsyncSession) -> None:
        """يهيئ الكائن بجلسة قاعدة البيانات غير المتزامنة."""
        self.db = db

    async def get_user_by_email(self, email: str) -> User | None:
        """يعيد المستخدم المقابل للبريد الإلكتروني بعد التطبيع."""
        stmt = select(User).where(User.email == email.lower().strip())
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_user_by_id(self, user_id: int) -> User | None:
        """يعيد المستخدم بحسب المعرف الرقمي."""
        return await self.db.get(User, user_id)

    async def create_user(
        self,
        full_name: str,
        email: str,
        password: str,
        is_admin: bool = False,
    ) -> User:
        """ينشئ مستخدمًا جديدًا عبر إدراج SQL مباشر لتفادي تعارضات مزامنة ORM."""
        normalized_email = email.lower().strip()
        password_owner = User(full_name=full_name, email=normalized_email, is_admin=is_admin)
        password_owner.set_password(password)

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
            RETURNING id
            """
        )
        result = await self.db.execute(
            insert_statement,
            {
                "external_id": str(uuid.uuid4()),
                "full_name": full_name,
                "email": normalized_email,
                "password_hash": password_owner.password_hash,
                "is_admin": is_admin,
                "is_active": True,
                "status": "active",
            },
        )
        await self.db.commit()

        created_id = int(result.scalar())
        created_user = await self.get_user_by_id(created_id)
        if created_user is None:
            raise RuntimeError("تعذر تحميل المستخدم بعد إنشائه")

        return created_user

    async def user_exists(self, email: str) -> bool:
        """يتحقق من وجود مستخدم بنفس البريد الإلكتروني."""
        user = await self.get_user_by_email(email)
        return user is not None
