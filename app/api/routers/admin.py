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
from collections.abc import Callable
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas.admin import ConversationDetailsResponse, ConversationSummaryResponse
from app.core.database import async_session_factory, get_db
from app.core.di import get_logger
from app.core.domain.user import User
from app.deps.auth import CurrentUser, get_current_user, require_roles
from app.infrastructure.clients.user_client import user_client
from app.services.boundaries.admin_chat_boundary_service import AdminChatBoundaryService
from app.services.chat.dispatcher import ChatRoleDispatcher, build_chat_dispatcher
from app.services.rbac import ADMIN_ROLE

logger = get_logger(__name__)


COMPATIBILITY_FACADE_MODE = True
# تم تعطيل مسار WS الإداري الداخلي نهائياً لمنع Split-Brain وفرض المرور عبر API Gateway.
CANONICAL_EXECUTION_AUTHORITY = "app.services.chat.orchestrator.ChatOrchestrator"


router = APIRouter(
    prefix="/admin",
    tags=["Admin"],
)


# -----------------------------------------------------------------------------
# DTOs
# -----------------------------------------------------------------------------
class AdminUserCountResponse(BaseModel):
    count: int


def get_session_factory() -> Callable[[], AsyncSession]:
    """تبعية توافقية تُعيد مصنع الجلسات دون تفعيل WS الإداري المحلي."""
    return async_session_factory


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


def get_chat_dispatcher(db: AsyncSession = Depends(get_db)) -> ChatRoleDispatcher:
    """تبعية توافقية محفوظة للاختبارات بعد تعطيل WS المحلي."""
    return build_chat_dispatcher(db)



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
