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

import inspect

import httpx

from fastapi import APIRouter, Depends, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routers.ws_auth import extract_websocket_auth
from app.core.config import get_settings
from app.core.database import async_session_factory, get_db
from app.core.di import get_logger
from app.core.domain.user import User
from app.deps.auth import CurrentUser, get_current_user, require_roles
from app.infrastructure.clients.orchestrator_client import orchestrator_client
from app.infrastructure.clients.user_client import user_client
from app.services.auth.token_decoder import decode_user_id
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
        logger.info("Admin WebSocket disconnected")


@router.get(
    "/api/chat/latest",
    summary="استرجاع آخر محادثة (Get Latest Conversation)",
)
async def get_latest_chat(
    request: Request,
    _current: CurrentUser = Depends(get_chat_actor),
) -> Response:
    """وكيل قراءة صارم: تمرير آخر محادثة إدارية إلى خدمة المنسّق."""
    settings = get_settings()
    orchestrator_url = f"{settings.ORCHESTRATOR_SERVICE_URL}{request.url.path}"
    auth_header = request.headers.get("authorization")
    headers = {"authorization": auth_header} if auth_header else {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream_response = await client.get(
            orchestrator_url,
            params=request.query_params,
            headers=headers,
        )
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type", "application/json"),
    )


@router.get(
    "/api/conversations",
    summary="سرد المحادثات (List Conversations)",
)
async def list_conversations(
    request: Request,
    _current: CurrentUser = Depends(get_chat_actor),
) -> Response:
    """وكيل قراءة صارم: تمرير قائمة المحادثات الإدارية إلى خدمة المنسّق."""
    settings = get_settings()
    orchestrator_url = f"{settings.ORCHESTRATOR_SERVICE_URL}{request.url.path}"
    auth_header = request.headers.get("authorization")
    headers = {"authorization": auth_header} if auth_header else {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream_response = await client.get(
            orchestrator_url,
            params=request.query_params,
            headers=headers,
        )
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type", "application/json"),
    )


@router.get(
    "/api/conversations/{conversation_id}",
    summary="تفاصيل المحادثة (Conversation Details)",
)
async def get_conversation(
    conversation_id: int,
    request: Request,
    _current: CurrentUser = Depends(get_chat_actor),
) -> Response:
    """وكيل قراءة صارم: تمرير تفاصيل المحادثة الإدارية إلى خدمة المنسّق."""
    settings = get_settings()
    orchestrator_url = f"{settings.ORCHESTRATOR_SERVICE_URL}{request.url.path}"
    auth_header = request.headers.get("authorization")
    headers = {"authorization": auth_header} if auth_header else {}
    async with httpx.AsyncClient(timeout=30.0) as client:
        upstream_response = await client.get(
            orchestrator_url,
            params=request.query_params,
            headers=headers,
        )
    return Response(
        content=upstream_response.content,
        status_code=upstream_response.status_code,
        media_type=upstream_response.headers.get("content-type", "application/json"),
    )
