"""اختبارات تكامل قرار التوجيه الموحد بين HTTP وWS في Gateway."""

from __future__ import annotations

from microservices.api_gateway import main
from microservices.api_gateway.config import settings


def test_http_and_ws_share_same_orchestrator_decision(monkeypatch) -> None:
    """لنفس الهوية ومع rollout=0 يجب أن يتفق HTTP وWS على orchestrator."""
    monkeypatch.setattr(settings, "ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT", 0)
    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 0)
    monkeypatch.setattr(settings, "ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")

    http_target = main._resolve_chat_target_base("chat_http", "id-123", 0)
    ws_target = main._resolve_chat_ws_target("chat_ws_customer", "api/chat/ws")

    assert http_target == "http://orchestrator-service:8006"
    assert ws_target.startswith("ws://orchestrator-service:8006/")


def test_http_and_ws_share_same_conversation_decision(monkeypatch) -> None:
    """لنفس السياسة ومع rollout=100 يجب أن يتفق HTTP وWS على conversation service."""
    monkeypatch.setattr(settings, "ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT", 100)
    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 100)
    monkeypatch.setattr(settings, "CONVERSATION_SERVICE_URL", "http://conversation-service:8010")

    http_target = main._resolve_chat_target_base("chat_http", "id-123", 100)
    ws_target = main._resolve_chat_ws_target("chat_ws_customer", "api/chat/ws")

    assert http_target == "http://conversation-service:8010"
    assert ws_target.startswith("ws://conversation-service:8010/")
