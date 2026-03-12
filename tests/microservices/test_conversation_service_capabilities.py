"""اختبارات إعلان قدرات conversation-service لدعم admission control."""

from __future__ import annotations

from fastapi.testclient import TestClient

from microservices.conversation_service.main import app


def test_conversation_health_declares_stub_by_default(monkeypatch) -> None:
    """يعلن الخدمة بوضع stub افتراضيًا لمنع promotion غير مقصود."""
    monkeypatch.delenv("CONVERSATION_CAPABILITY_LEVEL", raising=False)
    response = TestClient(app).get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["capability_level"] == "stub"
    assert payload["parity_ready"] is False


def test_conversation_health_can_declare_parity_ready(monkeypatch) -> None:
    """يسمح بإعلان الجاهزية صراحة عند التحقق من parity."""
    monkeypatch.setenv("CONVERSATION_CAPABILITY_LEVEL", "parity_ready")
    response = TestClient(app).get("/health")
    payload = response.json()

    assert response.status_code == 200
    assert payload["capability_level"] == "parity_ready"
    assert payload["parity_ready"] is True
