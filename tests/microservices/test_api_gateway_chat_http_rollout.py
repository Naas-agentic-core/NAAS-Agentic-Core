"""اختبارات التوجيه التدريجي لمسار HTTP chat نحو Conversation Service."""

from __future__ import annotations

from fastapi.responses import PlainTextResponse
from fastapi.testclient import TestClient

from microservices.api_gateway import main
from microservices.api_gateway.config import settings
from microservices.api_gateway.security import verify_gateway_request


def test_chat_http_routes_to_conversation_on_full_rollout(monkeypatch) -> None:
    """يتأكد أن نسبة 100% توجه HTTP chat إلى Conversation Service عند تعطيل legacy."""
    calls: list[tuple[str, str]] = []

    async def fake_forward(request, target_url, path, **_kwargs):
        calls.append((target_url, path))
        return PlainTextResponse("ok")

    monkeypatch.setattr(main.proxy_handler, "forward", fake_forward)
    monkeypatch.setattr(settings, "ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT", 100)
    monkeypatch.setattr(settings, "CONVERSATION_PARITY_VERIFIED", True)
    monkeypatch.setattr(settings, "CONVERSATION_CAPABILITY_LEVEL", "parity_ready")
    monkeypatch.setattr(settings, "CONVERSATION_SERVICE_URL", "http://conversation-service:8010")
    main.app.dependency_overrides[verify_gateway_request] = lambda: True

    response = TestClient(main.app).get("/api/chat/messages")
    main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls == [("http://conversation-service:8010", "api/chat/messages")]


def test_chat_http_cutover_blocked_when_parity_not_verified(monkeypatch) -> None:
    """يمنع التوجيه إلى conversation حتى مع rollout=100 عندما parity غير موثقة."""
    calls: list[tuple[str, str]] = []

    async def fake_forward(request, target_url, path, **_kwargs):
        calls.append((target_url, path))
        return PlainTextResponse("ok")

    monkeypatch.setattr(main.proxy_handler, "forward", fake_forward)
    monkeypatch.setattr(settings, "ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT", 100)
    monkeypatch.setattr(settings, "CONVERSATION_PARITY_VERIFIED", False)
    monkeypatch.setattr(settings, "CONVERSATION_CAPABILITY_LEVEL", "stub")
    monkeypatch.setattr(settings, "ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    main.app.dependency_overrides[verify_gateway_request] = lambda: True

    response = TestClient(main.app).get("/api/chat/messages")
    main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls == [("http://orchestrator-service:8006", "api/chat/messages")]


def test_chat_http_cutover_blocked_when_capability_not_ready(monkeypatch) -> None:
    """يمنع التوجيه إلى conversation إذا كانت capability غير جاهزة حتى مع parity=true."""
    calls: list[tuple[str, str]] = []

    async def fake_forward(request, target_url, path, **_kwargs):
        calls.append((target_url, path))
        return PlainTextResponse("ok")

    monkeypatch.setattr(main.proxy_handler, "forward", fake_forward)
    monkeypatch.setattr(settings, "ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT", 100)
    monkeypatch.setattr(settings, "CONVERSATION_PARITY_VERIFIED", True)
    monkeypatch.setattr(settings, "CONVERSATION_CAPABILITY_LEVEL", "stub")
    monkeypatch.setattr(settings, "ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    main.app.dependency_overrides[verify_gateway_request] = lambda: True

    response = TestClient(main.app).get("/api/chat/messages")
    main.app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls == [("http://orchestrator-service:8006", "api/chat/messages")]
