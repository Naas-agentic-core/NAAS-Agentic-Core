"""اختبارات وحدة لضمان ربط معرفات السياق في أحداث بث الدردشة."""

from __future__ import annotations

from app.api.routers import admin, customer_chat


def test_customer_bind_stream_metadata_adds_conversation_and_request_ids() -> None:
    """يتحقق من إضافة conversation_id وrequest_id في قناة العملاء."""
    event: dict[str, object] = {"type": "delta", "payload": {"content": "chunk"}}

    bound = customer_chat._bind_stream_metadata(
        event=event,
        conversation_id=42,
        request_id="req-abc",
    )

    payload = bound.get("payload")
    assert isinstance(payload, dict)
    assert payload["conversation_id"] == 42
    assert payload["request_id"] == "req-abc"
    assert payload["content"] == "chunk"


def test_admin_bind_stream_metadata_adds_conversation_and_request_ids() -> None:
    """يتحقق من إضافة conversation_id وrequest_id في قناة المسؤول."""
    event: dict[str, object] = {"type": "assistant_final", "payload": {"content": "done"}}

    bound = admin._bind_stream_metadata(
        event=event,
        conversation_id=7,
        request_id="req-xyz",
    )

    payload = bound.get("payload")
    assert isinstance(payload, dict)
    assert payload["conversation_id"] == 7
    assert payload["request_id"] == "req-xyz"
    assert payload["content"] == "done"


def test_bind_stream_metadata_preserves_existing_payload_when_request_missing() -> None:
    """يتحقق من عدم حذف المحتوى عند غياب request_id."""
    event: dict[str, object] = {"type": "persisted", "payload": {"status": "ok"}}

    bound = customer_chat._bind_stream_metadata(
        event=event,
        conversation_id=101,
        request_id=None,
    )

    payload = bound.get("payload")
    assert isinstance(payload, dict)
    assert payload["conversation_id"] == 101
    assert "request_id" not in payload
    assert payload["status"] == "ok"
