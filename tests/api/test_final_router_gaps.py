"""اختبارات فجوات الراوتر بعد إيقاف WebSocket المحلي للدردشة."""

from fastapi.testclient import TestClient


def test_customer_ws_route_is_removed_from_router_surface(test_app) -> None:
    """يتحقق من أن `/api/chat/ws` غير موجود في راوتر العملاء المونوليثي."""

    client = TestClient(test_app)
    response = client.get("/api/chat/ws")
    assert response.status_code == 404
