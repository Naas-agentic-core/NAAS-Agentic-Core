"""اختبارات سلوكية لتدفق mission_complex عند تعطل/تأخر ناقل الأحداث."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import asyncio

import pytest

from microservices.orchestrator_service.src.services.overmind.utils import mission_complex


class _FakeMission:
    """يمثل مهمة مبسطة مع معرف ثابت للاختبارات."""

    def __init__(self, mission_id: int) -> None:
        self.id = mission_id


async def _never_yield_subscription() -> AsyncGenerator[dict[str, object], None]:
    while True:
        await asyncio.sleep(3600)
        if False:
            yield {}


class _FakeEventBus:
    """ناقل أحداث مزيف يعيد اشتراكًا لا ينتج أحداثًا."""

    def subscribe(self, channel: str) -> AsyncGenerator[dict[str, object], None]:
        _ = channel
        return _never_yield_subscription()


class _FakeEventBusIdleOnce:
    """ناقل أحداث يظل خاملًا للتأكد من تفعيل الاسترجاع من قاعدة البيانات."""

    def subscribe(self, channel: str) -> AsyncGenerator[dict[str, object], None]:
        _ = channel
        return _never_yield_subscription()


@pytest.mark.asyncio
async def test_mission_complex_emits_timeout_error_when_event_bus_is_idle(monkeypatch) -> None:
    """يتأكد أن التدفق يعيد assistant_error واضحًا عند انقطاع أحداث التنفيذ."""

    async def fake_start_mission(**kwargs: object) -> _FakeMission:
        _ = kwargs
        return _FakeMission(321)

    async def fake_no_terminal_event(mission_id: int) -> dict[str, object] | None:
        _ = mission_id
        return None

    monkeypatch.setattr(mission_complex, "start_mission", fake_start_mission)
    monkeypatch.setattr(mission_complex, "get_event_bus", lambda: _FakeEventBus())
    monkeypatch.setattr(mission_complex, "_get_terminal_event_from_persistence", fake_no_terminal_event)
    monkeypatch.setattr(mission_complex, "MISSION_EVENT_WAIT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(mission_complex, "MISSION_EVENT_MAX_IDLE_CYCLES", 1)

    events: list[dict[str, object]] = []
    async for event in mission_complex.handle_mission_complex_stream(
        question="run",
        context={"conversation_id": 1},
        user_id=10,
    ):
        events.append(event)
        if event.get("type") == "assistant_error":
            break

    assert any(event.get("type") == "mission_created" for event in events)
    timeout_events = [event for event in events if event.get("type") == "assistant_error"]
    assert timeout_events
    payload = timeout_events[-1].get("payload")
    assert isinstance(payload, dict)
    assert "انتهت مهلة انتظار أحداث التنفيذ" in str(payload.get("content", ""))


@pytest.mark.asyncio
async def test_mission_complex_reads_terminal_result_from_persistence_on_idle(monkeypatch) -> None:
    """يتأكد أن التدفق يعيد assistant_final من قاعدة البيانات عند ضياع أحداث Redis."""

    async def fake_start_mission(**kwargs: object) -> _FakeMission:
        _ = kwargs
        return _FakeMission(999)

    async def fake_terminal_event(mission_id: int) -> dict[str, object] | None:
        _ = mission_id
        return {"type": "assistant_final", "payload": {"content": "result from db"}}

    monkeypatch.setattr(mission_complex, "start_mission", fake_start_mission)
    monkeypatch.setattr(mission_complex, "get_event_bus", lambda: _FakeEventBusIdleOnce())
    monkeypatch.setattr(mission_complex, "_get_terminal_event_from_persistence", fake_terminal_event)
    monkeypatch.setattr(mission_complex, "MISSION_EVENT_WAIT_TIMEOUT_SECONDS", 0.01)
    monkeypatch.setattr(mission_complex, "MISSION_EVENT_MAX_IDLE_CYCLES", 1)

    events: list[dict[str, object]] = []
    async for event in mission_complex.handle_mission_complex_stream(
        question="run",
        context={"conversation_id": 1},
        user_id=10,
    ):
        events.append(event)
        if event.get("type") in {"assistant_final", "assistant_error"}:
            break

    terminal_event = events[-1]
    assert terminal_event["type"] == "assistant_final"
    payload = terminal_event.get("payload")
    assert isinstance(payload, dict)
    assert payload.get("content") == "result from db"
