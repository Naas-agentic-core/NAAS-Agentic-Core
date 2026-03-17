"""حواجز سلوكية لمنع كسر اتصال WS في بيئات HTTPS والتهيئات الداخلية."""

from __future__ import annotations

from pathlib import Path


def test_agent_socket_forces_wss_when_page_is_https() -> None:
    """يتحقق من فرض wss عند تحميل الواجهة عبر HTTPS لتجنب mixed-content offline."""

    source = Path("frontend/app/hooks/useAgentSocket.js").read_text(encoding="utf-8")

    assert "const forceSecure = window.location.protocol === 'https:';" in source
    assert "resolveWebSocketProtocol(parsed.protocol, forceSecure)" in source
    assert "if (forceSecure) return 'wss:';" in source


def test_agent_socket_falls_back_from_internal_service_hostname() -> None:
    """يتحقق من منع استخدام hostname داخلي (مثل api-gateway) داخل متصفح المستخدم."""

    source = Path("frontend/app/hooks/useAgentSocket.js").read_text(encoding="utf-8")

    assert "const isLikelyInternalHostname = (hostname) =>" in source
    assert "Configured WS/API host looks internal for browser runtime" in source
    assert "return `${wsProtocol}//${window.location.host}`;" in source
