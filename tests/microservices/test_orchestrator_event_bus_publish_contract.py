"""اختبارات تثبيت سلوك EventBus للنشر مع تمرير الأخطاء للأعلى."""

from __future__ import annotations

import json

import pytest

from microservices.orchestrator_service.src.core.event_bus import EventBus


class _FailingRedis:
    """عميل Redis وهمي يفشل عمدًا لاختبار مسار الخطأ."""

    async def publish(self, channel: str, message: str) -> None:
        _ = (channel, message)
        raise RuntimeError("redis down")


class _CapturingRedis:
    """عميل Redis وهمي يلتقط payload المرسلة للتحقق من قابلية التسلسل."""

    def __init__(self) -> None:
        self.published: list[tuple[str, str]] = []

    async def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))


@pytest.mark.asyncio
async def test_event_bus_publish_raises_on_redis_error() -> None:
    """يثبت أن فشل Redis لا يُبتلع حتى تتمكن طبقة outbox من تعليم الحالة failed."""

    bus = EventBus()
    bus.redis = _FailingRedis()  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="redis down"):
        await bus.publish("mission:1", {"event_type": "status_change"})


@pytest.mark.asyncio
async def test_event_bus_publish_serializes_dict_payload() -> None:
    """يثبت أن EventBus ينشر payload بصيغة JSON سليمة."""

    bus = EventBus()
    capturing = _CapturingRedis()
    bus.redis = capturing  # type: ignore[assignment]

    payload = {"event_type": "status_change", "payload_json": {"x": 1}}
    await bus.publish("mission:2", payload)

    assert capturing.published
    channel, raw = capturing.published[0]
    assert channel == "mission:2"
    assert json.loads(raw) == payload
