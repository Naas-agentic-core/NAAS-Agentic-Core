"""اختبارات تثبيت سلوك Conversation WS URL أثناء rollout التدريجي."""

from __future__ import annotations

from microservices.api_gateway import main
from microservices.api_gateway.config import settings


def test_resolve_chat_ws_target_uses_conversation_ws_url_when_conversation_selected(monkeypatch) -> None:
    """عند اختيار conversation فعليًا يجب احترام CONVERSATION_WS_URL حرفيًا."""

    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 100)
    monkeypatch.setattr(settings, "CONVERSATION_PARITY_VERIFIED", True)
    monkeypatch.setattr(settings, "CONVERSATION_CAPABILITY_LEVEL", "parity_ready")
    monkeypatch.setattr(settings, "CONVERSATION_SERVICE_URL", "http://conversation-service:8010")
    monkeypatch.setattr(settings, "CONVERSATION_WS_URL", "wss://chat-edge.example.com/socket")

    target = main._resolve_chat_ws_target("chat_ws_customer", "api/chat/ws")

    assert target == "wss://chat-edge.example.com/socket/api/chat/ws"


def test_resolve_chat_ws_target_falls_back_to_conversation_http_url_when_ws_url_empty(
    monkeypatch,
) -> None:
    """يحافظ على التوافق: إذا كان CONVERSATION_WS_URL فارغًا نستخدم تحويل HTTP→WS."""

    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 100)
    monkeypatch.setattr(settings, "CONVERSATION_PARITY_VERIFIED", True)
    monkeypatch.setattr(settings, "CONVERSATION_CAPABILITY_LEVEL", "parity_ready")
    monkeypatch.setattr(settings, "CONVERSATION_SERVICE_URL", "https://conversation-service:8010")
    monkeypatch.setattr(settings, "CONVERSATION_WS_URL", "")

    target = main._resolve_chat_ws_target("chat_ws_customer", "api/chat/ws")

    assert target == "wss://conversation-service:8010/api/chat/ws"


def test_resolve_chat_ws_target_keeps_orchestrator_when_conversation_not_selected(monkeypatch) -> None:
    """لا يغير السلوك الافتراضي: عند عدم اختيار conversation يبقى الهدف orchestrator."""

    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 0)
    monkeypatch.setattr(settings, "ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    monkeypatch.setattr(settings, "CONVERSATION_WS_URL", "wss://chat-edge.example.com/socket")

    target = main._resolve_chat_ws_target("chat_ws_customer", "api/chat/ws")

    assert target == "ws://orchestrator-service:8006/api/chat/ws"
