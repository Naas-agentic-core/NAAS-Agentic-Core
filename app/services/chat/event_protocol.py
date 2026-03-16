"""أدوات توحيد بروتوكول أحداث الدردشة مع دعم التوافق الخلفي عبر راية تشغيل."""

from __future__ import annotations

import os

from app.contracts.chat_events import ChatEventEnvelope, ChatEventPayload, ChatEventType


def is_unified_chat_event_protocol_enabled() -> bool:
    """يتحقق من تفعيل البروتوكول الموحّد للأحداث عبر متغير بيئة."""
    return os.getenv("CHAT_USE_UNIFIED_EVENT_ENVELOPE", "0") == "1"


def build_chat_event_envelope(
    *,
    event_type: ChatEventType,
    content: str | None = None,
    details: str | None = None,
    status_code: int | None = None,
) -> dict[str, object]:
    """ينشئ مغلف حدث موحّد ومتوافق مع العقد الرسمي دون حقول فارغة."""
    envelope = ChatEventEnvelope(
        type=event_type,
        payload=ChatEventPayload(
            content=content,
            details=details,
            status_code=status_code,
        ),
    )
    return envelope.model_dump(exclude_none=True)


def normalize_streaming_event(event: object) -> dict[str, object]:
    """يوحّد حدث البث إلى ChatEventEnvelope مع الإبقاء على السلوك التاريخي عند تعطيل الراية."""
    if not is_unified_chat_event_protocol_enabled():
        if isinstance(event, dict):
            return event
        return {"type": "delta", "payload": {"content": str(event)}}

    if not isinstance(event, dict):
        return build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_DELTA,
            content=str(event),
        )

    raw_type = str(event.get("type", "assistant_delta"))
    payload_value = event.get("payload")
    payload = payload_value if isinstance(payload_value, dict) else {}

    if raw_type in ("status", ChatEventType.STATUS.value):
        status_value = payload.get("status_code")
        status_code = status_value if isinstance(status_value, int) else None
        return build_chat_event_envelope(event_type=ChatEventType.STATUS, status_code=status_code)

    if raw_type in ("error", "assistant_error"):
        details = str(payload.get("details", "")) or str(payload.get("content", ""))
        status_value = payload.get("status_code")
        status_code = status_value if isinstance(status_value, int) else None
        return build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_ERROR,
            details=details,
            status_code=status_code,
        )

    if raw_type == ChatEventType.ASSISTANT_FINAL.value:
        return build_chat_event_envelope(
            event_type=ChatEventType.ASSISTANT_FINAL,
            content=str(payload.get("content", "")),
        )

    content = str(payload.get("content", "")) if payload else str(event)
    return build_chat_event_envelope(
        event_type=ChatEventType.ASSISTANT_DELTA,
        content=content,
    )
