"""اختبارات بروتوكول تغليف أحداث دردشة الإدارة في Wave 1."""

from __future__ import annotations

import pytest

from app.services.chat import event_protocol


def test_admin_normalize_streaming_event_legacy_protocol_for_string(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يتحقق من بقاء السلوك التاريخي لمسار الإدارة عند تعطيل الراية."""
    monkeypatch.setenv("CHAT_USE_UNIFIED_EVENT_ENVELOPE", "0")

    event = event_protocol.normalize_streaming_event("hello")

    assert event == {"type": "delta", "payload": {"content": "hello"}}


def test_admin_normalize_streaming_event_unified_maps_legacy_delta(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يتحقق من تحويل delta إلى assistant_delta ضمن العقد الموحّد."""
    monkeypatch.setenv("CHAT_USE_UNIFIED_EVENT_ENVELOPE", "1")

    event = event_protocol.normalize_streaming_event(
        {"type": "delta", "payload": {"content": "chunk"}}
    )

    assert event["type"] == "assistant_delta"
    assert event["payload"]["content"] == "chunk"
    assert event["contract_version"] == "v1"


def test_admin_normalize_streaming_event_unified_maps_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يتحقق من تحويل error إلى assistant_error مع status_code."""
    monkeypatch.setenv("CHAT_USE_UNIFIED_EVENT_ENVELOPE", "1")

    event = event_protocol.normalize_streaming_event(
        {"type": "error", "payload": {"details": "boom", "status_code": 500}}
    )

    assert event["type"] == "assistant_error"
    assert event["payload"]["details"] == "boom"
    assert event["payload"]["status_code"] == 500
    assert event["contract_version"] == "v1"


def test_admin_normalize_streaming_event_unified_maps_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يتحقق من تحويل status مع الحفاظ على قيمة status_code."""
    monkeypatch.setenv("CHAT_USE_UNIFIED_EVENT_ENVELOPE", "1")

    event = event_protocol.normalize_streaming_event(
        {"type": "status", "payload": {"status_code": 202}}
    )

    assert event["type"] == "status"
    assert event["payload"]["status_code"] == 202
    assert event["contract_version"] == "v1"
