"""اختبار توثيقي: مسار WS المحلي للأدوات مُعطّل بعد توحيد الملكية."""

from fastapi.testclient import TestClient


def test_tool_access_ws_surface_is_decommissioned(test_app) -> None:
    """يتحقق من أن اختبارات منع الأدوات عبر WS المحلي لم تعد قابلة للتشغيل."""

    with TestClient(test_app) as client:
        response = client.get("/api/chat/ws")
    assert response.status_code == 404
