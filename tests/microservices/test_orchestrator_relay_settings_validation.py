"""اختبارات ضبط إعدادات relay لمنع misconfiguration التشغيلي."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from microservices.orchestrator_service.src.core.config import Settings


def _base_settings() -> dict[str, object]:
    return {
        "ENVIRONMENT": "development",
        "SECRET_KEY": "x" * 40,
    }


def test_relay_settings_reject_zero_interval() -> None:
    """يرفض إعداد interval أقل من 1 ثانية."""

    with pytest.raises(ValidationError):
        Settings(**_base_settings(), OUTBOX_RELAY_INTERVAL_SECONDS=0)


def test_relay_settings_reject_invalid_batch_size() -> None:
    """يرفض batch_size خارج المجال الآمن."""

    with pytest.raises(ValidationError):
        Settings(**_base_settings(), OUTBOX_RELAY_BATCH_SIZE=0)

    with pytest.raises(ValidationError):
        Settings(**_base_settings(), OUTBOX_RELAY_BATCH_SIZE=999)


def test_relay_settings_reject_invalid_retry_budget() -> None:
    """يرفض retry budget غير المنطقي."""

    with pytest.raises(ValidationError):
        Settings(**_base_settings(), OUTBOX_RELAY_MAX_FAILED_ATTEMPTS=0)

    with pytest.raises(ValidationError):
        Settings(**_base_settings(), OUTBOX_RELAY_MAX_FAILED_ATTEMPTS=99)


def test_relay_settings_reject_too_small_processing_timeout() -> None:
    """يرفض processing timeout الأصغر من الحد الأدنى."""

    with pytest.raises(ValidationError):
        Settings(**_base_settings(), OUTBOX_RELAY_PROCESSING_TIMEOUT_SECONDS=1)


def test_relay_settings_accept_valid_operational_window() -> None:
    """يقبل القيم التشغيلية الآمنة ضمن الحدود المعتمدة."""

    settings = Settings(
        **_base_settings(),
        OUTBOX_RELAY_INTERVAL_SECONDS=5,
        OUTBOX_RELAY_BATCH_SIZE=100,
        OUTBOX_RELAY_MAX_FAILED_ATTEMPTS=5,
        OUTBOX_RELAY_PROCESSING_TIMEOUT_SECONDS=300,
    )

    assert settings.OUTBOX_RELAY_INTERVAL_SECONDS == 5
    assert settings.OUTBOX_RELAY_BATCH_SIZE == 100
    assert settings.OUTBOX_RELAY_MAX_FAILED_ATTEMPTS == 5
    assert settings.OUTBOX_RELAY_PROCESSING_TIMEOUT_SECONDS == 300
