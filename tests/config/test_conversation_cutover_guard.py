"""اختبارات حارس الأمان لمنع تحويل conversation قبل إثبات التوافق."""

from __future__ import annotations

import pytest

from microservices.api_gateway.config import Settings


def test_rejects_conversation_rollout_without_parity_verification() -> None:
    """يرفض الإعدادات عندما تكون نسبة rollout أكبر من الصفر دون توثيق parity."""
    with pytest.raises(ValueError, match="CONVERSATION_PARITY_VERIFIED"):
        Settings(
            ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT=10,
            CONVERSATION_PARITY_VERIFIED=False,
        )


def test_allows_conversation_rollout_when_parity_verified() -> None:
    """يسمح بالـ rollout بعد التصريح الصريح بأن parity موثقة."""
    settings = Settings(
        ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT=10,
        CONVERSATION_PARITY_VERIFIED=True,
        CONVERSATION_CAPABILITY_LEVEL="parity_ready",
    )
    assert settings.ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT == 10
    assert settings.CONVERSATION_PARITY_VERIFIED is True


def test_rejects_rollout_when_capability_level_is_stub() -> None:
    """يرفض التفعيل عند بقاء capability في وضع stub حتى مع parity flag."""
    with pytest.raises(ValueError, match="CONVERSATION_CAPABILITY_LEVEL"):
        Settings(
            ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT=20,
            CONVERSATION_PARITY_VERIFIED=True,
            CONVERSATION_CAPABILITY_LEVEL="stub",
        )
