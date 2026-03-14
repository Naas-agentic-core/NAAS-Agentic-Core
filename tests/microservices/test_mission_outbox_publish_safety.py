"""اختبارات Characterization لضمان سلامة تحديث حالة Outbox عند نشر الأحداث."""

from __future__ import annotations

from dataclasses import dataclass
import json

import pytest

from microservices.orchestrator_service.src.models.mission import MissionEventType, MissionOutbox
from microservices.orchestrator_service.src.services.overmind.state import MissionStateManager


@dataclass
class _FakeEventBus:
    """ناقل أحداث وهمي يسمح بمحاكاة النجاح/الفشل بدقة."""

    should_fail: bool = False
    published_messages: list[tuple[str, object]] | None = None

    def __post_init__(self) -> None:
        if self.published_messages is None:
            self.published_messages = []

    async def publish(self, channel: str, event: object) -> None:
        self.published_messages.append((channel, event))
        if self.should_fail:
            raise RuntimeError("bus unavailable")


class _FakeSession:
    """جلسة مبسطة لتتبع عمليات add/commit دون قاعدة بيانات فعلية."""

    def __init__(self) -> None:
        self.added: list[object] = []
        self.commit_count = 0

    def add(self, obj: object) -> None:
        if isinstance(obj, MissionOutbox) and obj.id is None:
            obj.id = 1
        self.added.append(obj)

    async def commit(self) -> None:
        self.commit_count += 1


@pytest.mark.asyncio
async def test_log_event_marks_outbox_published_on_success() -> None:
    """يثبت أن outbox ينتقل إلى published عند نجاح النشر الفوري."""

    session = _FakeSession()
    manager = MissionStateManager(session=session, event_bus=_FakeEventBus(should_fail=False))

    await manager.log_event(
        mission_id=42,
        event_type=MissionEventType.STATUS_CHANGE,
        payload={"k": "v"},
    )

    assert manager.event_bus.published_messages
    channel, message = manager.event_bus.published_messages[0]
    assert channel == "mission:42"
    assert isinstance(message, dict)
    json.dumps(message)
    assert message["event_type"] == "status_change"

    outboxes = [obj for obj in session.added if isinstance(obj, MissionOutbox)]
    assert len(outboxes) == 1
    outbox = outboxes[0]
    assert outbox.status == "published"
    assert outbox.published_at is not None
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_log_event_marks_outbox_failed_on_publish_error() -> None:
    """يثبت أن outbox ينتقل إلى failed عند تعذر النشر دون فقدان السجل."""

    session = _FakeSession()
    manager = MissionStateManager(session=session, event_bus=_FakeEventBus(should_fail=True))

    await manager.log_event(
        mission_id=99,
        event_type=MissionEventType.STATUS_CHANGE,
        payload={"k": "v"},
    )

    outboxes = [obj for obj in session.added if isinstance(obj, MissionOutbox)]
    assert len(outboxes) == 1
    outbox = outboxes[0]
    assert outbox.status == "failed"
    assert outbox.published_at is None
    assert session.commit_count == 2


@pytest.mark.asyncio
async def test_relay_outbox_events_publishes_pending_records() -> None:
    """يثبت أن relay يعالج pending وينقلها إلى published برسالة قابلة للتسلسل."""

    pending = MissionOutbox(
        id=7,
        mission_id=77,
        event_type="status_change",
        payload_json={"x": 1},
        status="pending",
    )
    session = _FakeSession()
    bus = _FakeEventBus(should_fail=False)
    manager = MissionStateManager(session=session, event_bus=bus)

    async def _fake_candidates(*, batch_size: int):
        _ = batch_size
        return [pending]

    manager._load_relay_candidates = _fake_candidates  # type: ignore[method-assign]

    result = await manager.relay_outbox_events(batch_size=10, max_failed_attempts=3)

    assert result == {"processed": 1, "published": 1, "failed": 0, "skipped": 0}
    assert pending.status == "published"
    assert pending.published_at is not None
    assert bus.published_messages
    _, message = bus.published_messages[0]
    json.dumps(message)


