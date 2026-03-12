"""اختبارات تكامل لتوجيه WebSocket في API Gateway بعد إغلاق legacy."""

from __future__ import annotations

from fastapi.testclient import TestClient

from microservices.api_gateway import main
from microservices.api_gateway.config import settings


def test_chat_ws_routes_to_conversation_when_rollout_full(monkeypatch) -> None:
    """يتأكد أن WS chat يوجّه إلى Conversation عند rollout=100."""
    routed_targets: list[str] = []

    async def fake_ws_proxy(websocket, target_url: str) -> None:
        await websocket.accept()
        routed_targets.append(target_url)
        await websocket.send_text("ok")
        await websocket.close()

    monkeypatch.setattr(main, "websocket_proxy", fake_ws_proxy)
    monkeypatch.setattr(settings, "CONVERSATION_WS_URL", "ws://conversation-service:8010")
    monkeypatch.setattr(settings, "CONVERSATION_PARITY_VERIFIED", True)
    monkeypatch.setattr(settings, "CONVERSATION_CAPABILITY_LEVEL", "parity_ready")
    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 100)

    with TestClient(main.app).websocket_connect("/api/chat/ws") as ws:
        assert ws.receive_text() == "ok"

    assert routed_targets == ["ws://conversation-service:8010/api/chat/ws"]


def test_chat_ws_routes_to_orchestrator_when_rollout_zero(monkeypatch) -> None:
    """يتأكد أن canary بنسبة 0% يوجّه إلى orchestrator."""
    routed_targets: list[str] = []

    async def fake_ws_proxy(websocket, target_url: str) -> None:
        await websocket.accept()
        routed_targets.append(target_url)
        await websocket.send_text("ok")
        await websocket.close()

    monkeypatch.setattr(main, "websocket_proxy", fake_ws_proxy)
    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 0)
    monkeypatch.setattr(settings, "ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")

    with TestClient(main.app).websocket_connect("/api/chat/ws") as ws:
        assert ws.receive_text() == "ok"

    assert routed_targets == ["ws://orchestrator-service:8006/api/chat/ws"]


def test_chat_ws_cutover_blocked_when_parity_not_verified(monkeypatch) -> None:
    """يتأكد أن WS يبقى على orchestrator عندما parity غير مثبتة حتى مع rollout=100."""
    routed_targets: list[str] = []

    async def fake_ws_proxy(websocket, target_url: str) -> None:
        await websocket.accept()
        routed_targets.append(target_url)
        await websocket.send_text("ok")
        await websocket.close()

    monkeypatch.setattr(main, "websocket_proxy", fake_ws_proxy)
    monkeypatch.setattr(settings, "CONVERSATION_PARITY_VERIFIED", False)
    monkeypatch.setattr(settings, "CONVERSATION_CAPABILITY_LEVEL", "stub")
    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 100)
    monkeypatch.setattr(settings, "ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")

    with TestClient(main.app).websocket_connect("/api/chat/ws") as ws:
        assert ws.receive_text() == "ok"

    assert routed_targets == ["ws://orchestrator-service:8006/api/chat/ws"]


def test_chat_ws_cutover_blocked_when_capability_not_ready(monkeypatch) -> None:
    """يبقي WS على orchestrator إذا كانت capability=stub حتى مع parity=true."""
    routed_targets: list[str] = []

    async def fake_ws_proxy(websocket, target_url: str) -> None:
        await websocket.accept()
        routed_targets.append(target_url)
        await websocket.send_text("ok")
        await websocket.close()

    monkeypatch.setattr(main, "websocket_proxy", fake_ws_proxy)
    monkeypatch.setattr(settings, "CONVERSATION_PARITY_VERIFIED", True)
    monkeypatch.setattr(settings, "CONVERSATION_CAPABILITY_LEVEL", "stub")
    monkeypatch.setattr(settings, "ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT", 100)
    monkeypatch.setattr(settings, "ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")

    with TestClient(main.app).websocket_connect("/api/chat/ws") as ws:
        assert ws.receive_text() == "ok"

    assert routed_targets == ["ws://orchestrator-service:8006/api/chat/ws"]
