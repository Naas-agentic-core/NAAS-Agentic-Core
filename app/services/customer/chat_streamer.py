"""
بث محادثات العملاء القياسيين (Customer Chat Streamer).

يوفر قناة WebSocket آمنة مع حفظ الاستجابات بعد اكتمال البث.
"""

from __future__ import annotations

import logging
from collections.abc import AsyncGenerator, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.ai_gateway import AIClient
from app.core.domain.chat import CustomerConversation, MessageRole
from app.services.chat import get_chat_orchestrator
from app.services.chat.contracts import ChatStreamEvent
from app.services.chat.orchestrator import ChatOrchestrator
from app.services.customer.chat_persistence import CustomerChatPersistence

logger = logging.getLogger(__name__)


class CustomerChatStreamer:
    """
    باث محادثات العملاء القياسيين.
    """

    def __init__(self, persistence: CustomerChatPersistence) -> None:
        self.persistence = persistence

    async def stream_response(
        self,
        conversation: CustomerConversation,
        question: str,
        history: list[dict[str, str]],
        ai_client: AIClient,
        session_factory_func: Callable[[], AsyncSession],
        metadata: dict[str, object] | None = None,
    ) -> AsyncGenerator[ChatStreamEvent, None]:
        """
        بث استجابة الذكاء الاصطناعي مع حفظ الرسالة النهائية.
        """
        self._inject_system_context_if_missing(history)
        yield self._create_init_event(conversation)

        full_response: list[str] = []
        try:
            orchestrator = self._get_orchestrator()
            async for content in orchestrator.process(
                question=question,
                user_id=conversation.user_id,
                conversation_id=conversation.id,
                ai_client=ai_client,
                history_messages=history,
                session_factory=session_factory_func,
                metadata=metadata,
            ):
                if not content:
                    continue

                if isinstance(content, dict):
                    # Direct pass-through for structured events (AgentEvent)
                    # content is expected to be {type: ..., payload: ...}
                    yield content
                else:
                    full_response.append(content)
                    yield self._create_chunk_event(content)
        except Exception as exc:
            logger.error(f"❌ Customer chat streaming failed: {exc}")
            fallback_message = "تعذر الوصول إلى خدمة الذكاء الاصطناعي حالياً. حاول مرة أخرى لاحقاً."
            full_response = [fallback_message]
            yield self._create_chunk_event(fallback_message)
        finally:
            await self._persist_response(conversation.id, full_response, session_factory_func)
            yield {"type": "complete", "payload": {"status": "done"}}

    def _create_init_event(self, conversation: CustomerConversation) -> ChatStreamEvent:
        payload = {"conversation_id": conversation.id, "title": conversation.title}
        return {"type": "conversation_init", "payload": payload}

    def _create_chunk_event(self, content: str) -> ChatStreamEvent:
        return {"type": "delta", "payload": {"content": content}}

    def _inject_system_context_if_missing(self, history: list[dict[str, str]]) -> None:
        """
        حقن سياق النظام التعليمي لمسار الزبون عند غيابه.
        """
        has_system = any(msg.get("role") == "system" for msg in history)
        if not has_system:
            try:
                from app.services.chat.context_service import get_context_service

                ctx_service = get_context_service()
                system_prompt = ctx_service.get_customer_system_prompt()
                history.insert(0, {"role": "system", "content": system_prompt})
            except Exception as exc:
                logger.error(f"⚠️ Failed to inject customer context: {exc}")

    def _get_orchestrator(self) -> ChatOrchestrator:
        """
        إرجاع منسق المحادثة القياسي لضمان استخدام وكلاء Overmind المتعددين.
        """
        return get_chat_orchestrator()

    async def _persist_response(
        self,
        conversation_id: int,
        response_parts: list[str],
        session_factory_func: Callable[[], AsyncSession],
    ) -> None:
        assistant_content = "".join(response_parts)
        if not assistant_content:
            assistant_content = "Error: No response received from AI service."

        try:
            async with session_factory_func() as session:
                persistence = CustomerChatPersistence(session)
                await persistence.save_message(
                    conversation_id,
                    MessageRole.ASSISTANT,
                    assistant_content,
                )
        except Exception as exc:
            logger.error(f"❌ Failed to save assistant message: {exc}")