@pytest.mark.asyncio
async def test_relay_outbox_events_skips_failed_after_retry_budget() -> None:
    """يثبت أن relay لا يعيد المحاولة بعد استهلاك ميزانية retry المحددة."""

    failed = MissionOutbox(
        id=9,
        mission_id=88,
        event_type="status_change",
        payload_json={"__relay": {"attempt": 3}},
        status="failed",
    )
    session = _FakeSession()
    bus = _FakeEventBus(should_fail=False)
    manager = MissionStateManager(session=session, event_bus=bus)

    async def _fake_candidates(*, batch_size: int):
        _ = batch_size
        return [failed]

    manager._load_relay_candidates = _fake_candidates  # type: ignore[method-assign]

    result = await manager.relay_outbox_events(batch_size=10, max_failed_attempts=3)

    assert result == {"processed": 0, "published": 0, "failed": 0, "skipped": 1}
    assert failed.status == "failed"
    assert bus.published_messages == []


@pytest.mark.asyncio
async def test_relay_outbox_events_marks_serialization_error_without_publish_call() -> None:
    """يثبت تصنيف serialization_error عندما تكون الحمولة غير قابلة للتسلسل."""

    class _NotSerializable:
        pass

    broken = MissionOutbox(
        id=11,
        mission_id=101,
        event_type="status_change",
        payload_json={"x": _NotSerializable()},
        status="pending",
    )
    session = _FakeSession()
    bus = _FakeEventBus(should_fail=False)
    manager = MissionStateManager(session=session, event_bus=bus)

    async def _fake_candidates(*, batch_size: int):
        _ = batch_size
        return [broken]

    manager._load_relay_candidates = _fake_candidates  # type: ignore[method-assign]

    result = await manager.relay_outbox_events(batch_size=10, max_failed_attempts=3)

    assert result == {"processed": 1, "published": 0, "failed": 1, "skipped": 0}
    assert broken.status == "failed"
    assert bus.published_messages == []
    relay_meta = broken.payload_json.get("__relay") if isinstance(broken.payload_json, dict) else None
    assert isinstance(relay_meta, dict)
    assert relay_meta.get("last_error_kind") == "serialization_error"


@pytest.mark.asyncio
async def test_relay_outbox_events_skips_fresh_processing_records() -> None:
    """يتجاوز سجلات processing الحديثة لتجنب التنافس مع معالجة جارية."""

    fresh_processing = MissionOutbox(
        id=12,
        mission_id=202,
        event_type="status_change",
        payload_json={"x": 1},
        status="processing",
    )
    session = _FakeSession()
    bus = _FakeEventBus(should_fail=False)
    manager = MissionStateManager(session=session, event_bus=bus)

    async def _fake_candidates(*, batch_size: int):
        _ = batch_size
        return [fresh_processing]

    manager._load_relay_candidates = _fake_candidates  # type: ignore[method-assign]

    result = await manager.relay_outbox_events(
        batch_size=10,
        max_failed_attempts=3,
        processing_timeout_seconds=3600,
    )

    assert result == {"processed": 0, "published": 0, "failed": 0, "skipped": 1}
    assert fresh_processing.status == "processing"
    assert bus.published_messages == []


@pytest.mark.asyncio
async def test_relay_processing_staleness_uses_last_attempt_timestamp_when_available() -> None:
    """يعتمد relay على __relay.last_attempt_at بدل created_at عند توفره."""

    old_created_recent_attempt = MissionOutbox(
        id=13,
        mission_id=303,
        event_type="status_change",
        payload_json={"__relay": {"last_attempt_at": "2999-01-01T00:00:00+00:00"}},
        status="processing",
    )
    session = _FakeSession()
    bus = _FakeEventBus(should_fail=False)
    manager = MissionStateManager(session=session, event_bus=bus)

    async def _fake_candidates(*, batch_size: int):
        _ = batch_size
        return [old_created_recent_attempt]

    manager._load_relay_candidates = _fake_candidates  # type: ignore[method-assign]

    result = await manager.relay_outbox_events(
        batch_size=10,
        max_failed_attempts=3,
        processing_timeout_seconds=30,
    )

    assert result == {"processed": 0, "published": 0, "failed": 0, "skipped": 1}
    assert bus.published_messages == []
