"""
UMS Routes for User Service.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import desc, select

from microservices.user_service.models import AuditLog, User
from microservices.user_service.security import get_auth_service, get_current_user, require_role
from microservices.user_service.src.schemas.ums import (
    AdminCreateUserRequest,
    ChangePasswordRequest,
    PasswordResetConfirmRequest,
    PasswordResetRequest,
    PasswordResetResponse,
    ProfileUpdateRequest,
    RoleAssignmentRequest,
    StatusUpdateRequest,
    UserOut,
)
from microservices.user_service.src.services.auth.service import AuthService
from microservices.user_service.src.services.rbac import ADMIN_ROLE

router = APIRouter(tags=["UMS"])


@router.get("/users/me", response_model=UserOut)
async def get_my_profile(
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    roles = await service.rbac.user_roles(user.id)
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        status=user.status,
        roles=roles,
    )


@router.patch("/users/me", response_model=UserOut)
async def update_my_profile(
    payload: ProfileUpdateRequest,
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    updated_user = await service.update_profile(
        user=user,
        full_name=payload.full_name,
        email=payload.email,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    roles = await service.rbac.user_roles(updated_user.id)
    return UserOut(
        id=updated_user.id,
        email=updated_user.email,
        full_name=updated_user.full_name,
        is_active=updated_user.is_active,
        status=updated_user.status,
        roles=roles,
    )


@router.post("/users/me/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    request: Request,
    user: User = Depends(get_current_user),
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await service.change_password(
        user=user,
        current_password=payload.current_password,
        new_password=payload.new_password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    return {"status": "password_changed"}


@router.post("/auth/password/forgot", response_model=PasswordResetResponse)
async def forgot_password(
    payload: PasswordResetRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> PasswordResetResponse:
    token, expires_in = await service.request_password_reset(
        email=payload.email,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    return PasswordResetResponse(reset_token=token, expires_in=expires_in)


@router.post("/auth/password/reset")
async def reset_password(
    payload: PasswordResetConfirmRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> dict[str, str]:
    await service.reset_password(
        token=payload.token,
        new_password=payload.new_password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    return {"status": "password_reset"}


# --- Admin Routes ---


@router.get(
    "/admin/users", response_model=list[UserOut], dependencies=[Depends(require_role(ADMIN_ROLE))]
)
async def list_users_admin(
    service: AuthService = Depends(get_auth_service),
) -> list[UserOut]:
    result = await service.session.execute(select(User))
    users = result.scalars().all()

    output = []
    for u in users:
        roles = await service.rbac.user_roles(u.id)
        output.append(
            UserOut(
                id=u.id,
                email=u.email,
                full_name=u.full_name,
                is_active=u.is_active,
                status=u.status,
                roles=roles,
            )
        )
    return output


@router.post(
    "/admin/users", response_model=UserOut, dependencies=[Depends(require_role(ADMIN_ROLE))]
)
async def create_user_admin(
    payload: AdminCreateUserRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    user = await service.register_user(
        full_name=payload.full_name,
        email=payload.email,
        password=payload.password,
        ip=request.client.host if request.client else None,
        user_agent=request.headers.get("User-Agent"),
    )
    if payload.is_admin:
        await service.promote_to_admin(user=user)

    roles = await service.rbac.user_roles(user.id)
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        status=user.status,
        roles=roles,
    )


@router.patch(
    "/admin/users/{user_id}/status",
    response_model=UserOut,
    dependencies=[Depends(require_role(ADMIN_ROLE))],
)
async def update_user_status(
    user_id: int,
    payload: StatusUpdateRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    user = await service.session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    user.status = payload.status
    user.is_active = payload.status == "active"
    await service.session.commit()

    roles = await service.rbac.user_roles(user.id)
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        status=user.status,
        roles=roles,
    )


@router.post(
    "/admin/users/{user_id}/roles",
    response_model=UserOut,
    dependencies=[Depends(require_role(ADMIN_ROLE))],
)
async def assign_role(
    user_id: int,
    payload: RoleAssignmentRequest,
    service: AuthService = Depends(get_auth_service),
) -> UserOut:
    user = await service.session.get(User, user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    if payload.role_name == ADMIN_ROLE:
        await service.promote_to_admin(user=user)
    else:
        await service.rbac.assign_role(user, payload.role_name)

    roles = await service.rbac.user_roles(user.id)
    return UserOut(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_active=user.is_active,
        status=user.status,
        roles=roles,
    )


@router.get(
    "/admin/audit",
    response_model=list[dict],
    dependencies=[Depends(require_role(ADMIN_ROLE))],
)
async def list_audit(
    service: AuthService = Depends(get_auth_service),
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    if limit < 1 or limit > 500:
        raise HTTPException(status_code=400, detail="limit out of range")
    if offset < 0:
        raise HTTPException(status_code=400, detail="offset out of range")

    result = await service.session.execute(
        select(AuditLog).order_by(desc(AuditLog.timestamp)).limit(limit).offset(offset)
    )
    rows = result.scalars().all()
    return [row.model_dump() for row in rows]
