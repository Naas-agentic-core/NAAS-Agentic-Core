"""
واجهة برمجة تطبيقات محادثة العملاء القياسيين.

توفر نقاط النهاية الخاصة بالمستخدمين القياسيين للوصول إلى محادثة تعليمية
مع فرض سياسات الأمان والملكية.
"""

from collections.abc import Callable
import os

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ws_auth import extract_websocket_auth
from app.api.schemas.customer_chat import CustomerConversationDetails, CustomerConversationSummary
from app.contracts.chat_events import ChatEventEnvelope, ChatEventPayload, ChatEventType
from app.core.ai_gateway import AIClient, get_ai_client
from app.core.config import get_settings
from app.core.database import async_session_factory, get_db
from app.core.di import get_logger
from app.core.domain.user import User
from app.deps.auth import CurrentUser, require_permissions
from app.services.auth.token_decoder import decode_user_id
from app.services.boundaries.customer_chat_boundary_service import CustomerChatBoundaryService
from app.services.chat.contracts import ChatDispatchRequest
from app.services.chat.dispatcher import ChatRoleDispatcher, build_chat_dispatcher
from app.services.chat.orchestrator import ChatOrchestrator
from app.services.rbac import QA_SUBMIT

logger = get_logger(__name__)

COMPATIBILITY_FACADE_MODE = True
CANONICAL_EXECUTION_AUTHORITY = "app.services.chat.orchestrator.ChatOrchestrator"

router = APIRouter(
    prefix="/api/chat",
    tags=["Customer Chat"],
)


def _is_unified_chat_event_protocol_enabled() -> bool:
    """يتحقق من تفعيل البروتوكول الموحّد للأحداث عبر راية تشغيل تدريجية."""
    return os.getenv("CHAT_USE_UNIFIED_EVENT_ENVELOPE", "0") == "1"


def _build_chat_event_envelope(
    *,
    event_type: ChatEventType,
    content: str | None = None,
    details: str | None = None,
    status_code: int | None = None,
) -> dict[str, object]:
    """ينشئ مغلف حدث موحّد ومتوافق مع العقد الرسمي دون حقول فارغة."""
    envelope = ChatEventEnvelope(
        type=event_type,
        payload=ChatEventPayload(
            content=content,
            details=details,
            status_code=status_code,
        ),
    )
    return envelope.model_dump(exclude_none=True)


def _normalize_streaming_event(event: object) -> dict[str, object]:
    """يوحّد حدث البث إلى ChatEventEnvelope عند تفعيل الراية مع إبقاء التوافق الخلفي."""
    if not _is_unified_chat_event_protocol_enabled():
        if isinstance(event, dict):
            return event
        return {"type": "delta", "payload": {"content": str(event)}}

    if not isinstance(event, dict):
        return _build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_DELTA,
            content=str(event),
        )

    raw_type = str(event.get("type", "assistant_delta"))
    payload_value = event.get("payload")
    payload = payload_value if isinstance(payload_value, dict) else {}

    if raw_type in ("status", ChatEventType.STATUS.value):
        status_value = payload.get("status_code")
        status_code = status_value if isinstance(status_value, int) else None
        return _build_chat_event_envelope(event_type=ChatEventType.STATUS, status_code=status_code)

    if raw_type in ("error", "assistant_error"):
        details = str(payload.get("details", "")) or str(payload.get("content", ""))
        status_value = payload.get("status_code")
        status_code = status_value if isinstance(status_value, int) else None
        return _build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_ERROR,
            details=details,
            status_code=status_code,
        )

    if raw_type == ChatEventType.ASSISTANT_FINAL.value:
        return _build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_FINAL,
            content=str(payload.get("content", "")),
        )

    content = str(payload.get("content", "")) if payload else str(event)
    return _build_chat_event_envelope(
        event_type=ChatEventType.ASSISTANT_DELTA,
        content=content,
    )


def get_session_factory() -> Callable[[], AsyncSession]:
    """تبعية لاسترجاع مصنع الجلسات."""
    return async_session_factory


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


def get_customer_service(db: AsyncSession = Depends(get_db)) -> CustomerChatBoundaryService:
    """تبعية للحصول على خدمة حدود محادثة العملاء."""
    return CustomerChatBoundaryService(db)


def get_chat_dispatcher(db: AsyncSession = Depends(get_db)) -> ChatRoleDispatcher:
    """تبعية للحصول على موزّع الدردشة حسب الدور."""
    return build_chat_dispatcher(db)


@router.websocket("/ws")
async def chat_stream_ws(
    websocket: WebSocket,
    ai_client: AIClient = Depends(get_ai_client),
    dispatcher: ChatRoleDispatcher = Depends(get_chat_dispatcher),
    session_factory: Callable[[], AsyncSession] = Depends(get_session_factory),
    db: AsyncSession = Depends(get_db),
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

    actor = await db.get(User, user_id)
    if actor is None or not actor.is_active:
        await websocket.close(code=4401)
        return

    await websocket.accept(subprotocol=selected_protocol)

    if actor.is_admin:
        await websocket.send_json(
            _normalize_streaming_event(
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
            question = str(payload.get("question", "")).strip()
            if not question:
                await websocket.send_json(
                    _normalize_streaming_event(
                        {"type": "error", "payload": {"details": "Question is required."}}
                    )
                )
                continue

            mission_type = payload.get("mission_type")
            metadata: dict[str, object] = {}
            if mission_type:
                metadata["mission_type"] = mission_type

            try:
                dispatch_request = ChatDispatchRequest(
                    question=question,
                    conversation_id=payload.get("conversation_id"),
                    ai_client=ai_client,
                    session_factory=session_factory,
                    metadata=metadata,
                )
                dispatch_result = await ChatOrchestrator.dispatch(
                    user=actor,
                    request=dispatch_request,
                    dispatcher=dispatcher,
                )
            except HTTPException as exc:
                await websocket.send_json(
                    _normalize_streaming_event(
                        {
                            "type": "error",
                            "payload": {"details": exc.detail, "status_code": exc.status_code},
                        }
                    )
                )
                continue

            await websocket.send_json(
                _normalize_streaming_event(
                    {"type": "status", "payload": {"status_code": dispatch_result.status_code}}
                )
            )

            try:
                async for event in dispatch_result.stream:
                    normalized_event = _normalize_streaming_event(event)
                    await websocket.send_json(normalized_event)
            except Exception as exc:
                logger.error(f"Error in chat stream: {exc}", exc_info=True)
                await websocket.send_json(
                    _normalize_streaming_event(
                        {
                            "type": "error",
                            "payload": {"details": str(exc), "status_code": 500},
                        }
                    )
                )
                continue

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
