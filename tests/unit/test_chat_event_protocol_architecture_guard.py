"""حواجز معمارية لمنع انجراف تطبيع أحداث الدردشة بين الراوترات."""

from __future__ import annotations

from pathlib import Path


def test_chat_routers_do_not_expose_local_websocket_protocol_logic() -> None:
    """يتحقق من أن راوترات الدردشة لا تعيد إدخال منطق WS محلي بعد الإيقاف."""
    routers = (
        Path("app/api/routers/customer_chat.py"),
        Path("app/api/routers/admin.py"),
    )

    for router_file in routers:
        content = router_file.read_text(encoding="utf-8")
        assert "@router.websocket(" not in content


def test_chat_routers_do_not_redefine_event_protocol_helpers() -> None:
    """يتحقق من عدم عودة الدوال المكررة داخل الراوترات بعد التوحيد."""
    forbidden_helper_names = (
        "def _normalize_streaming_event",
        "def _build_chat_event_envelope",
        "def _is_unified_chat_event_protocol_enabled",
    )

    routers = (
        Path("app/api/routers/customer_chat.py"),
        Path("app/api/routers/admin.py"),
    )

    for router_file in routers:
        content = router_file.read_text(encoding="utf-8")
        for helper_name in forbidden_helper_names:
            assert helper_name not in content


def test_chat_routers_do_not_import_legacy_websocket_auth_or_token_decoders() -> None:
    """يتحقق من عدم عودة تبعيات المصادقة WS المحلية بعد توحيد الملكية."""

    forbidden_imports = (
        "from app.api.routers.ws_auth import extract_websocket_auth",
        "from app.services.auth.token_decoder import decode_user_id",
    )

    routers = (
        Path("app/api/routers/customer_chat.py"),
        Path("app/api/routers/admin.py"),
    )

    for router_file in routers:
        content = router_file.read_text(encoding="utf-8")
        for forbidden_import in forbidden_imports:
            assert forbidden_import not in content
