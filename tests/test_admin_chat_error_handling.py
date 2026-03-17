"""اختبارات تعامل الأخطاء بعد إيقاف WS الإداري المحلي."""

from fastapi.testclient import TestClient


def test_chat_error_handling_no_auth(test_app) -> None:
    """يتحقق من عدم توفر WS الإداري المحلي حتى دون مصادقة."""

    with TestClient(test_app) as client:
        response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404


def test_chat_error_handling_with_auth_but_service_error(test_app) -> None:
    """يتحقق من أن المسار مُعطل كليًا وليس مجرد خطأ خدمة."""

    with TestClient(test_app) as client:
        response = client.get("/admin/api/chat/ws")
    assert response.status_code == 404
