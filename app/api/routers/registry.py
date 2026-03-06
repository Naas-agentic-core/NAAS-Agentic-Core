"""
سجل موجهات API كمصدر حقيقة موحّد.
"""

from fastapi import APIRouter

from app.api.routers import (
    content,
    data_mesh,
    security,
    system,
    ums,
)

type RouterSpec = tuple[APIRouter, str]


def base_router_registry() -> list[RouterSpec]:
    """
    يبني سجل الموجهات الأساسية للتطبيق بدون موجه البوابة.
    """
    return [
        (system.root_router, ""),
        (system.router, ""),
        (security.router, "/api/security"),
        (data_mesh.router, "/api/v1/data-mesh"),
        (ums.router, "/api/v1"),
        (content.router, ""),
    ]
