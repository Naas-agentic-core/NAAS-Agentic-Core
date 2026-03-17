"""Regression: لم يعد هناك WS محلي، لذا لا يجوز اختبار delta عبر المونوليث."""

from fastapi.testclient import TestClient


def test_chat_stream_surface_is_decommissioned(test_app) -> None:
    """يتحقق من أن واجهة WS المحلية مُزالة مما يمنع إعادة ظهور bug القديم."""

    with TestClient(test_app) as client:
        response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404
