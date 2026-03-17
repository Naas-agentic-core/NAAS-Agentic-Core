"""حواجز سلوكية لمنع كسر اتصال WS في بيئات HTTPS."""

from __future__ import annotations

from pathlib import Path


def test_agent_socket_forces_wss_when_page_is_https() -> None:
    """يتحقق من فرض wss عند تحميل الواجهة عبر HTTPS لتجنب mixed-content offline."""

    source = Path("frontend/app/hooks/useAgentSocket.js").read_text(encoding="utf-8")

    assert "const forceSecure = window.location.protocol === 'https:';" in source
    assert "resolveWebSocketProtocol(parsed.protocol, forceSecure)" in source
    assert "if (forceSecure) return 'wss:';" in source
