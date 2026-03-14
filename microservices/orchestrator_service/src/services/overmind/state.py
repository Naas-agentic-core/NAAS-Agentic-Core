# app/services/overmind/state.py
# =================================================================================================
# OVERMIND STATE MANAGER – NEURAL MEMORY SUBSYSTEM
# Version: 11.2.0-pacelc-gapless
# =================================================================================================

import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from microservices.orchestrator_service.src.core.event_bus import get_event_bus
from microservices.orchestrator_service.src.core.protocols import EventBusProtocol
from microservices.orchestrator_service.src.models.mission import (
    Mission,
    MissionEvent,
    MissionEventType,
    MissionOutbox,
    MissionPlan,
    MissionStatus,
    PlanStatus,
    Task,
    TaskStatus,
)
from microservices.orchestrator_service.src.services.overmind.domain.types import (
    JsonValue,
    MissionContext,
)

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(UTC)


class MissionStateManager:
    """
    يدير الحالة الدائمة للمهام والخطط داخل نواة الواقع.

    يعتمد الإدخال/الإخراج غير المتزامن لتعظيم الأداء،
    ويستخدم ناقل الأحداث لتوفير استجابة منخفضة مع الحفاظ على الاتساق.
    """

    def __init__(self, session: AsyncSession, event_bus: EventBusProtocol | None = None) -> None:
        self.session = session
        self.event_bus = event_bus or get_event_bus()


    def _build_event_bus_message(
        self,
        *,
        mission_id: int,
        event_type: MissionEventType,
        payload: dict[str, JsonValue],
        created_at: datetime,
    ) -> dict[str, object]:
        """يبني رسالة حدث قابلة للتسلسل وتوافق عقود البث الحالية."""

        message: dict[str, object] = {
            "mission_id": mission_id,
            "event_type": str(event_type.value),
            "payload_json": payload,
            "created_at": created_at.isoformat(),
        }
        json.dumps(message)
        return message

    async def _load_relay_candidates(self, *, batch_size: int) -> list[MissionOutbox]:
        """يحمّل دفعة سجلات Outbox المرشحة لإعادة النشر."""

        stmt = (
            select(MissionOutbox)
            .where(MissionOutbox.status.in_(["pending", "failed", "processing"]))
            .order_by(MissionOutbox.id.asc())
            .limit(batch_size)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    def _relay_attempt(self, outbox: MissionOutbox) -> int:
        """يستخرج عداد محاولات relay من الحمولة الداخلية دون كسر البيانات الأصلية."""

        payload = outbox.payload_json
        if not isinstance(payload, dict):
            return 0
        relay_meta = payload.get("__relay")
        if not isinstance(relay_meta, dict):
            return 0
        attempt = relay_meta.get("attempt")
        if isinstance(attempt, int) and attempt >= 0:
            return attempt
        return 0

    def _business_payload(self, outbox: MissionOutbox) -> dict[str, JsonValue]:
        """يعيد حمولة الحدث الأصلية مع حذف مفاتيح relay الداخلية عند الحاجة."""

        payload = outbox.payload_json
        if not isinstance(payload, dict):
            return {}
        clean_payload = dict(payload)
        clean_payload.pop("__relay", None)
        return clean_payload

    def _processing_reference_time(self, outbox: MissionOutbox) -> datetime:
        """يستخرج مرجع الزمن لمعالجة processing مع تفضيل آخر محاولة relay."""

        payload = outbox.payload_json
        if isinstance(payload, dict):
            relay_meta = payload.get("__relay")
            if isinstance(relay_meta, dict):
                raw_last_attempt = relay_meta.get("last_attempt_at")
                if isinstance(raw_last_attempt, str) and raw_last_attempt.strip():
                    try:
                        parsed = datetime.fromisoformat(raw_last_attempt)
                        if parsed.tzinfo is None:
                            return parsed.replace(tzinfo=UTC)
                        return parsed
                    except ValueError:
                        pass

        created_at = outbox.created_at
        if created_at.tzinfo is None:
            return created_at.replace(tzinfo=UTC)
        return created_at

    def _is_processing_stale(
        self,
        outbox: MissionOutbox,
        *,
        processing_timeout_seconds: int,
        now: datetime,
    ) -> bool:
        """يحدد ما إذا كان سجل processing قديمًا بما يكفي لإعادة المعالجة بأمان."""

        if outbox.status != "processing":
            return True
        timeout = max(1, int(processing_timeout_seconds))
        reference_time = self._processing_reference_time(outbox)
        return reference_time <= (now - timedelta(seconds=timeout))

    async def relay_outbox_events(
        self,
        *,
        batch_size: int = 50,
        max_failed_attempts: int = 3,
        processing_timeout_seconds: int = 300,
    ) -> dict[str, int]:
        """يعيد نشر سجلات outbox المتعثرة/المعلقة مع حالات معالجة واضحة."""

        now = utc_now()
        candidates = await self._load_relay_candidates(batch_size=batch_size)
        processed = 0
        published = 0
        failed = 0
        skipped = 0

        for outbox in candidates:
            current_attempt = self._relay_attempt(outbox)
            if outbox.status == "failed" and current_attempt >= max_failed_attempts:
                skipped += 1
                logger.info(
                    "outbox_relay_skipped id=%s mission_id=%s attempt=%s reason=max_failed_attempts",
                    outbox.id,
                    outbox.mission_id,
                    current_attempt,
                )
                continue

            if not self._is_processing_stale(
                outbox,
                processing_timeout_seconds=processing_timeout_seconds,
                now=now,
            ):
                skipped += 1
                logger.info(
                    "outbox_relay_skipped id=%s mission_id=%s attempt=%s reason=processing_inflight",
                    outbox.id,
                    outbox.mission_id,
                    current_attempt,
                )
                continue

            outbox.status = "processing"
            await self.session.commit()

            next_attempt = current_attempt + 1
            payload = self._business_payload(outbox)
            message = {
                "mission_id": outbox.mission_id,
                "event_type": outbox.event_type,
                "payload_json": payload,
                "created_at": outbox.created_at.isoformat(),
            }

            error_kind = "publish_error"
            try:
                json.dumps(message)
            except TypeError as exc:
                error_kind = "serialization_error"
                payload_with_meta = dict(payload)
                payload_with_meta["__relay"] = {
                    "attempt": next_attempt,
                    "last_error": str(exc),
                    "last_error_kind": error_kind,
                    "last_attempt_at": utc_now().isoformat(),
                }
                outbox.payload_json = payload_with_meta
                await self._set_outbox_status(outbox, status="failed")
                failed += 1
                processed += 1
                logger.warning(
                    "outbox_relay_failed id=%s mission_id=%s reason=%s",
                    outbox.id,
                    outbox.mission_id,
                    error_kind,
                )
                continue

            try:
                await self.event_bus.publish(f"mission:{outbox.mission_id}", message)
                await self._set_outbox_status(outbox, status="published", published_at=utc_now())
                published += 1
                logger.info(
                    "outbox_relay_published id=%s mission_id=%s attempt=%s",
                    outbox.id,
                    outbox.mission_id,
                    next_attempt,
                )
            except Exception as exc:
                payload_with_meta = dict(payload)
                payload_with_meta["__relay"] = {
                    "attempt": next_attempt,
                    "last_error": str(exc),
                    "last_error_kind": error_kind,
                    "last_attempt_at": utc_now().isoformat(),
                }
                outbox.payload_json = payload_with_meta
                await self._set_outbox_status(outbox, status="failed")
                failed += 1
                logger.warning(
                    "outbox_relay_failed id=%s mission_id=%s reason=%s",
                    outbox.id,
                    outbox.mission_id,
                    error_kind,
                )

            processed += 1

        return {
            "processed": processed,
            "published": published,
            "failed": failed,
            "skipped": skipped,
        }


    async def get_outbox_operational_snapshot(self) -> dict[str, int | str | None]:
        """يعيد ملخصًا تشغيليًا لحالة outbox لدعم المراقبة واتخاذ القرار."""

        status_stmt = (
            select(MissionOutbox.status, func.count(MissionOutbox.id))
            .group_by(MissionOutbox.status)
        )
        status_result = await self.session.execute(status_stmt)
        rows = status_result.all()

        counts: dict[str, int] = {
            "pending": 0,
            "processing": 0,
            "failed": 0,
            "published": 0,
        }
        for status, total in rows:
            key = str(status)
            if key in counts:
                counts[key] = int(total)

        oldest_pending_stmt = select(func.min(MissionOutbox.created_at)).where(
            MissionOutbox.status == "pending"
        )
        oldest_pending_result = await self.session.execute(oldest_pending_stmt)
        oldest_pending = oldest_pending_result.scalar_one_or_none()

        oldest_pending_age_seconds: int | None = None
        if isinstance(oldest_pending, datetime):
            delta = utc_now() - oldest_pending
            oldest_pending_age_seconds = max(0, int(delta.total_seconds()))

        return {
            "pending": counts["pending"],
            "processing": counts["processing"],
            "failed": counts["failed"],
            "published": counts["published"],
            "oldest_pending_age_seconds": oldest_pending_age_seconds,
            "generated_at": utc_now().isoformat(),
        }

    async def create_mission(
        self,
        objective: str,
        initiator_id: int,
        context: MissionContext | None = None,
        idempotency_key: str | None = None,
    ) -> Mission:
        # Check for existing mission with idempotency_key
        if idempotency_key:
            stmt = select(Mission).where(Mission.idempotency_key == idempotency_key)
            result = await self.session.execute(stmt)
            existing = result.scalar_one_or_none()
            if existing:
                return existing

        mission = Mission(
            objective=objective,
            initiator_id=initiator_id,
            status=MissionStatus.PENDING,
            idempotency_key=idempotency_key,
            created_at=utc_now(),
            updated_at=utc_now(),
        )
        self.session.add(mission)
        await self.session.flush()
        await self.session.commit()
        return mission

    async def get_mission(self, mission_id: int) -> Mission | None:
        stmt = (
            select(Mission)
            .options(
                joinedload(Mission.mission_plans),
                joinedload(Mission.tasks),
            )
            .where(Mission.id == mission_id)
        )
        result = await self.session.execute(stmt)
        # Using unique() is essential when using joinedload with one-to-many relationships
        # to prevent duplicate Mission objects due to the Cartesian product.
        return result.unique().scalar_one_or_none()

    async def update_mission_status(
        self, mission_id: int, status: MissionStatus, note: str | None = None
    ) -> None:
        stmt = select(Mission).where(Mission.id == mission_id)
        result = await self.session.execute(stmt)
        mission = result.scalar_one_or_none()
        if mission:
            # Enforce Strict State Transitions
            if not self._is_valid_transition(mission.status, status):
                error_msg = f"Invalid Mission Transition: {mission.status} -> {status} for Mission {mission_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)

            old_status = str(mission.status)
            mission.status = status
            mission.updated_at = utc_now()

            # Log the status change event (which now commits)
            await self.log_event(
                mission_id,
                MissionEventType.STATUS_CHANGE,
                {"old_status": old_status, "new_status": str(status), "note": note},
            )
            # Explicit commit to ensure status update is visible
            await self.session.commit()

    def _is_valid_transition(self, current: MissionStatus, new_status: MissionStatus) -> bool:
        """
        Defines the legal state transitions for the Mission State Machine.
        """
        if current == new_status:
            return True

        # Define allowed transitions
        transitions = {
            MissionStatus.PENDING: {
                MissionStatus.RUNNING,
                MissionStatus.FAILED,
                MissionStatus.CANCELED,
            },
            MissionStatus.RUNNING: {
                MissionStatus.SUCCESS,
                MissionStatus.PARTIAL_SUCCESS,
                MissionStatus.FAILED,
                MissionStatus.CANCELED,
            },
            # Allow Retry from Terminal States
            MissionStatus.FAILED: {MissionStatus.PENDING, MissionStatus.RUNNING},
            MissionStatus.CANCELED: {MissionStatus.PENDING, MissionStatus.RUNNING},
            MissionStatus.SUCCESS: set(),  # Final state
            MissionStatus.PARTIAL_SUCCESS: set(),  # Final state
        }

        allowed = transitions.get(current, set())
        return new_status in allowed

    async def complete_mission(
        self,
        mission_id: int,
        result_summary: str | None = None,
        result_json: dict[str, JsonValue] | None = None,
        status: MissionStatus = MissionStatus.SUCCESS,
    ) -> None:
        """
        Completes the mission, updates the result summary, and logs the completion event.
        Fixes the visibility issue in Admin Dashboard.
        """
        stmt = select(Mission).where(Mission.id == mission_id)
        result = await self.session.execute(stmt)
        mission = result.scalar_one_or_none()
        if mission:
            mission.status = status
            mission.updated_at = utc_now()
            if result_summary:
                mission.result_summary = result_summary

            # Log completion event
            payload = {"result": result_json} if result_json else {}
            await self.log_event(
                mission_id,
                MissionEventType.MISSION_COMPLETED,
                payload,
            )
            # Explicit commit to ensure persistence
            await self.session.commit()

    async def log_event(
        self, mission_id: int, event_type: MissionEventType, payload: dict[str, JsonValue]
    ) -> None:
        # 1. Log Event (Source of Truth)
        event = MissionEvent(
            mission_id=mission_id,
            event_type=event_type,
            payload_json=payload,
            created_at=utc_now(),
        )
        self.session.add(event)

        # 2. Add to Outbox (Transactional Guarantee)
        # The prompt mandates Transactional Outbox to solve dual-write.
        # This ensures that even if Redis fails, the intention to publish is recorded.
        outbox = MissionOutbox(
            mission_id=mission_id,
            event_type=str(event_type.value),
            payload_json=payload,
            status="pending",
            created_at=utc_now(),
        )
        self.session.add(outbox)

        # 3. Commit Atomically
        await self.session.commit()

        # 4. Broadcast immediately (Best effort)
        # Ideally, a background worker polls 'mission_outbox' where status='pending'.
        # For simplicity and latency, we try direct publish.
        # If this fails, the 'monitor_mission_events' (catch-up) mechanism still works via DB polling.
        message = self._build_event_bus_message(
            mission_id=mission_id,
            event_type=event_type,
            payload=payload,
            created_at=event.created_at,
        )
        try:
            await self.event_bus.publish(f"mission:{mission_id}", message)
            await self._set_outbox_status(outbox, status="published", published_at=utc_now())
        except Exception as e:
            await self._set_outbox_status(outbox, status="failed")
            logger.warning(f"Failed to publish event to Redis: {e}. Outbox record ID: {outbox.id}")


    async def _set_outbox_status(
        self,
        outbox: MissionOutbox,
        *,
        status: str,
        published_at: datetime | None = None,
    ) -> None:
        """يحدّث حالة سجل الـ Outbox بشكل صريح لضمان تتبع موثوق للنشر."""

        outbox.status = status
        outbox.published_at = published_at
        await self.session.commit()

    async def get_mission_events(self, mission_id: int) -> list[MissionEvent]:
        """Fetch all historical events for a mission."""
        stmt = (
            select(MissionEvent)
            .where(MissionEvent.mission_id == mission_id)
            .order_by(MissionEvent.id.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def persist_plan(
        self,
        mission_id: int,
        planner_name: str,
        plan_schema: object,  # MissionPlanSchema - using object to avoid circular import if schema is elsewhere
        score: float,
        rationale: str,
    ) -> MissionPlan:
        # Determine version
        stmt = select(func.max(MissionPlan.version)).where(MissionPlan.mission_id == mission_id)
        result = await self.session.execute(stmt)
        current_max = result.scalar() or 0
        version = current_max + 1

        # Safe access to attributes using getattr
        objective = getattr(plan_schema, "objective", "")
        tasks = getattr(plan_schema, "tasks", [])

        raw_data = {
            "objective": str(objective),
            "tasks_count": len(list(tasks)),  # Ensure it's iterable
        }

        mp = MissionPlan(
            mission_id=mission_id,
            version=version,
            planner_name=planner_name,
            status=PlanStatus.VALID,
            score=score,
            rationale=rationale,
            raw_json=raw_data,
            stats_json={},
            warnings_json=[],
            created_at=utc_now(),
        )
        self.session.add(mp)
        await self.session.flush()

        # Update Mission active plan
        mission_stmt = select(Mission).where(Mission.id == mission_id)
        mission_res = await self.session.execute(mission_stmt)
        mission = mission_res.scalar_one()
        mission.active_plan_id = mp.id

        # Create Tasks
        for t in tasks:
            task_row = Task(
                mission_id=mission_id,
                plan_id=mp.id,
                task_key=getattr(t, "task_id", ""),
                description=getattr(t, "description", ""),
                tool_name=getattr(t, "tool_name", ""),
                tool_args_json=getattr(t, "tool_args", {}),
                status=TaskStatus.PENDING,
                attempt_count=0,
                max_attempts=3,  # Default
                priority=getattr(t, "priority", 0),
                depends_on_json=getattr(t, "dependencies", []),
                created_at=utc_now(),
                updated_at=utc_now(),
            )
            self.session.add(task_row)

        await self.session.commit()
        return mp

    async def get_tasks(self, mission_id: int) -> list[Task]:
        stmt = select(Task).where(Task.mission_id == mission_id).order_by(Task.id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def mark_task_running(self, task_id: int) -> None:
        stmt = select(Task).where(Task.id == task_id)
        result = await self.session.execute(stmt)
        task = result.scalar_one()
        task.status = TaskStatus.RUNNING
        task.started_at = utc_now()
        task.attempt_count += 1
        await self.session.flush()
        await self.session.commit()

    async def mark_task_complete(
        self, task_id: int, result_text: str, meta: dict[str, JsonValue] | None = None
    ) -> None:
        if meta is None:
            meta = {}
        stmt = select(Task).where(Task.id == task_id)
        result = await self.session.execute(stmt)
        task = result.scalar_one()
        task.status = TaskStatus.SUCCESS
        task.finished_at = utc_now()
        task.result_text = result_text
        task.result_meta_json = meta
        await self.session.flush()
        await self.session.commit()

    async def mark_task_failed(self, task_id: int, error_text: str) -> None:
        stmt = select(Task).where(Task.id == task_id)
        result = await self.session.execute(stmt)
        task = result.scalar_one()
        task.status = TaskStatus.FAILED
        task.finished_at = utc_now()
        task.error_text = error_text
        await self.session.flush()
        await self.session.commit()

    async def monitor_mission_events(
        self, mission_id: int, poll_interval: float = 1.0
    ) -> AsyncGenerator[MissionEvent, None]:
        """
        Monitors a mission for new events using PACELC Optimization.
        Prioritizes EventBus for Low Latency (L), falling back to DB Polling
        only for recovery/initial load (Consistency).

        Gap-Free Strategy:
        1. Subscribe to EventBus (buffer events).
        2. Query Database (get past events).
        3. Yield DB events.
        4. Yield Buffered events (deduplicate).
        5. Continue Streaming from Bus.

        Args:
            mission_id (int): ID of the mission to monitor.
            poll_interval (float): Unused in EventBus mode.

        Yields:
            MissionEvent: The next event in the stream.
        """
        last_event_id = 0
        channel = f"mission:{mission_id}"

        # 1. Subscribe FIRST to avoid Race Condition (Gap-Free)
        queue = self.event_bus.subscribe_queue(channel)

        try:
            # 2. Catch-up from Database (Consistency)
            stmt = (
                select(MissionEvent)
                .where(MissionEvent.mission_id == mission_id)
                .order_by(MissionEvent.id.asc())
            )
            result = await self.session.execute(stmt)
            db_events = result.scalars().all()

            # Yield DB events
            for event in db_events:
                yield event
                if event.id:
                    last_event_id = max(last_event_id, event.id)
                if self._is_terminal_event(event):
                    return

            # 3. Process Buffered Queue & Live Stream (Latency)
            while True:
                event = await queue.get()

                # Handle dict events from Redis Bridge (which lack .id attribute)
                if isinstance(event, dict):
                    try:
                        # Attempt to reconstruct MissionEvent from dict
                        # This ensures downstream consumers receive the expected type
                        evt_type = event.get("event_type")
                        payload = event.get("payload_json") or event.get("data") or {}

                        # Create transient MissionEvent (not attached to session)
                        event = MissionEvent(
                            mission_id=mission_id,
                            event_type=evt_type,
                            payload_json=payload,
                            created_at=utc_now(),
                        )
                    except Exception as e:
                        logger.warning(f"Failed to convert Redis event dict to MissionEvent: {e}")
                        # Fallback: skip this malformed event to avoid crashing the stream
                        continue

                # Deduplicate: Skip if we already saw this ID from DB
                # Safety check: ensure event has .id attribute
                event_id = getattr(event, "id", None)

                if event_id and event_id <= last_event_id:
                    continue

                yield event

                if event_id:
                    last_event_id = max(last_event_id, event_id)

                if self._is_terminal_event(event):
                    return

        finally:
            self.event_bus.unsubscribe_queue(channel, queue)

    def _is_terminal_event(self, event: MissionEvent) -> bool:
        """Helper to check if an event concludes the mission."""
        return event.event_type in [
            MissionEventType.MISSION_COMPLETED,
            MissionEventType.MISSION_FAILED,
        ]
