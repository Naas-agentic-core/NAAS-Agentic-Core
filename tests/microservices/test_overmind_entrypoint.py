"""اختبارات سلوكية لمسار dispatch في entrypoint عند تعطل قفل Redis."""

from __future__ import annotations

import pytest

from microservices.orchestrator_service.src.models.mission import MissionStatus
from microservices.orchestrator_service.src.services.overmind import entrypoint


class _FakeMission:
    """يمثل مهمة مبسطة لاختبار منطق الإطلاق."""

    def __init__(self, mission_id: int, status: MissionStatus) -> None:
        self.id = mission_id
        self.status = status


class _FakeStateManager:
    """يدير حالة مزيفة مع تسجيل الاستدعاءات للتحقق من السلوك."""

    instances: list["_FakeStateManager"] = []

    def __init__(self, session: object) -> None:
        _ = session
        self.logged_events: list[dict[str, object]] = []
        self.status_updates: list[dict[str, object]] = []
        _FakeStateManager.instances.append(self)

    async def create_mission(
        self,
        objective: str,
        initiator_id: int,
        context: dict[str, object] | None,
        idempotency_key: str | None,
    ) -> _FakeMission:
        _ = (objective, initiator_id, context, idempotency_key)
        return _FakeMission(mission_id=99, status=MissionStatus.PENDING)

    async def log_event(self, mission_id: int, event_type: object, payload: dict[str, object]) -> None:
        _ = event_type
        self.logged_events.append({"mission_id": mission_id, "payload": payload})

    async def update_mission_status(
        self,
        mission_id: int,
        status: MissionStatus,
        note: str | None = None,
    ) -> None:
        self.status_updates.append({"mission_id": mission_id, "status": status, "note": note})


class _FakeRedisLock:
    """قفل Redis مزيف يُفشل الاكتساب لمحاكاة انقطاع Redis."""

    async def acquire(self, blocking: bool = False) -> bool:
        _ = blocking
        raise RuntimeError("redis unavailable")

    async def release(self) -> None:
        return None


class _FakeRedisClient:
    """عميل Redis مزيف يعيد القفل المزيف ويغلق بشكل طبيعي."""

    def lock(self, key: str, timeout: int) -> _FakeRedisLock:
        _ = (key, timeout)
        return _FakeRedisLock()

    async def close(self) -> None:
        return None


@pytest.mark.asyncio
async def test_start_mission_dispatches_in_degraded_mode_when_redis_lock_fails(monkeypatch) -> None:
    """يتأكد أن المهمة تُطلق فعليًا حتى عند فشل Redis lock مع وسم تشغيل متدهور."""

    created_tasks: list[object] = []
    _FakeStateManager.instances.clear()

    def fake_create_task(coro: object) -> object:
        created_tasks.append(coro)
        if hasattr(coro, "close"):
            coro.close()
        return object()

    monkeypatch.setattr(entrypoint, "MissionStateManager", _FakeStateManager)
    monkeypatch.setattr(entrypoint.redis, "from_url", lambda *args, **kwargs: _FakeRedisClient())
    monkeypatch.setattr(entrypoint.asyncio, "create_task", fake_create_task)

    mission = await entrypoint.start_mission(
        session=object(),
        objective="run mission",
        initiator_id=1,
        context={"conversation_id": 10},
    )

    assert mission.id == 99
    assert len(created_tasks) == 1
    manager = _FakeStateManager.instances[0]
    assert manager.status_updates == []
    assert manager.logged_events
    assert manager.logged_events[0]["payload"]["triggered_by"] == "entrypoint_degraded_no_lock"
