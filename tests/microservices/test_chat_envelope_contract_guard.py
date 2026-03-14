"""اختبارات حراسة لعقود chat HTTP/WS لمنع الانحراف غير المقصود في الـ envelopes."""

from __future__ import annotations

import jwt
from fastapi.testclient import TestClient

from microservices.orchestrator_service.main import app
from microservices.orchestrator_service.src.core.config import get_settings


def test_chat_http_health_envelope_is_stable() -> None:
    """يثبت shape استجابة GET /api/chat/messages المستخدمة أماميًا."""

    response = TestClient(app).get("/api/chat/messages")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "orchestrator-service"
    assert payload["control_plane"] == "stategraph"


def test_chat_ws_error_envelope_for_invalid_payload_shape() -> None:
    """يثبت envelope الخطأ عند إرسال payload غير قاموسي على WS chat."""

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")

    with TestClient(app).websocket_connect(f"/api/chat/ws?token={token}") as ws:
        ws.send_json(["invalid"])
        event = ws.receive_json()

    assert event == {"status": "error", "message": "invalid payload"}


def test_chat_ws_error_envelope_for_missing_objective() -> None:
    """يثبت envelope الخطأ عند غياب question/objective في WS chat."""

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")

    with TestClient(app).websocket_connect(f"/api/chat/ws?token={token}") as ws:
        ws.send_json({"context": {"x": 1}})
        event = ws.receive_json()

    assert event == {"status": "error", "message": "question/objective required"}


def test_chat_http_messages_missing_objective_keeps_422_contract() -> None:
    """يثبت أن POST /api/chat/messages يحافظ على 422 ورسالة الخطأ المتوقعة."""

    response = TestClient(app).post("/api/chat/messages", json={"context": {"x": 1}})

    assert response.status_code == 422
    assert response.json() == {"detail": "question/objective is required"}
