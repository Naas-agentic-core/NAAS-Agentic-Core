"""اختبارات تفرع الأدوار بعد إلغاء WS المحلي."""

from fastapi.testclient import TestClient


def test_admin_blocked_from_customer_chat(test_app) -> None:
    """يتحقق من أن مسار WS المحلي للعملاء غير متاح أساسًا."""

    with TestClient(test_app) as client:
        response = client.get("/api/chat/ws")
    assert response.status_code == 404
