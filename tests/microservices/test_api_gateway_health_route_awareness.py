"""اختبارات Characterization لتأكد أن صحة البوابة تعكس مسارات chat الفعلية."""

from __future__ import annotations

from fastapi.testclient import TestClient

from microservices.api_gateway import main
from microservices.api_gateway.config import settings


def test_gateway_health_defaults_to_orchestrator_chat_mode(monkeypatch) -> None:
    """يثبت السلوك الآمن الافتراضي: chat mode = orchestrator بدون rollout."""

    async def fake_get(url: str, timeout: float = 2.0):  # noqa: ARG001
        class _Response:
            status_code = 200

        return _Response()

    monkeypatch.setattr(main.proxy_handler.client, "get", fake_get)
    monkeypatch.setattr(settings, "ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT", 0)
    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 0)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_route_mode"] == "orchestrator"
    assert "conversation_service" not in payload["dependencies"]
    assert "orchestrator_service" in payload["dependencies"]


def test_gateway_health_includes_conversation_when_chat_rollout_enabled(monkeypatch) -> None:
    """يثبت أن readiness أصبح route-aware عند تفعيل rollout."""

    async def fake_get(url: str, timeout: float = 2.0):  # noqa: ARG001
        class _Response:
            status_code = 200

        return _Response()

    monkeypatch.setattr(main.proxy_handler.client, "get", fake_get)
    monkeypatch.setattr(settings, "ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT", 10)
    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 0)

    response = TestClient(main.app).get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["chat_route_mode"] == "conversation"
    assert "conversation_service" in payload["dependencies"]
    assert "orchestrator_service" in payload["dependencies"]
