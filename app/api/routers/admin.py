# app/api/routers/admin.py
"""
واجهة برمجة تطبيقات المسؤول (Admin API).
---------------------------------------------------------
توفر هذه الوحدة نقاط النهاية (Endpoints) الخاصة بالمسؤولين،
وتعتمد بشكل كامل على خدمة `AdminChatBoundaryService` لفصل المسؤوليات.
تتبع نمط "Presentation Layer" فقط، ولا تحتوي على أي منطق عمل.

المعايير:
- توثيق شامل باللغة العربية.
- صرامة في تحديد الأنواع (Strict Typing).
- اعتماد كامل على حقن التبعيات (Dependency Injection).
"""

import asyncio
import inspect

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ws_auth import extract_websocket_auth
from app.api.schemas.admin import (
    ConversationDetailsResponse,
    ConversationSummaryResponse,
)
from app.core.config import get_settings
from app.core.database import async_session_factory, get_db
from app.core.di import get_logger
from app.core.domain.chat import MessageRole
from app.core.domain.user import User
from app.deps.auth import CurrentUser, get_current_user, require_roles
from app.infrastructure.clients.orchestrator_client import orchestrator_client
from app.infrastructure.clients.user_client import user_client
from app.services.auth.token_decoder import decode_user_id
from app.services.boundaries.admin_chat_boundary_service import AdminChatBoundaryService
from app.services.rbac import ADMIN_ROLE
from shared.chat_protocol.event_protocol import normalize_streaming_event

logger = get_logger(__name__)

COMPATIBILITY_FACADE_MODE = True
# تنبيه معماري: هذا المسار واجهة توافقية فقط ويُمنع فيه أي تنفيذ محلي لمنطق الدردشة.
CANONICAL_EXECUTION_AUTHORITY = "orchestrator-service:/agent/chat"
LEGACY_LOCAL_EXECUTION_BLOCKED = True

router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


# -----------------------------------------------------------------------------
# DTOs
# -----------------------------------------------------------------------------
class AdminUserCountResponse(BaseModel):
    count: int


def get_chat_actor(
    current: CurrentUser = Depends(get_current_user),
) -> CurrentUser:
    """تبعية تُعيد المستخدم الحالي لاستخدام قنوات الدردشة الإدارية."""

    return current


def get_current_user_id(current: CurrentUser = Depends(get_chat_actor)) -> int:
    """
    إرجاع معرف المستخدم الحالي بعد التحقق من صلاحيات الأسئلة التعليمية.

    يعتمد هذا التابع على تبعية `get_chat_actor` لضمان أن المستدعي يملك
    التصاريح اللازمة قبل متابعة أي عمليات بث أو استعلامات خاصة بالمحادثات
    الإدارية.

    Args:
        current: كائن المستخدم الحالي المزود بالأدوار والصلاحيات.

    Returns:
        int: معرف المستخدم الموثق.
    """

    return current.user.id


async def get_actor_user(
    user_id: int = Depends(get_current_user_id),
    db: AsyncSession = Depends(get_db),
) -> User:
    """
    الحصول على كائن المستخدم الفعلي بالاعتماد على معرفه.

    يوفر هذا التابع طبقة تجريد تُمكِّن من تجاوز التحقق في الاختبارات عبر
    إعادة تعريف `get_current_user_id`، مع الحفاظ على مسار التحقق الأساسي في
    بيئة الإنتاج.

    Args:
        user_id: معرف المستخدم المستخرج من التبعيات السابقة.
        db: جلسة قاعدة البيانات المستخدمة للاستعلام.

    Returns:
        User: كائن المستخدم الفعّال.

    Raises:
        HTTPException: إذا كان المستخدم غير موجود أو غير مفعّل.
    """

    user = await db.get(User, user_id)
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")

    if not user.is_active:
        raise HTTPException(status_code=403, detail="User inactive")

    # فصل الكائن عن الجلسة لضمان توفر بياناته أثناء البث الطويل دون الاصطدام بإغلاق الجلسة.
    await db.refresh(user)
    expunge_result = db.expunge(user)
    if inspect.isawaitable(expunge_result):
        await expunge_result

    return user


