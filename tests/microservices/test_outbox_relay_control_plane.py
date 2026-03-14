"""اختبارات مسار التحكم اليدوي للـ Outbox relay داخل orchestrator."""

from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from microservices.orchestrator_service.src.api import routes
from microservices.orchestrator_service.src.core.database import get_db


class _FakeManager:
    """مدير وهمي لإرجاع ملخص relay والتحقق من معاملات الاستدعاء."""

    def __init__(self, session):
        _ = session
        self.calls: list[tuple[int, int, int]] = []

    async def relay_outbox_events(
        self,
        *,
        batch_size: int,
        max_failed_attempts: int,
        processing_timeout_seconds: int = 300,
    ) -> dict[str, int]:
        self.calls.append((batch_size, max_failed_attempts, processing_timeout_seconds))
        return {"processed": 1, "published": 1, "failed": 0, "skipped": 0}


def _build_test_app() -> FastAPI:
    app = FastAPI()
    app.include_router(routes.router)
    return app


def test_trigger_outbox_relay_requires_admin_access(monkeypatch) -> None:
    """يرفض endpoint relay بدون مصادقة داخلية/إدارية."""

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY="x" * 40),
    )

    app = _build_test_app()

    def mock_get_db():
        return object()

    app.dependency_overrides[get_db] = mock_get_db
    client = TestClient(app)

    response = client.post("/api/v1/system/outbox/relay")
    assert response.status_code == 401


def test_trigger_outbox_relay_normalizes_limits_and_returns_summary(monkeypatch) -> None:
    """يشغّل relay يدويًا ويطبع القيم ضمن الحدود الآمنة."""

    fake_manager = _FakeManager(session=object())

    def _manager_factory(session):
        _ = session
        return fake_manager

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY="x" * 40),
    )
    monkeypatch.setattr(routes, "MissionStateManager", _manager_factory)

    app = _build_test_app()

    def mock_get_db_trigger():
        return object()

    app.dependency_overrides[get_db] = mock_get_db_trigger
    client = TestClient(app)

    response = client.post(
        "/api/v1/system/outbox/relay?batch_size=999&max_failed_attempts=99",
        headers={"x-internal-admin-key": "internal-key-1234567890"},
    )

    assert response.status_code == 200
    assert response.json() == {"processed": 1, "published": 1, "failed": 0, "skipped": 0}
    assert fake_manager.calls == [(200, 10, 300)]


def test_trigger_outbox_relay_normalizes_processing_timeout(monkeypatch) -> None:
    """يضبط processing_timeout ضمن الحدود الآمنة قبل تمريره إلى relay."""

    fake_manager = _FakeManager(session=object())

    def _manager_factory(session):
        _ = session
        return fake_manager

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY="x" * 40),
    )
    monkeypatch.setattr(routes, "MissionStateManager", _manager_factory)

    app = _build_test_app()

    def mock_get_db_timeout():
        return object()

    app.dependency_overrides[get_db] = mock_get_db_timeout
    client = TestClient(app)

    response = client.post(
        "/api/v1/system/outbox/relay?processing_timeout_seconds=1",
        headers={"x-internal-admin-key": "internal-key-1234567890"},
    )

    assert response.status_code == 200
    assert fake_manager.calls == [(50, 3, 5)]


def test_outbox_status_requires_admin_access(monkeypatch) -> None:
    """يرفض endpoint status دون اعتماد إداري/داخلي."""

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY="x" * 40),
    )

    app = _build_test_app()

    def mock_get_db_status_no_admin():
        return object()

    app.dependency_overrides[get_db] = mock_get_db_status_no_admin
    client = TestClient(app)

    response = client.get("/api/v1/system/outbox/status")
    assert response.status_code == 401


def test_outbox_status_returns_operational_snapshot(monkeypatch) -> None:
    """يعرض endpoint status صورة تشغيلية ثابتة قابلة للمراقبة."""

    class _StatusManager:
        def __init__(self, session) -> None:
            _ = session

        async def get_outbox_operational_snapshot(self) -> dict[str, int | str | None]:
            return {
                "pending": 2,
                "processing": 1,
                "failed": 3,
                "published": 5,
                "oldest_pending_age_seconds": 42,
                "generated_at": "2026-01-01T00:00:00+00:00",
            }

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY="x" * 40),
    )
    monkeypatch.setattr(routes, "MissionStateManager", _StatusManager)

    app = _build_test_app()

    def mock_get_db_status_operational():
        return object()

    app.dependency_overrides[get_db] = mock_get_db_status_operational
    client = TestClient(app)

    response = client.get(
        "/api/v1/system/outbox/status",
        headers={"x-internal-admin-key": "internal-key-1234567890"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "pending": 2,
        "processing": 1,
        "failed": 3,
        "published": 5,
        "oldest_pending_age_seconds": 42,
        "generated_at": "2026-01-01T00:00:00+00:00",
    }




def test_admin_graph_access_node_is_fail_closed() -> None:
    """يتأكد أن عقدة الوصول الإدارية لم تعد تعمل بمنطق السماح العام."""

    module_text = Path(
        "microservices/orchestrator_service/src/services/overmind/graph/admin.py"
    ).read_text(encoding="utf-8")

    assert "ADMIN_ACCESS_DENIED" in module_text
    assert "Allow all for now" not in module_text


def test_admin_tool_invoke_count_python_files_success(monkeypatch) -> None:
    """يتأكد أن أداة عد ملفات بايثون تعمل end-to-end عبر endpoint الإداري."""

    class _Registry:
        def get(self, name: str):
            if name != "admin.count_python_files":
                return None

            async def _tool(**_kwargs):
                return 321

            return _tool

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY="x" * 40),
    )
    monkeypatch.setattr(routes, "get_registry", lambda: _Registry())

    app = _build_test_app()

    def mock_get_db_tool():
        return object()

    app.dependency_overrides[get_db] = mock_get_db_tool
    client = TestClient(app)

    response = client.post(
        "/api/v1/tools/admin.count_python_files/invoke",
        headers={"x-internal-admin-key": "internal-key-1234567890"},
        json={},
    )

    assert response.status_code == 200
    assert response.json() == {"status": "success", "result": 321}


def test_admin_tool_invoke_sanitizes_tool_errors(monkeypatch) -> None:
    """يتأكد أن أخطاء أدوات الإدارة تُعاد برسالة آمنة دون تسريب الاستثناء الخام."""

    class _Registry:
        def get(self, name: str):
            if name != "admin.count_python_files":
                return None

            async def _tool(**_kwargs):
                raise RuntimeError("sensitive-tool-trace")

            return _tool

    monkeypatch.setattr(
        routes,
        "get_settings",
        lambda: SimpleNamespace(ADMIN_TOOL_API_KEY="internal-key-1234567890", SECRET_KEY="x" * 40),
    )
    monkeypatch.setattr(routes, "get_registry", lambda: _Registry())

    app = _build_test_app()

    def mock_get_db_tool_error():
        return object()

    app.dependency_overrides[get_db] = mock_get_db_tool_error
    client = TestClient(app)

    response = client.post(
        "/api/v1/tools/admin.count_python_files/invoke",
        headers={"x-internal-admin-key": "internal-key-1234567890"},
        json={},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "error"
    assert "sensitive-tool-trace" not in payload["message"]
    assert "request_id=" in payload["message"]
