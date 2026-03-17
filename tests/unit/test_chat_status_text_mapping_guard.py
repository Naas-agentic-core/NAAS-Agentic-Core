"""حارس يضمن ترجمة حالات اتصال WS الحديثة في الواجهة."""

from __future__ import annotations

from pathlib import Path


def test_cogniforge_status_text_covers_realtime_states() -> None:
    """يتحقق من دعم الحالات offline/degraded/auth_error بنصوص مفهومة."""

    source = Path("frontend/app/components/CogniForgeApp.jsx").read_text(encoding="utf-8")

    assert "case 'offline':" in source
    assert "case 'degraded': return 'اتصال غير مستقر';" in source
    assert "case 'auth_error': return 'انتهت الجلسة';" in source
