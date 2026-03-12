"""اختبارات عقود أحداث chat لضمان عدم انجراف schema بين الطبقات."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.contracts.chat_events import ChatEventEnvelope, ChatEventType


def test_chat_event_envelope_accepts_assistant_delta() -> None:
    """يتأكد أن مغلف assistant_delta صالح ومتوافق مع العقد."""
    envelope = ChatEventEnvelope(
        type=ChatEventType.ASSISTANT_DELTA,
        payload={"content": "مرحبا"},
    )
    assert envelope.contract_version == "v1"
    assert envelope.payload.content == "مرحبا"


def test_chat_event_envelope_accepts_assistant_error_with_request_id() -> None:
    """يتأكد أن assistant_error يحافظ على حقول التشخيص الآمنة المتوقعة من الواجهة."""
    envelope = ChatEventEnvelope(
        type=ChatEventType.ASSISTANT_ERROR,
        payload={"content": "تعذر الطلب", "request_id": "req-1", "retry_hint": "retry"},
    )
    assert envelope.payload.request_id == "req-1"


def test_chat_event_envelope_rejects_unknown_type() -> None:
    """يرفض أي نوع حدث غير معرّف لمنع silent schema drift."""
    with pytest.raises(ValidationError):
        ChatEventEnvelope(type="unknown_event", payload={"content": "x"})
