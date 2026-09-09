"""
RBAC Service for User Service.
"""

from __future__ import annotations

from typing import Final

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from microservices.user_service.models import Permission, Role, RolePermission, User, UserRole
from microservices.user_service.src.core.common import utc_now

STANDARD_ROLE: Final[str] = "STANDARD_USER"
ADMIN_ROLE: Final[str] = "ADMIN"

USERS_READ: Final[str] = "USERS_READ"
USERS_WRITE: Final[str] = "USERS_WRITE"
ROLES_WRITE: Final[str] = "ROLES_WRITE"
AUDIT_READ: Final[str] = "AUDIT_READ"
AI_CONFIG_READ: Final[str] = "AI_CONFIG_READ"
AI_CONFIG_WRITE: Final[str] = "AI_CONFIG_WRITE"
ACCOUNT_SELF: Final[str] = "ACCOUNT_SELF"
QA_SUBMIT: Final[str] = "QA_SUBMIT"

DEFAULT_ROLE_PERMISSIONS: Final[dict[str, set[str]]] = {
    STANDARD_ROLE: {QA_SUBMIT, ACCOUNT_SELF},
    ADMIN_ROLE: {
        USERS_READ,
        USERS_WRITE,
        ROLES_WRITE,
        AUDIT_READ,
        AI_CONFIG_READ,
        AI_CONFIG_WRITE,
        QA_SUBMIT,
        ACCOUNT_SELF,
    },
}

PERMISSION_DESCRIPTIONS: Final[dict[str, str]] = {
    USERS_READ: "Read User Data",
    USERS_WRITE: "Modify/Create User Accounts",
    ROLES_WRITE: "Assign Roles (Break-Glass)",
    AUDIT_READ: "Read Audit Logs",
    AI_CONFIG_READ: "Read AI Config",
    AI_CONFIG_WRITE: "Write AI Config",
    ACCOUNT_SELF: "Manage Own Account",
    QA_SUBMIT: "Submit QA Questions",
}


class RBACService:
    """
    Service for Role-Based Access Control.
    """

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def ensure_seed(self) -> None:
        """Seed default roles and permissions."""
        await self._seed_permissions()
        await self._seed_roles()

    async def _seed_permissions(self) -> None:
        existing = await self.session.execute(select(Permission))
        existing_names = {perm.name for perm in existing.scalars().all()}
        missing = set(PERMISSION_DESCRIPTIONS.keys()) - existing_names
        if not missing:
            return

        for name in sorted(missing):
            self.session.add(Permission(name=name, description=PERMISSION_DESCRIPTIONS.get(name)))
        await self.session.commit()

    async def _seed_roles(self) -> None:
        existing = await self.session.execute(select(Role))
        existing_names = {role.name for role in existing.scalars().all()}
        missing_roles = set(DEFAULT_ROLE_PERMISSIONS.keys()) - existing_names
        if not missing_roles:
            await self._sync_role_permissions()
            return

        for role_name in sorted(missing_roles):
            self.session.add(Role(name=role_name, description=f"Role {role_name}"))
        await self.session.commit()
        await self._sync_role_permissions()

    async def _sync_role_permissions(self) -> None:
        perms_map = await self._load_permissions()
        roles_map = await self._load_roles()

        for role_name, perm_names in DEFAULT_ROLE_PERMISSIONS.items():
            role = roles_map.get(role_name)
            if not role:
                continue
            desired_ids = {perms_map[name].id for name in perm_names if name in perms_map}
            await self._reconcile_role_permissions(role.id, desired_ids)

    async def _reconcile_role_permissions(
        self, role_id: int, desired_permission_ids: set[int]
    ) -> None:
        existing_links = await self.session.execute(
            select(RolePermission.permission_id).where(RolePermission.role_id == role_id)
        )
        existing_ids = {row[0] for row in existing_links.all() if row[0] is not None}
        to_remove = existing_ids - desired_permission_ids
        to_add = desired_permission_ids - existing_ids

        if to_remove:
            await self.session.execute(
                delete(RolePermission).where(
                    RolePermission.role_id == role_id,
                    RolePermission.permission_id.in_(to_remove),
                )
            )
        for perm_id in sorted(to_add):
            self.session.add(
                RolePermission(role_id=role_id, permission_id=perm_id, created_at=utc_now())
            )
        await self.session.commit()

    async def assign_role(self, user: User, role_name: str) -> None:
        roles_map = await self._load_roles()
        role = roles_map.get(role_name)
        if role is None or role.id is None:
            raise ValueError(f"Role {role_name} not found")

        link_exists = await self.session.execute(
            select(UserRole).where(UserRole.user_id == user.id, UserRole.role_id == role.id)
        )
        if link_exists.scalar_one_or_none():
            return

        self.session.add(UserRole(user_id=user.id, role_id=role.id))
        await self.session.commit()

    async def user_roles(self, user_id: int) -> list[str]:
        result = await self.session.execute(
            select(Role.name)
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .where(UserRole.user_id == user_id)
        )
        return [row[0] for row in result.all()]

    async def user_permissions(self, user_id: int) -> set[str]:
        result = await self.session.execute(
            select(Permission.name)
            .select_from(UserRole)
            .join(Role, Role.id == UserRole.role_id)
            .join(RolePermission, RolePermission.role_id == Role.id)
            .join(Permission, Permission.id == RolePermission.permission_id)
            .where(UserRole.user_id == user_id)
        )
        return {row[0] for row in result.all()}

    async def _load_permissions(self) -> dict[str, Permission]:
        result = await self.session.execute(select(Permission))
        perms = result.scalars().all()
        return {perm.name: perm for perm in perms if perm.id is not None}

    async def _load_roles(self) -> dict[str, Role]:
        result = await self.session.execute(select(Role))
        roles = result.scalars().all()
        return {role.name: role for role in roles if role.id is not None}
