"""
واجهة برمجة تطبيقات محادثة العملاء القياسيين.

توفر نقاط النهاية الخاصة بالمستخدمين القياسيين للوصول إلى محادثة تعليمية
مع فرض سياسات الأمان والملكية.
"""

import asyncio
import uuid

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ws_auth import extract_websocket_auth
from app.api.schemas.customer_chat import (
    CustomerConversationDetails,
    CustomerConversationSummary,
)
from app.core.config import get_settings
from app.core.database import async_session_factory, get_db
from app.core.di import get_logger
from app.core.domain.chat import MessageRole
from app.core.domain.user import User
from app.deps.auth import CurrentUser, require_permissions
from app.infrastructure.clients.orchestrator_client import orchestrator_client
from app.services.auth.token_decoder import decode_user_id
from app.services.boundaries.customer_chat_boundary_service import (
    CustomerChatBoundaryService,
)
from app.services.rbac import QA_SUBMIT
from shared.chat_protocol.event_protocol import normalize_streaming_event

logger = get_logger(__name__)

COMPATIBILITY_FACADE_MODE = True
# تنبيه معماري: هذا المسار واجهة توافقية فقط ويُمنع فيه أي تنفيذ محلي لمنطق الدردشة.
CANONICAL_EXECUTION_AUTHORITY = "orchestrator-service:/agent/chat"
LEGACY_LOCAL_EXECUTION_BLOCKED = True

router = APIRouter(
    prefix="/api/chat",
    tags=["Customer Chat"],
)

TEXT_EVENT_TYPES = {"delta", "assistant_delta", "assistant_final"}


def get_chat_actor(
    current: CurrentUser = Depends(require_permissions(QA_SUBMIT)),
) -> CurrentUser:
    """تبعية تضمن امتلاك صلاحية الأسئلة التعليمية."""
    return current


def get_current_user_id(current: CurrentUser = Depends(get_chat_actor)) -> int:
    """إرجاع معرف المستخدم الحالي بعد تحقق الصلاحيات."""
    return current.user.id


