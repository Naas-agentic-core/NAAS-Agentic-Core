"""اختبارات واجهات دردشة العملاء بعد إزالة WS المحلي."""

from fastapi.testclient import TestClient


def test_customer_chat_history_routes_exist(test_app) -> None:
    """يتحقق من بقاء واجهات التاريخ HTTP معرفة في التطبيق."""

    with TestClient(test_app) as client:
        latest = client.get("/api/chat/latest")
        conversations = client.get("/api/chat/conversations")

    assert latest.status_code in {200, 401, 403}
    assert conversations.status_code in {200, 401, 403}


def test_customer_chat_ws_path_is_decommissioned(test_app) -> None:
    """يتحقق من إلغاء WS المحلي للعملاء لمنع split-brain."""

    with TestClient(test_app) as client:
        response = client.get("/api/chat/ws")
    assert response.status_code == 404
