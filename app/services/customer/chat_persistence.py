"""
طبقة التخزين لمحادثات العملاء القياسيين.

تعزل عمليات القراءة والكتابة الخاصة بالمحادثات التعليمية لضمان وضوح الحدود
بين طبقة العرض والمنطق التطبيقي.
"""

from __future__ import annotations

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.domain.chat import CustomerConversation, CustomerMessage, MessageRole
from app.core.domain.user import User
from app.core.prompts import get_customer_system_prompt

logger = logging.getLogger(__name__)


class CustomerChatPersistence:
    """
    مستودع بيانات محادثات العملاء القياسيين.
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def verify_access(self, user_id: int, conversation_id: int) -> CustomerConversation:
        """
        التحقق من وصول المستخدم إلى المحادثة.
        """
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("User not found")

        conversation = await self.db.get(CustomerConversation, conversation_id)
        if not conversation:
            raise ValueError("Conversation not found")

        if conversation.user_id != user_id:
            raise ValueError("Access denied to conversation")

        return conversation

    async def get_or_create_conversation(
        self,
        user_id: int,
        title_hint: str,
        conversation_id: str | int | None = None,
    ) -> CustomerConversation:
        """
        استرجاع محادثة موجودة أو إنشاء واحدة جديدة.
        """
        conversation: CustomerConversation | None = None
        if conversation_id:
            conversation = await self.verify_access(user_id, int(conversation_id))

        if not conversation:
            conversation = CustomerConversation(title=title_hint[:50], user_id=user_id)
            self.db.add(conversation)
            await self.db.commit()
            await self.db.refresh(conversation)

        return conversation

    async def save_message(
        self,
        conversation_id: int,
        role: MessageRole,
        content: str,
        policy_flags: dict[str, str] | None = None,
    ) -> CustomerMessage:
        """
        حفظ رسالة جديدة ضمن محادثة العميل مع حماية صارمة ضد التكرار (Duplicate Guard).
        """
        from datetime import datetime, timedelta, timezone
        from sqlalchemy import and_

        # --- DUPLICATE DETECTION GUARD ---
        ten_seconds_ago = datetime.now(timezone.utc) - timedelta(seconds=10)
        # Using naive utcnow() if model doesn't support timezone aware, but usually SQLAlchemy handles it. Let's use naive if standard in project, or aware.
        # It's safer to just fetch the last message for this role/conversation and compare.
        stmt = (
            select(CustomerMessage)
            .where(
                and_(
                    CustomerMessage.conversation_id == conversation_id,
                    CustomerMessage.role == role,
                    CustomerMessage.content == content
                )
            )
            .order_by(CustomerMessage.created_at.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        existing_msg = result.scalar_one_or_none()
        
        if existing_msg:
            # Check if it was created very recently (within 10 seconds)
            time_diff = None
            if existing_msg.created_at:
                now = datetime.now(existing_msg.created_at.tzinfo) if existing_msg.created_at.tzinfo else datetime.utcnow()
                time_diff = (now - existing_msg.created_at).total_seconds()
                
            if time_diff is not None and time_diff <= 10:
                logger.critical(
                    f"[DUPLICATE_GUARD_ACTIVATED] Suppressed duplicate message save. "
                    f"conversation_id={conversation_id} role={role.value}"
                )
                return existing_msg

        message = CustomerMessage(
            conversation_id=conversation_id,
            role=role,
            content=content,
            policy_flags=policy_flags,
        )
        self.db.add(message)
        await self.db.commit()
        return message

    async def get_chat_history(self, conversation_id: int, limit: int = 20) -> list[dict[str, str]]:
        """
        استرجاع تاريخ المحادثة مع موجه تعليمي آمن.
        """
        stmt = (
            select(CustomerMessage)
            .where(CustomerMessage.conversation_id == conversation_id)
            .order_by(CustomerMessage.created_at.desc(), CustomerMessage.id.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()

        history: list[dict[str, str]] = [
            {"role": "system", "content": get_customer_system_prompt()}
        ]
        for msg in messages:
            history.append({"role": msg.role.value, "content": msg.content})

        return history

    async def get_latest_conversation(self, user_id: int) -> CustomerConversation | None:
        """
        استرجاع آخر محادثة للمستخدم القياسي.
        """
        stmt = (
            select(CustomerConversation)
            .where(CustomerConversation.user_id == user_id)
            .order_by(CustomerConversation.created_at.desc(), CustomerConversation.id.desc())
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def list_conversations(self, user_id: int) -> list[CustomerConversation]:
        """
        سرد جميع محادثات المستخدم القياسي.
        """
        stmt = (
            select(CustomerConversation)
            .where(CustomerConversation.user_id == user_id)
            .order_by(CustomerConversation.created_at.desc(), CustomerConversation.id.desc())
        )
        result = await self.db.execute(stmt)
        return list(result.scalars().all())

    async def get_conversation_messages(
        self,
        conversation_id: int,
        limit: int = 1000,
    ) -> list[CustomerMessage]:
        """
        استرجاع رسائل محادثة محددة بترتيب زمني.
        """
        stmt = (
            select(CustomerMessage)
            .where(CustomerMessage.conversation_id == conversation_id)
            .order_by(CustomerMessage.created_at.desc(), CustomerMessage.id.desc())
            .limit(limit)
        )
        result = await self.db.execute(stmt)
        messages = list(result.scalars().all())
        messages.reverse()
        return messages
