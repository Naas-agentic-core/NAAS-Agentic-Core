"""اختبارات حارس الأمان لتحويل conversation بعد فرض parity بشكل قاطع."""

from __future__ import annotations

import pytest

from microservices.api_gateway.config import Settings


def test_enforces_parity_verification_true_even_if_env_sets_false() -> None:
    """يتحقق من أن الإعداد النهائي يفرض parity=true حتى لو طُلب false."""

    settings = Settings(
        ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT=10,
        CONVERSATION_PARITY_VERIFIED=False,
        CONVERSATION_CAPABILITY_LEVEL="parity_ready",
    )

    assert settings.CONVERSATION_PARITY_VERIFIED is True


def test_allows_conversation_rollout_when_parity_verified() -> None:
    """يسمح بالـ rollout بعد إثبات capability المناسبة."""

    settings = Settings(
        ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT=10,
        CONVERSATION_PARITY_VERIFIED=True,
        CONVERSATION_CAPABILITY_LEVEL="parity_ready",
    )
    assert settings.ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT == 10
    assert settings.CONVERSATION_PARITY_VERIFIED is True


def test_rejects_rollout_when_capability_level_is_stub() -> None:
    """يرفض التفعيل عند بقاء capability في وضع stub."""

    with pytest.raises(ValueError, match="CONVERSATION_CAPABILITY_LEVEL"):
        Settings(
            ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT=20,
            CONVERSATION_PARITY_VERIFIED=True,
            CONVERSATION_CAPABILITY_LEVEL="stub",
        )
