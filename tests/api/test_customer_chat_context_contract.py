"""اختبارات عقد استمرارية السياق لمسار محادثة العميل."""

from app.api.routers.customer_chat import (
    _has_entity_anchor,
    _is_ambiguous_followup_question,
)


def test_ambiguous_followup_detection_for_arabic_reference_question() -> None:
    """يتحقق من اكتشاف الأسئلة الإحالية القصيرة (مثل: ما هي عاصمتها؟)."""
    assert _is_ambiguous_followup_question("ما هي عاصمتها؟") is True
    assert _is_ambiguous_followup_question("أين تقع النيجر؟") is False


def test_anchor_detection_uses_recent_user_messages() -> None:
    """يتحقق من قبول المتابعة الإحالية عند وجود مرساة كيان في رسائل المستخدم."""
    messages = [
        {"role": "user", "content": "أين تقع النيجر؟"},
        {"role": "assistant", "content": "تقع في غرب إفريقيا."},
    ]
    assert _has_entity_anchor(messages) is True


def test_anchor_detection_rejects_pronoun_only_context() -> None:
    """يتحقق من رفض السياق الضميري الخالص بدون مرساة كيان واضحة."""
    messages = [
        {"role": "user", "content": "ما هي عاصمتها؟"},
        {"role": "assistant", "content": "يرجى تحديد الدولة."},
    ]
    assert _has_entity_anchor(messages) is False
