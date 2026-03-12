"""اختبارات أمان إعدادات Gateway في production/staging."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from microservices.api_gateway.config import Settings


def test_gateway_rejects_weak_secret_in_production() -> None:
    """يفشل الإقلاع إذا كان SECRET_KEY افتراضياً في الإنتاج."""
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="production",
            SECRET_KEY="super_secret_key_change_in_production",
            ALLOWED_HOSTS=["api.example.com"],
            BACKEND_CORS_ORIGINS=["https://app.example.com"],
        )


def test_gateway_rejects_wildcard_hosts_in_staging() -> None:
    """يفشل الإقلاع عند ALLOWED_HOSTS wildcard في staging."""
    with pytest.raises(ValidationError):
        Settings(
            ENVIRONMENT="staging",
            SECRET_KEY="x" * 40,
            ALLOWED_HOSTS=["*"],
            BACKEND_CORS_ORIGINS=["https://app.example.com"],
        )
