"""حواجز سلوكية لعميل الدردشة الإداري في الواجهة التقليدية."""

from __future__ import annotations

from pathlib import Path


def test_admin_chat_js_targets_unified_gateway_websocket_path() -> None:
    """يتحقق من توجيه العميل إلى مسار WS الموحّد عبر البوابة."""

    script_content = Path("app/static/js/admin_chat.js").read_text(encoding="utf-8")

    assert "/admin/api/chat/ws" in script_content
    assert "Legacy admin_chat.js is disabled" not in script_content


def test_admin_chat_js_guards_missing_dom_elements() -> None:
    """يتحقق من وجود حارس مبكر يمنع أخطاء التشغيل عند غياب عناصر الصفحة."""

    script_content = Path("app/static/js/admin_chat.js").read_text(encoding="utf-8")

    assert "if (!chatBox || !chatInput || !sendBtn)" in script_content
