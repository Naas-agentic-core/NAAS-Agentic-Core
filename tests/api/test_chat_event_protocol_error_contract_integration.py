"""اختبارات تكاملية بعد إيقاف WS المونوليثي: يجب ألّا يكون العقد المحلي قابلاً للاستدعاء."""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_customer_ws_error_contract_surface_is_decommissioned(test_app) -> None:
    """يتحقق من أن قناة العملاء WS المحلية لم تعد متاحة."""

    with TestClient(test_app) as client:
        response = client.get("/api/chat/ws")
    assert response.status_code == 404


def test_admin_ws_error_contract_surface_is_decommissioned(test_app) -> None:
    """يتحقق من أن قناة الإدارة WS المحلية لم تعد متاحة."""

    with TestClient(test_app) as client:
        response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404
