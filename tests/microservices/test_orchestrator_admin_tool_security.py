"""اختبارات أمان لمسارات أدوات الإدارة مع سياسة fail-closed."""

from __future__ import annotations

import sys
from types import ModuleType, SimpleNamespace

import jwt
from fastapi import FastAPI
from fastapi.testclient import TestClient

# Provide a lightweight redis.asyncio stub for environments without redis dependency.
if "redis" not in sys.modules:
    redis_module = ModuleType("redis")
    redis_asyncio_module = ModuleType("redis.asyncio")

    class _RedisStub:
        async def publish(self, *_args, **_kwargs) -> None:
            return None

        def pubsub(self):
            return self

        async def subscribe(self, *_args, **_kwargs) -> None:
            return None

        async def listen(self):
            if False:
                yield {}

        async def unsubscribe(self, *_args, **_kwargs) -> None:
            return None

        async def close(self) -> None:
            return None

    def _from_url(*_args, **_kwargs):
        return _RedisStub()

    redis_asyncio_module.from_url = _from_url
    redis_module.asyncio = redis_asyncio_module
    sys.modules["redis"] = redis_module
    sys.modules["redis.asyncio"] = redis_asyncio_module

from microservices.orchestrator_service.src.api import routes
from microservices.orchestrator_service.src.contracts.admin_tools import ADMIN_TOOL_CONTRACT


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(routes.router)
    return app


def test_admin_tool_routes_reject_unauthenticated_requests(monkeypatch) -> None:
    """يرفض الوصول إلى أدوات الإدارة دون اعتماد صريح."""
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY="x" * 40),
    )

    tool_name = next(iter(ADMIN_TOOL_CONTRACT))
    client = TestClient(_build_test_app())
    response = client.get(f"/api/v1/tools/{tool_name}/health")

    assert response.status_code == 401


def test_admin_tool_routes_allow_internal_key(monkeypatch) -> None:
    """يسمح بالوصول الداخلي فقط عند إرسال مفتاح إداري صحيح."""
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY="x" * 40),
    )

    tool_name = next(iter(ADMIN_TOOL_CONTRACT))
    client = TestClient(_build_test_app())
    response = client.get(
        f"/api/v1/tools/{tool_name}/health",
        headers={"x-internal-admin-key": "internal-key-1234567890"},
    )

    assert response.status_code == 200


def test_admin_tool_routes_reject_non_admin_bearer(monkeypatch) -> None:
    """يرفض JWT صحيحاً لكنه بلا صلاحية إدارية عند الوصول لأدوات الإدارة."""
    secret = "x" * 40
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY=secret),
    )

    token = jwt.encode({"sub": "22", "role": "customer"}, secret, algorithm="HS256")
    tool_name = next(iter(ADMIN_TOOL_CONTRACT))
    client = TestClient(_build_test_app())
    response = client.get(
        f"/api/v1/tools/{tool_name}/health",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 403


def test_admin_tool_routes_allow_admin_bearer(monkeypatch) -> None:
    """يسمح JWT إداري صريح بالوصول مع بقاء السياسة fail-closed لغير ذلك."""
    secret = "x" * 40
    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY=secret),
    )

    token = jwt.encode({"sub": "1", "role": "admin", "is_admin": True}, secret, algorithm="HS256")
    tool_name = next(iter(ADMIN_TOOL_CONTRACT))
    client = TestClient(_build_test_app())
    response = client.get(
        f"/api/v1/tools/{tool_name}/health",
        headers={"Authorization": f"Bearer {token}"},
    )

    assert response.status_code == 200
