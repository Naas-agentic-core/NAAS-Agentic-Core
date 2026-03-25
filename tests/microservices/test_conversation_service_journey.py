"""اختبارات رحلة تركيبية لخدمة Conversation عبر HTTP وWebSocket."""

from __future__ import annotations

from unittest.mock import patch

from fastapi.testclient import TestClient

from microservices.conversation_service.main import app


def test_conversation_health_and_http_chat() -> None:
    """يتأكد أن الخدمة الجديدة تقدم health وHTTP chat بشكل متوافق مبدئيًا."""
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["service"] == "conversation-service"

    chat = client.get("/api/chat/messages")
    assert chat.status_code == 200
    assert chat.json()["status"] == "ok"


@patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"})
def test_conversation_ws_synthetic_journey_customer() -> None:
    """يراقب رحلة WS: اتصال ثم إرسال question ثم استقبال response envelope."""
    with TestClient(app).websocket_connect("/api/chat/ws") as ws:
        init_payload = ws.receive_json()
        assert init_payload["type"] == "conversation_init"

        ws.send_json({"question": "hello"})
        payload = ws.receive_json()

    assert payload["type"] == "assistant_delta"
    assert "conversation-service:hello" in payload["payload"]["content"]
