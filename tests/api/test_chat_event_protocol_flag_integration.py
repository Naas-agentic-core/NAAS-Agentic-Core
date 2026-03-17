"""اختبارات علم البروتوكول بعد إلغاء WS المحلي من المونوليث."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_customer_ws_flag_paths_are_decommissioned(test_app) -> None:
    """يتحقق من أن قناة العملاء المحلية غير معروضة بغض النظر عن الأعلام."""

    with TestClient(test_app) as client:
        response = client.get("/api/chat/ws")
    assert response.status_code == 404


def test_admin_ws_flag_paths_are_decommissioned(test_app) -> None:
    """يتحقق من أن قناة الإدارة المحلية غير معروضة بغض النظر عن الأعلام."""

    with TestClient(test_app) as client:
        response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404
