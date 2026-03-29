"""
واجهة برمجة تطبيقات محادثة العملاء القياسيين.

توفر نقاط النهاية الخاصة بالمستخدمين القياسيين للوصول إلى محادثة تعليمية
مع فرض سياسات الأمان والملكية.
"""

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
            question = str(payload.get("question", "")).strip()
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

            try:
                async for event in orchestrator_client.chat_with_agent(
                    question=question,
                    user_id=actor.id,
                    conversation_id=original_conversation_id,
                    context={
                        "chat_scope": "customer",
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
                        if original_conversation_id:
                            # Rewrite to the established local sequence
                            normalized_event["payload"]["conversation_id"] = (
                                original_conversation_id
                            )
                        else:
                            # Strip it to avoid overwriting local state with a foreign ID
                            normalized_event["payload"].pop("conversation_id", None)

                    await websocket.send_json(normalized_event)
            except HTTPException as http_exc:
                logger.error(
                    f"HTTPException in compatibility facade stream: {http_exc}", exc_info=True
                )
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
                logger.error(f"Error in compatibility facade stream: {exc}", exc_info=True)
                await websocket.send_json(
                    normalize_streaming_event(
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
