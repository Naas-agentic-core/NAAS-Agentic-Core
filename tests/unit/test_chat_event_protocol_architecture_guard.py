"""حواجز معمارية لمنع انجراف تطبيع أحداث الدردشة بين الراوترات."""

from __future__ import annotations

from pathlib import Path


def test_chat_routers_use_shared_event_protocol_module() -> None:
    """يتحقق من اعتماد راوترات الدردشة على الوحدة المركزية للتطبيع."""
    routers = (
        Path("app/api/routers/customer_chat.py"),
        Path("app/api/routers/admin.py"),
    )

    for router_file in routers:
        content = router_file.read_text(encoding="utf-8")
        assert "from shared.chat_protocol.event_protocol import normalize_streaming_event" in content


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