async def get_actor_user(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    جلب كائن المستخدم الفعلي بعد التحقق من الحالة.
    """
    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")
    await db.refresh(user)
    db.expunge(user)
    return user


def get_customer_service(
    db: AsyncSession = Depends(get_db),
) -> CustomerChatBoundaryService:
    """تبعية للحصول على خدمة حدود محادثة العملاء."""
    return CustomerChatBoundaryService(db)


def _is_text_event(event: dict[str, object]) -> bool:
    """يتحقق من أن الحدث نصي ومسموح بتجميعه داخل مخزن النص النهائي."""
    return str(event.get("type", "")) in TEXT_EVENT_TYPES


def _bind_local_conversation_id(
    event: dict[str, object], conversation_id: int | None
) -> dict[str, object]:
    """يربط معرف المحادثة المحلي بجميع أحداث البث لمنع اختلاط السياق في الواجهة."""
    if conversation_id is None:
        return event
    payload = event.get("payload")
    if isinstance(payload, dict):
        payload["conversation_id"] = conversation_id
    else:
        event["payload"] = {"conversation_id": conversation_id}
    return event


def _bind_stream_metadata(
    event: dict[str, object],
    conversation_id: int | None,
    request_id: str | None,
) -> dict[str, object]:
    """يربط بيانات التتبع القياسية بكل حدث بث لعزل السياق بين الطلبات."""
    bound_event = _bind_local_conversation_id(event, conversation_id)
    if not request_id:
        return bound_event
    payload = bound_event.get("payload")
    if isinstance(payload, dict):
        payload["request_id"] = request_id
    else:
        bound_event["payload"] = {"request_id": request_id}
    return bound_event


def _extract_client_context_messages(payload: dict[str, object]) -> list[dict[str, str]]:
    """استخراج سياق المحادثة المرسل من الواجهة بشكل آمن ومحدود الحجم."""
    raw_context = payload.get("client_context_messages")
    if not isinstance(raw_context, list):
        return []

    sanitized: list[dict[str, str]] = []
    for item in raw_context:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str):
            continue
        text = content.strip()
        if not text:
            continue
        sanitized.append({"role": role, "content": text})
        if len(sanitized) >= 50:
            break
    return sanitized


def _merge_history_with_client_context(
    persisted_history: list[dict[str, str]],
    client_context: list[dict[str, str]],
) -> list[dict[str, str]]:
    """دمج تاريخ قاعدة البيانات مع سياق العميل للحفاظ على الاستمرارية بدون تكرار."""
    if not client_context:
        return persisted_history
    if not persisted_history:
        return []

    merged_history = list(persisted_history)
    for message in client_context:
        if message not in merged_history:
            merged_history.append(message)
    return merged_history[-80:]


@router.websocket("/ws")
async def chat_stream_ws(
    websocket: WebSocket,
) -> None:
    """
    قناة WebSocket لبث محادثة تعليمية للمستخدم القياسي.
    """
    token, selected_protocol = extract_websocket_auth(websocket)
    if not token:
        await websocket.close(code=4401)
        return

    try:
        user_id = decode_user_id(token, get_settings().SECRET_KEY)
    except HTTPException:
        await websocket.close(code=4401)
        return

    async with async_session_factory() as db:
        actor = await db.get(User, user_id)
        if actor is None or not actor.is_active:
            await websocket.close(code=4401)
            return

        # Expunge the actor so we can use it after the session is closed
        db.expunge(actor)

    await websocket.accept(subprotocol=selected_protocol)

    if actor.is_admin:
        await websocket.send_json(
            normalize_streaming_event(
                {
                    "type": "error",
                    "payload": {
                        "details": "Admin accounts must use the admin chat endpoint.",
                        "status_code": 403,
                    },
                }
            )
        )
        await websocket.close(code=4403)
        return

    try:
        while True:
            payload = await websocket.receive_json()
            request_id_value = payload.get("client_request_id")
            client_request_id = (
                str(request_id_value).strip() if request_id_value is not None else None
            )
            if client_request_id == "":
                client_request_id = None
            stream_request_id = client_request_id or str(uuid.uuid4())

            question = str(payload.get("question", "")).replace("\x00", "").strip()
            if not question:
                await websocket.send_json(
                    _bind_stream_metadata(
                        normalize_streaming_event(
                            {
                                "type": "error",
                                "payload": {"details": "Question is required."},
                            }
                        ),
                        None,
                        stream_request_id,
                    )
                )
                continue

            mission_type = payload.get("mission_type")
            metadata: dict[str, object] = {}
            if mission_type:
                metadata["mission_type"] = mission_type
            client_context_messages = _extract_client_context_messages(payload)
            if client_context_messages:
                metadata["client_context_messages"] = client_context_messages

            original_conversation_id = payload.get("conversation_id")
            local_conversation_id: int | None = None
            history_messages: list[dict[str, str]] = []

            try:
                async with async_session_factory() as db:
                    persistence_service = CustomerChatBoundaryService(db)
                    local_conversation = await persistence_service.get_or_create_conversation(
                        actor,
                        question,
                        original_conversation_id,
                    )
                    local_conversation_id = local_conversation.id
                    await persistence_service.save_message(
                        local_conversation_id,
                        MessageRole.USER,
                        question,
                    )
                    history_messages = await persistence_service.get_chat_history(
                        local_conversation_id,
                        limit=50,
                    )
                    history_messages = _merge_history_with_client_context(
                        history_messages,
                        client_context_messages,
                    )
                await websocket.send_json(
                    normalize_streaming_event(
                        {
                            "type": "conversation_init",
                            "payload": {
                                "conversation_id": local_conversation_id,
                                "request_id": stream_request_id,
                            },
                        }
                    )
                )
            except HTTPException as http_exc:
                await websocket.send_json(
                    _bind_stream_metadata(
                        normalize_streaming_event(
                            {
                                "type": "error",
                                "payload": {
                                    "details": str(http_exc.detail),
                                    "status_code": http_exc.status_code,
                                },
                            }
                        ),
                        local_conversation_id,
                        stream_request_id,
                    )
                )
                continue
            except Exception as exc:
                logger.error(
                    f"Failed to persist customer user message locally: {exc}",
                    exc_info=True,
                )
                await websocket.send_json(
                    _bind_stream_metadata(
                        normalize_streaming_event(
                            {
                                "type": "error",
                                "payload": {
                                    "details": "Failed to save your message locally.",
                                    "status_code": 500,
                                },
                            }
                        ),
                        local_conversation_id,
                        stream_request_id,
                    )
                )
                continue

            complete_ai_response = ""
            assistant_message_persisted = False
            pending_terminal_event: dict[str, object] | None = None
            stream_task: asyncio.Task[None] | None = None
            stream_error: HTTPException | Exception | None = None

            try:

                async def stream_and_forward(
                    q=question,
                    lc_id=local_conversation_id,
                    meta=metadata,
                    history=history_messages,
                    request_id=stream_request_id,
                ) -> None:
                    nonlocal pending_terminal_event
                    nonlocal complete_ai_response
                    async for event in orchestrator_client.chat_with_agent(
                        question=q,
                        user_id=actor.id,
                        conversation_id=lc_id,
                        history_messages=history,
                        context={
                            "chat_scope": "customer",
                            "metadata": meta,
                            "compatibility_facade": True,
                        },
                    ):
                        normalized_event = normalize_streaming_event(event)

                        # Prevent "Split-Brain" DB FK violation:
                        # Intercept Orchestrator's conversation_init and rewrite/strip conversation_id
                        # so the local frontend doesn't overwrite its local sequence with Orchestrator's sequence.
                        if normalized_event.get("type") == "conversation_init" and isinstance(
                            normalized_event.get("payload"), dict
                        ):
                            if lc_id is not None:
                                # Rewrite to the established local sequence
                                normalized_event["payload"]["conversation_id"] = lc_id
                            else:
                                # Strip it to avoid overwriting local state with a foreign ID
                                normalized_event["payload"].pop("conversation_id", None)

                        event_type = normalized_event.get("type")
                        if event_type in {"complete", "assistant_final"}:
                            pending_terminal_event = _bind_stream_metadata(
                                normalized_event, lc_id, request_id
                            )
                        else:
                            await websocket.send_json(
                                _bind_stream_metadata(normalized_event, lc_id, request_id)
                            )

                        if _is_text_event(normalized_event) and isinstance(
                            normalized_event.get("payload"), dict
                        ):
                            chunk_text = normalized_event["payload"].get("content")
                            if isinstance(chunk_text, str) and chunk_text:
                                complete_ai_response += chunk_text

                stream_task = asyncio.create_task(stream_and_forward())
                await stream_task

            except HTTPException as http_exc:
                stream_error = http_exc
                logger.error(
                    f"HTTPException in compatibility facade stream: {http_exc}", exc_info=True
                )
            except Exception as exc:
                stream_error = exc
                logger.error(f"Error in compatibility facade stream: {exc}", exc_info=True)
                if not isinstance(exc, WebSocketDisconnect):
                    await websocket.send_json(
                        normalize_streaming_event(
                            {
                                "type": "error",
                                "payload": {"details": str(exc), "status_code": 500},
                            }
                        )
                    )
            finally:
                if stream_task is not None and not stream_task.done():
                    stream_task.cancel()
                    try:
                        await stream_task
                    except asyncio.CancelledError:
                        logger.info("Cancelled customer stream task after disconnect/finalization")

                if (
                    not assistant_message_persisted
                    and complete_ai_response
                    and local_conversation_id is not None
                ):
                    try:
                        async with async_session_factory() as db:
                            persistence_service = CustomerChatBoundaryService(db)
                            await persistence_service.save_message(
                                conversation_id=local_conversation_id,
                                role=MessageRole.ASSISTANT,
                                content=complete_ai_response.replace("\x00", ""),
                            )
                            assistant_message_persisted = True
                    except Exception as persistence_exc:
                        logger.error(
                            (
                                "Failed to persist customer assistant message locally "
                                f"for conversation {local_conversation_id}: {persistence_exc}"
                            ),
                            exc_info=True,
                        )
                if assistant_message_persisted:
                    if pending_terminal_event is not None:
                        await websocket.send_json(pending_terminal_event)
                    await websocket.send_json(
                        _bind_stream_metadata(
                            normalize_streaming_event({"type": "persisted"}),
                            local_conversation_id,
                            stream_request_id,
                        )
                    )
                elif pending_terminal_event is not None and stream_error is None:
                    await websocket.send_json(
                        _bind_stream_metadata(
                            normalize_streaming_event(
                                {
                                    "type": "error",
                                    "payload": {
                                        "details": (
                                            "Failed to confirm assistant persistence before completion."
                                        ),
                                        "status_code": 500,
                                    },
                                }
                            ),
                            local_conversation_id,
                            stream_request_id,
                        )
                    )
                if isinstance(stream_error, HTTPException):
                    await websocket.send_json(
                        _bind_stream_metadata(
                            normalize_streaming_event(
                                {
                                    "type": "error",
                                    "payload": {
                                        "details": str(stream_error.detail),
                                        "status_code": stream_error.status_code,
                                    },
                                }
                            ),
                            local_conversation_id,
                            stream_request_id,
                        )
                    )
                    # Cannot 'continue' inside finally, but stream_error is handled.
                    # Loop naturally repeats on the next client payload message.

    except WebSocketDisconnect:
        logger.info("Customer WebSocket disconnected")


@router.get(
    "/latest",
    summary="استرجاع آخر محادثة",
    response_model=CustomerConversationDetails | None,
)
async def get_latest_chat(
    actor: User = Depends(get_actor_user),
    service: CustomerChatBoundaryService = Depends(get_customer_service),
) -> CustomerConversationDetails | None:
    conversation_data = await service.get_latest_conversation_details(actor)
    if not conversation_data:
        return None
    return CustomerConversationDetails.model_validate(conversation_data)


@router.get(
    "/conversations",
    summary="سرد المحادثات",
    response_model=list[CustomerConversationSummary],
)
async def list_conversations(
    actor: User = Depends(get_actor_user),
    service: CustomerChatBoundaryService = Depends(get_customer_service),
) -> list[CustomerConversationSummary]:
    results = await service.list_user_conversations(actor)
    return [CustomerConversationSummary.model_validate(r) for r in results]


@router.get(
    "/conversations/{conversation_id}",
    summary="تفاصيل محادثة",
    response_model=CustomerConversationDetails,
    description="استرجاع تفاصيل محادثة محددة.",
    operation_id="chatConversationGet",
)
async def get_conversation(
    conversation_id: int,
    actor: User = Depends(get_actor_user),
    service: CustomerChatBoundaryService = Depends(get_customer_service),
) -> CustomerConversationDetails:
    data = await service.get_conversation_details(actor, conversation_id)
    return CustomerConversationDetails.model_validate(data)