def get_admin_service(db: AsyncSession = Depends(get_db)) -> AdminChatBoundaryService:
    """تبعية للحصول على خدمة حدود محادثة المسؤول."""
    return AdminChatBoundaryService(db)


# -----------------------------------------------------------------------------
# Endpoints
# -----------------------------------------------------------------------------


@router.get(
    "/users/count",
    summary="User Count (Admin)",
    response_model=AdminUserCountResponse,
    dependencies=[Depends(require_roles(ADMIN_ROLE))],
)
async def get_admin_user_count() -> AdminUserCountResponse:
    """
    Retrieve the total number of users in the system.
    Proxies to the User Service.
    """
    try:
        count = await user_client.get_user_count()
        return AdminUserCountResponse(count=count)
    except Exception as e:
        logger.error(f"Failed to retrieve user count: {e}")
        raise HTTPException(status_code=503, detail="User Service unavailable") from e


@router.websocket("/api/chat/ws")
async def chat_stream_ws(
    websocket: WebSocket,
) -> None:
    """
    قناة WebSocket لبث محادثة المسؤول بشكل حي وآمن.
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

    if not actor.is_admin:
        await websocket.send_json(
            normalize_streaming_event(
                {
                    "type": "error",
                    "payload": {
                        "details": "Standard accounts must use the customer chat endpoint.",
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
            question = str(payload.get("question", "")).replace("\x00", "").strip()
            if not question:
                await websocket.send_json(
                    normalize_streaming_event(
                        {
                            "type": "error",
                            "payload": {"details": "Question is required."},
                        }
                    )
                )
                continue

            mission_type = payload.get("mission_type")
            metadata: dict[str, object] = {}
            if mission_type:
                metadata["mission_type"] = mission_type

            original_conversation_id = payload.get("conversation_id")
            local_conversation_id: int | None = None

            try:
                async with async_session_factory() as db:
                    persistence_service = AdminChatBoundaryService(db)
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
            except HTTPException as http_exc:
                await websocket.send_json(
                    normalize_streaming_event(
                        {
                            "type": "error",
                            "payload": {
                                "details": str(http_exc.detail),
                                "status_code": http_exc.status_code,
                            },
                        }
                    )
                )
                continue
            except Exception as exc:
                logger.error(
                    f"Failed to persist admin user message locally: {exc}",
                    exc_info=True,
                )
                await websocket.send_json(
                    normalize_streaming_event(
                        {
                            "type": "error",
                            "payload": {
                                "details": "Failed to save your message locally.",
                                "status_code": 500,
                            },
                        }
                    )
                )
                continue

            complete_ai_response = ""
            assistant_message_persisted = False
            pending_terminal_event: dict[str, object] | None = None
            stream_task: asyncio.Task[None] | None = None
            stream_error: HTTPException | Exception | None = None

            try:
                async def stream_and_forward() -> None:
                    nonlocal pending_terminal_event
                    nonlocal complete_ai_response
                    async for event in orchestrator_client.chat_with_agent(
                        question=question,
                        user_id=actor.id,
                        conversation_id=local_conversation_id,
                        context={
                            "chat_scope": "admin",
                            "metadata": metadata,
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
                            if local_conversation_id is not None:
                                # Rewrite to the established local sequence
                                normalized_event["payload"]["conversation_id"] = local_conversation_id
                            else:
                                # Strip it to avoid overwriting local state with a foreign ID
                                normalized_event["payload"].pop("conversation_id", None)

                        event_type = normalized_event.get("type")
                        if event_type in {"complete", "assistant_final"}:
                            pending_terminal_event = normalized_event
                        else:
                            await websocket.send_json(normalized_event)

                        if isinstance(normalized_event.get("payload"), dict):
                            chunk_text = normalized_event["payload"].get("content")
                            if isinstance(chunk_text, str) and chunk_text:
                                complete_ai_response += chunk_text

                stream_task = asyncio.create_task(stream_and_forward())
                await stream_task
            except HTTPException as http_exc:
                stream_error = http_exc
            except Exception as exc:
                stream_error = exc
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
                        logger.info("Cancelled admin stream task after disconnect/finalization")
                if (
                    not assistant_message_persisted
                    and complete_ai_response
                    and local_conversation_id is not None
                ):
                    try:
                        async with async_session_factory() as db:
                            persistence_service = AdminChatBoundaryService(db)
                            await persistence_service.save_message(
                                conversation_id=local_conversation_id,
                                role=MessageRole.ASSISTANT,
                                content=complete_ai_response.replace("\x00", ""),
                            )
                            assistant_message_persisted = True
                    except Exception as persistence_exc:
                        logger.error(
                            (
                                "Failed to persist admin assistant message locally "
                                f"for conversation {local_conversation_id}: {persistence_exc}"
                            ),
                            exc_info=True,
                        )
                if assistant_message_persisted:
                    if pending_terminal_event is not None:
                        await websocket.send_json(pending_terminal_event)
                    await websocket.send_json(normalize_streaming_event({"type": "persisted"}))
                elif pending_terminal_event is not None and stream_error is None:
                    await websocket.send_json(
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
                        )
                    )
                if isinstance(stream_error, HTTPException):
                    await websocket.send_json(
                        normalize_streaming_event(
                            {
                                "type": "error",
                                "payload": {
                                    "details": str(stream_error.detail),
                                    "status_code": stream_error.status_code,
                                },
                            }
                        )
                    )
                    continue
                if isinstance(stream_error, Exception):
                    continue

    except WebSocketDisconnect:
        logger.info("Admin WebSocket disconnected")


@router.get(
    "/api/chat/latest",
    summary="استرجاع آخر محادثة (Get Latest Conversation)",
    response_model=ConversationDetailsResponse | None,
)
async def get_latest_chat(
    actor: User = Depends(get_actor_user),
    service: AdminChatBoundaryService = Depends(get_admin_service),
) -> ConversationDetailsResponse | None:
    """
    استرجاع تفاصيل آخر محادثة للمستخدم الحالي.
    مفيد لاستعادة الحالة عند إعادة تحميل الصفحة.
    """
    if not actor.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")
    conversation_data = await service.get_latest_conversation_details(actor)
    if not conversation_data:
        return None
    return ConversationDetailsResponse.model_validate(conversation_data)


@router.get(
    "/api/conversations",
    summary="سرد المحادثات (List Conversations)",
    response_model=list[ConversationSummaryResponse],
)
async def list_conversations(
    actor: User = Depends(get_actor_user),
    service: AdminChatBoundaryService = Depends(get_admin_service),
) -> list[ConversationSummaryResponse]:
    """
    استرجاع قائمة بجميع محادثات المستخدم.

    الخدمة تعيد البيانات متوافقة مع Schema مباشرة.
    """
    results = await service.list_user_conversations(actor)
    return [ConversationSummaryResponse.model_validate(r) for r in results]


@router.get(
    "/api/conversations/{conversation_id}",
    summary="تفاصيل المحادثة (Conversation Details)",
    response_model=ConversationDetailsResponse,
)
async def get_conversation(
    conversation_id: int,
    actor: User = Depends(get_actor_user),
    service: AdminChatBoundaryService = Depends(get_admin_service),
) -> ConversationDetailsResponse:
    """
    استرجاع الرسائل والتفاصيل لمحادثة محددة.
    """
    data = await service.get_conversation_details(actor, conversation_id)
    return ConversationDetailsResponse.model_validate(data)
