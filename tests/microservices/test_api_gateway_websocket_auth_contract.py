"""اختبارات توافق عقد WS auth داخل API Gateway proxy."""

from __future__ import annotations

import pytest
from starlette.websockets import WebSocketState

from microservices.api_gateway import websockets as ws_proxy


class _FakeClientWebSocket:
    """يمثل عميل WebSocket مبسطًا لتثبيت سلوك التفاوض على subprotocol."""

    def __init__(self, protocol_header: str) -> None:
        self.headers = {"sec-websocket-protocol": protocol_header}
        self.client_state = WebSocketState.CONNECTING
        self.accepted_subprotocol: str | None = None
        self.closed: list[tuple[int, str]] = []
        self.url = "ws://gateway/api/chat/ws"

    async def accept(self, subprotocol: str | None = None) -> None:
        self.accepted_subprotocol = subprotocol
        self.client_state = WebSocketState.CONNECTED

    async def close(self, code: int, reason: str = "") -> None:
        self.closed.append((code, reason))
        self.client_state = WebSocketState.DISCONNECTED


@pytest.mark.asyncio
async def test_gateway_ws_proxy_selects_jwt_subprotocol_even_if_not_first(monkeypatch) -> None:
    """يثبت أن البوابة تختار jwt حتى إن جاء الترويس بترتيب [token, jwt]."""

    captured: dict[str, object] = {}

    def fake_connect(target_url: str, **kwargs):
        captured["target_url"] = target_url
        captured["kwargs"] = kwargs
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(ws_proxy.websockets, "connect", fake_connect)

    client_ws = _FakeClientWebSocket("my_token, jwt")
    await ws_proxy.websocket_proxy(client_ws, "ws://orchestrator-service:8006/api/chat/ws")

    assert client_ws.accepted_subprotocol == "jwt"
    assert captured["kwargs"]["subprotocols"] == ["my_token", "jwt"]
    assert client_ws.closed
    assert client_ws.closed[0][0] == 1011


@pytest.mark.asyncio
async def test_gateway_ws_proxy_keeps_first_protocol_when_jwt_absent(monkeypatch) -> None:
    """يثبت التوافق العكسي: عند غياب jwt يبقى أول بروتوكول كما هو."""

    captured: dict[str, object] = {}

    def fake_connect(target_url: str, **kwargs):
        captured["target_url"] = target_url
        captured["kwargs"] = kwargs
        raise RuntimeError("upstream unavailable")

    monkeypatch.setattr(ws_proxy.websockets, "connect", fake_connect)

    client_ws = _FakeClientWebSocket("custom-proto")
    await ws_proxy.websocket_proxy(client_ws, "ws://orchestrator-service:8006/api/chat/ws")

    assert client_ws.accepted_subprotocol == "custom-proto"
    assert captured["kwargs"]["subprotocols"] == ["custom-proto"]
    assert client_ws.closed
    assert client_ws.closed[0][0] == 1011
