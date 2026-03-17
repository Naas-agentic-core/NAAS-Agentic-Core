"""حواجز معمارية لضمان منع عودة split-brain في مسار الدردشة."""

from __future__ import annotations

from pathlib import Path


def test_monolith_chat_routers_do_not_expose_websocket_endpoints() -> None:
    """يثبت إزالة مسارات WebSocket من المونوليث لضمان ملكية جلسة واحدة فقط."""

    admin_router = Path("app/api/routers/admin.py").read_text(encoding="utf-8")
    customer_router = Path("app/api/routers/customer_chat.py").read_text(encoding="utf-8")

    assert "@router.websocket(" not in admin_router
    assert "@router.websocket(" not in customer_router


def test_customer_chat_router_registered_without_ws_execution_path() -> None:
    """يثبت أن تسجيل راوتر العملاء مخصص لقراءة التاريخ دون WS محلي."""

    registry_module = Path("app/api/routers/registry.py").read_text(encoding="utf-8")
    customer_router = Path("app/api/routers/customer_chat.py").read_text(encoding="utf-8")

    assert "(customer_chat.router, \"\")" in registry_module
    assert "@router.websocket(" not in customer_router


def test_gateway_enforces_parity_cutover_true() -> None:
    """يفرض أن بوابة الواجهات لا تسمح بتراجع parity إلى false."""

    config_module = Path("microservices/api_gateway/config.py").read_text(encoding="utf-8")

    assert "CONVERSATION_PARITY_VERIFIED: bool = True" in config_module
    assert "self.CONVERSATION_PARITY_VERIFIED = True" in config_module
