"""اختبارات تثبت أن مسارات legacy تعمل كواجهات توافقية معلنة لا كسلطات مستقلة."""

from __future__ import annotations

from app.api.routers import admin, content, customer_chat


def test_legacy_routers_are_explicitly_marked_as_compatibility_facades() -> None:
    """يفرض وسمًا صريحًا يمنع إخفاء دين معماري غير محكوم."""
    assert admin.COMPATIBILITY_FACADE_MODE is True
    assert customer_chat.COMPATIBILITY_FACADE_MODE is True
    assert content.COMPATIBILITY_FACADE_MODE is True


def test_chat_facades_delegate_to_single_canonical_authority() -> None:
    """يثبت أن مسارات chat legacy تعلن نفس السلطة التنفيذية القانونية."""
    assert admin.CANONICAL_EXECUTION_AUTHORITY == customer_chat.CANONICAL_EXECUTION_AUTHORITY
    assert admin.CANONICAL_EXECUTION_AUTHORITY.endswith("ChatOrchestrator")
