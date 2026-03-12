"""اختبارات إعدادات الأمان لخدمة orchestrator في production/staging."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from microservices.orchestrator_service.src.core.config import Settings


def test_orchestrator_requires_admin_tool_key_in_staging() -> None:
    """يفشل الإقلاع دون ADMIN_TOOL_API_KEY قوي في staging."""
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="x" * 40,
            BACKEND_CORS_ORIGINS=["https://app.example.com"],
            ADMIN_TOOL_API_KEY=None,
        )


def test_orchestrator_accepts_strong_admin_tool_key() -> None:
    """ينجح التهيئة عندما تتوفر مفاتيح أمان قوية في staging."""
    settings = Settings(
        ENVIRONMENT="staging",
        SECRET_KEY="x" * 40,
        BACKEND_CORS_ORIGINS=["https://app.example.com"],
        ADMIN_TOOL_API_KEY="internal-key-super-strong-123456",
    )
    assert settings.ADMIN_TOOL_API_KEY is not None
