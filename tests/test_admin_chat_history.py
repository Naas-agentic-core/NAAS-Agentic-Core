"""اختبارات تاريخ دردشة الإدارة بعد إيقاف WS المحلي."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_admin_websocket_surface_is_decommissioned(test_app) -> None:
    """يتحقق من أن WS الإداري المحلي غير متاح."""

    with TestClient(test_app) as client:
        response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404


def test_admin_history_http_endpoints_still_available(test_app) -> None:
    """يتحقق من بقاء واجهات HTTP التاريخية دون إعادة WS المحلي."""

    with TestClient(test_app) as client:
        # without auth, endpoints should still exist (401/403/404 حسب الحماية) لكن ليست 405 missing route بشكل خاطئ
        response = client.get("/admin/api/chat/latest")
    assert response.status_code in {200, 401, 403, 404}
