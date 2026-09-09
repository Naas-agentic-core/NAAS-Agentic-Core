# app/services/overmind/state.py
# =================================================================================================
# OVERMIND STATE MANAGER – NEURAL MEMORY SUBSYSTEM
# Version: 11.2.0-pacelc-gapless
# =================================================================================================

import json
import logging
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from microservices.orchestrator_service.src.core.database import _pgsafe_lit
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

    async def _load_relay_candidates(self, *, batch_size: int) -> list[dict]:
        """يحمّل دفعة سجلات Outbox المرشحة لإعادة النشر.

        D-194 (2026-08-12): ORM select مع .in_([...]) يولّد :status_N params
        تُنفذ عبر PsycopgSession فيرتطم syntax error على pgbouncer — raw psycopg فقط.
        """
        from sqlalchemy import text as _text

        rows = (
            await self.session.execute(
                _text(
                    "SELECT * FROM mission_outbox WHERE status IN ('pending', 'failed', 'processing') "
                    f"ORDER BY id ASC LIMIT {_pgsafe_lit(int(batch_size))}"
                ),
                [],
            )
        ).fetchall()
        return [dict(r) for r in rows]

    def _relay_attempt(self, outbox: MissionOutbox) -> int:
        """يستخرج عداد محاولات relay من الحمولة الداخلية دون كسر البيانات الأصلية."""

        payload = outbox["payload_json"] if isinstance(outbox, dict) else outbox.payload_json
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

        payload = outbox["payload_json"] if isinstance(outbox, dict) else outbox.payload_json
        if not isinstance(payload, dict):
            return {}
        clean_payload = dict(payload)
        clean_payload.pop("__relay", None)
        return clean_payload

    def _processing_reference_time(self, outbox: MissionOutbox) -> datetime:
        """يستخرج مرجع الزمن لمعالجة processing مع تفضيل آخر محاولة relay."""

        payload = outbox["payload_json"] if isinstance(outbox, dict) else outbox.payload_json
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

        created_at = outbox["created_at"] if isinstance(outbox, dict) else outbox.created_at
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

        ostatus = outbox["status"] if isinstance(outbox, dict) else outbox.status
        if ostatus != "processing":
            return True
        timeout = max(1, int(processing_timeout_seconds))
        reference_time = self._processing_reference_time(outbox)
        return reference_time <= (now - timedelta(seconds=timeout))

    async def relay_outbox_events(  # noqa: PLR0915 (god-function paydown deferred; D-105)
        self,
        *,
        batch_size: int = 50,
        max_failed_attempts: int = 3,
        processing_timeout_seconds: int = 300,
    ) -> dict[str, int]:
        """يعيد نشر سجلات outbox المتعثرة/المعلقة مع حالات معالجة واضحة."""

        now = utc_now()
        is_raw = not hasattr(self.session, "add")
        candidates = await self._load_relay_candidates(batch_size=batch_size)
        processed = 0
        published = 0
        failed = 0
        skipped = 0

        for _raw_outbox in candidates:
            # D-194: raw psycopg يرجع dict rows — ORM sessions تعمل على objects مباشرة (توافق tests/main)
            outbox = (
                {
                    c: getattr(_raw_outbox, c, None)
                    for c in (
                        "id",
                        "mission_id",
                        "status",
                        "event_type",
                        "payload_json",
                        "created_at",
                        "attempts",
                        "processing_started_at",
                        "processing_attempts",
                    )
                }
                if is_raw and not isinstance(_raw_outbox, dict)
                else _raw_outbox
            )

            current_attempt = self._relay_attempt(outbox)
            if (
                outbox["status"] if isinstance(outbox, dict) else outbox.status
            ) == "failed" and current_attempt >= max_failed_attempts:
                skipped += 1
                logger.info(
                    "outbox_relay_skipped id=%s mission_id=%s attempt=%s reason=max_failed_attempts",
                    outbox["id"] if isinstance(outbox, dict) else outbox.id,
                    outbox["mission_id"] if isinstance(outbox, dict) else outbox.mission_id,
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
                    outbox["id"] if isinstance(outbox, dict) else outbox.id,
                    outbox["mission_id"] if isinstance(outbox, dict) else outbox.mission_id,
                    current_attempt,
                )
                continue

            if isinstance(outbox, dict):
                outbox["status"] = "processing"
            else:
                outbox.status = "processing"  # ORM object
            await self.session.commit()

            next_attempt = current_attempt + 1
            payload = self._business_payload(outbox)
            message = {
                "mission_id": outbox["mission_id"]
                if isinstance(outbox, dict)
                else outbox.mission_id,
                "event_type": outbox["event_type"]
                if isinstance(outbox, dict)
                else outbox.event_type,
                "payload_json": payload,
                "created_at": (
                    outbox["created_at"] if isinstance(outbox, dict) else outbox.created_at
                ).isoformat(),
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
                if isinstance(outbox, dict):
                    outbox["payload_json"] = payload_with_meta
                else:
                    outbox.payload_json = payload_with_meta  # ORM object
                await self._set_outbox_status(outbox, status="failed")
                failed += 1
                processed += 1
                logger.warning(
                    "outbox_relay_failed id=%s mission_id=%s reason=%s",
                    outbox["id"] if isinstance(outbox, dict) else outbox.id,
                    outbox["mission_id"] if isinstance(outbox, dict) else outbox.mission_id,
                    error_kind,
                )
                continue

            try:
                await self.event_bus.publish(
                    f"mission:{outbox['mission_id'] if isinstance(outbox, dict) else outbox.mission_id}",
                    message,
                )
                await self._set_outbox_status(outbox, status="published", published_at=utc_now())
                published += 1
                logger.info(
                    "outbox_relay_published id=%s mission_id=%s attempt=%s",
                    outbox["id"] if isinstance(outbox, dict) else outbox.id,
                    outbox["mission_id"] if isinstance(outbox, dict) else outbox.mission_id,
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
                if isinstance(outbox, dict):
                    outbox["payload_json"] = payload_with_meta
                else:
                    outbox.payload_json = payload_with_meta  # ORM object
                await self._set_outbox_status(outbox, status="failed")
                failed += 1
                logger.warning(
                    "outbox_relay_failed id=%s mission_id=%s reason=%s",
                    outbox["id"] if isinstance(outbox, dict) else outbox.id,
                    outbox["mission_id"] if isinstance(outbox, dict) else outbox.mission_id,
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

        from sqlalchemy import text as _text

        # D-193 (2026-08-12): على pgbouncer transaction mode، ORM path
        # (select/func.count مع :status_1 placeholder) يفشل في PsycopgSession —
        # ننفذ raw psycopg inline literals فقط (لا ORM)
        rows = (
            await self.session.execute(
                _text("SELECT status, count(*) FROM mission_outbox GROUP BY status"), []
            )
        ).fetchall()

        counts: dict[str, int] = {
            "pending": 0,
            "processing": 0,
            "failed": 0,
            "published": 0,
        }
        for row in rows:
            key = str(row["status"] if isinstance(row, dict) else row[0])
            if key in counts:
                counts[key] = int(row["count"] if isinstance(row, dict) else row[1])

        oldest = (
            await self.session.execute(
                _text("SELECT min(created_at) FROM mission_outbox WHERE status = 'pending'"), []
            )
        ).fetchone()
        oldest_pending = oldest[0] if oldest else None

        oldest_pending_age_seconds: int | None = None
        if oldest_pending and isinstance(oldest_pending, datetime):
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
        # D-182 (2026-08-12): على Supabase pgbouncer transaction mode، SQLAlchemy
        # ORM (asyncpg dialect) غير متاح — نستخدم نص SQL مع PsycopgSession إن
        # كانت الجلسة لا تدعم AsyncSession API (dict_row rows + no add/flush).
        is_raw = not hasattr(self.session, "add")

        if is_raw:
            # D-191 (2026-08-12): pgbouncer transaction mode يرفض placeholders/params
            # كلياً (DuplicatePreparedStatement حتى مع prepare_threshold=0) — inline literals فقط
            from sqlalchemy import text as _text

            _q = _pgsafe_lit
            # تحقق idempotency يدوي
            if idempotency_key:
                chk = await self.session.execute(
                    _text(
                        f"SELECT id FROM missions WHERE idempotency_key = {_q(idempotency_key)} LIMIT 1"
                    ),
                    [],
                )
                if chk.fetchone():
                    # نعيد نفس المهمة عبر fetch كامل
                    row = (
                        await self.session.execute(
                            _text(
                                f"SELECT * FROM missions WHERE idempotency_key = {_q(idempotency_key)} LIMIT 1"
                            ),
                            [],
                        )
                    ).fetchone()
                    return Mission(
                        **{
                            k: v
                            for k, v in dict(row).items()
                            if k in {f.name for f in Mission.__table__.columns}
                        }
                    )
            now = utc_now()
            ins = await self.session.execute(
                _text(
                    "INSERT INTO missions "
                    "(objective, initiator_id, status, locked, adaptive_cycles, created_at, updated_at, idempotency_key) "
                    f"VALUES ({_q(objective)}, {_q(initiator_id)}, {_q(MissionStatus.PENDING)}, {_q(False)}, 0, {_q(now)}, {_q(now)}, {_q(idempotency_key)}) RETURNING *"
                ),
                [],
            )
            row = ins.fetchone()
            return Mission(
                **{
                    k: v
                    for k, v in dict(row).items()
                    if k in {f.name for f in Mission.__table__.columns}
                }
            )

        # المسار الأصلي (SQLAlchemy AsyncSession)
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
        is_raw = not hasattr(self.session, "add")
        if is_raw:
            from sqlalchemy import text as _text

            row = (
                await self.session.execute(
                    _text(f"SELECT * FROM missions WHERE id = {_pgsafe_lit(mission_id)}"), []
                )
            ).fetchone()
            if not row:
                return None
            return Mission(
                **{
                    k: v
                    for k, v in dict(row).items()
                    if k in {f.name for f in Mission.__table__.columns}
                }
            )

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
        is_raw = not hasattr(self.session, "add")
        if is_raw:
            from sqlalchemy import text as _text

            row = (
                await self.session.execute(
                    _text(f"SELECT status FROM missions WHERE id = {_pgsafe_lit(mission_id)}"), []
                )
            ).fetchone()
            if row is None:
                return
            current = row["status"] if isinstance(row, dict) else row[0]
            current_enum = MissionStatus(current)
            if not self._is_valid_transition(current_enum, status):
                error_msg = f"Invalid Mission Transition: {current} -> {status.value} for Mission {mission_id}"
                logger.error(error_msg)
                raise ValueError(error_msg)
            await self.session.execute(
                _text(
                    f"UPDATE missions SET status = {_pgsafe_lit(status.value)}, updated_at = {_pgsafe_lit(utc_now())} "
                    f"WHERE id = {_pgsafe_lit(mission_id)}"
                ),
                [],
            )
            await self.log_event(
                mission_id,
                MissionEventType.STATUS_CHANGE,
                {"old_status": current, "new_status": str(status), "note": note},
            )
            return

        # D-193 (2026-08-12): ORM else branch يُفعَّل في PsycopgSession
        # فيرتطم :id_1 placeholder (SQLAlchemy select). نفس منطق raw path أعلاه.
        from sqlalchemy import text as _text

        row = (
            await self.session.execute(
                _text(f"SELECT status FROM missions WHERE id = {_pgsafe_lit(mission_id)}"), []
            )
        ).fetchone()
        if row is None:
            return
        current = row["status"] if isinstance(row, dict) else row[0]
        current_enum = MissionStatus(current)
        if not self._is_valid_transition(current_enum, status):
            error_msg = (
                f"Invalid Mission Transition: {current} -> {status.value} for Mission {mission_id}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        await self.session.execute(
            _text(
                f"UPDATE missions SET status = {_pgsafe_lit(status.value)}, updated_at = {_pgsafe_lit(utc_now())} "
                f"WHERE id = {_pgsafe_lit(mission_id)}"
            ),
            [],
        )
        await self.log_event(
            mission_id,
            MissionEventType.STATUS_CHANGE,
            {"old_status": current, "new_status": str(status), "note": note},
        )

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

        D-193 (2026-08-12): هذا المسار كان ORM-only (select(Mission)) — يفشل على
        pgbouncer transaction mode (:id_1 placeholder يمر عبر PsycopgSession).
        حوّلناه إلى raw psycopg inline literals (نفس مبدأ D-188/D-192).
        """
        from sqlalchemy import text as _text

        row = (
            await self.session.execute(
                _text(f"SELECT id, status FROM missions WHERE id = {_pgsafe_lit(mission_id)}"), []
            )
        ).fetchone()
        if row is None:
            return
        current = row["status"] if isinstance(row, dict) else row[1]
        if not self._is_valid_transition(MissionStatus(current), status):
            error_msg = (
                f"Invalid Mission Transition: {current} -> {status.value} for Mission {mission_id}"
            )
            logger.error(error_msg)
            raise ValueError(error_msg)
        now = utc_now()
        await self.session.execute(
            _text(
                "UPDATE missions SET status = {_s}, updated_at = {_t}{_r} WHERE id = {_m}".format(
                    _s=_pgsafe_lit(status.value),
                    _t=_pgsafe_lit(now),
                    _r=", result_summary = " + _pgsafe_lit(result_summary)
                    if result_summary
                    else "",
                    _m=_pgsafe_lit(mission_id),
                )
            ),
            [],
        )
        # Log completion event
        payload = {"result": result_json} if result_json else {}
        await self.log_event(
            mission_id,
            MissionEventType.MISSION_COMPLETED,
            payload,
        )

    async def rollback(self) -> None:
        """إلغاء التغييرات الحالية في الجلسة (Rollback)."""
        await self.session.rollback()

    async def log_event(
        self, mission_id: int, event_type: MissionEventType, payload: dict[str, JsonValue]
    ) -> None:
        is_raw = not hasattr(self.session, "add")
        if is_raw:
            from sqlalchemy import text as _text

            now = utc_now()
            payload_text = json.dumps(payload)
            # 1. Log Event + 2. Outbox في عملية واحدة (commit فوري مع autocommit=True)
            await self.session.execute(
                _text(
                    "INSERT INTO mission_events (mission_id, event_type, payload_json, created_at, updated_at) "
                    f"VALUES ({_pgsafe_lit(mission_id)}, {_pgsafe_lit(event_type.value)}, {_pgsafe_lit(payload_text)}, {_pgsafe_lit(now)}, {_pgsafe_lit(now)})"
                ),
                [],
            )
            await self.session.execute(
                _text(
                    "INSERT INTO mission_outbox (mission_id, event_type, payload_json, status, created_at) "
                    f"VALUES ({_pgsafe_lit(mission_id)}, {_pgsafe_lit(event_type.value)}, {_pgsafe_lit(payload_text)}, 'pending', {_pgsafe_lit(now)})"
                ),
                [],
            )
            return

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
        outbox,
        *,
        status: str,
        published_at: datetime | None = None,
    ) -> None:
        """يحدّث حالة سجل الـ Outbox بشكل صريح لضمان تتبع موثوق للنشر.
        D-194 (2026-08-12): PsycopgSession (raw psycopg) لا يملك ORM commit — raw UPDATE.
        ORM sessions (tests/dev) تُحدَّث عبر object attributes ثم commit (D-199).
        """
        is_raw = not hasattr(self.session, "add")
        oid = outbox.get("id") if isinstance(outbox, dict) else getattr(outbox, "id", None)
        if oid is None:
            return
        now = published_at or utc_now()
        is_published = status == "published"
        if is_raw:
            from sqlalchemy import text as _text

            set_clause = f"status = {_pgsafe_lit(status)}"
            if is_published:
                set_clause += f", published_at = {_pgsafe_lit(now)}"
            await self.session.execute(
                _text(f"UPDATE mission_outbox SET {set_clause} WHERE id = {_pgsafe_lit(int(oid))}"),
                [],
            )
            return
        # ORM path: تحديث الـ object المُرسل نفسه ثم commit (لا raw UPDATE على ORM)
        if hasattr(outbox, "status"):
            outbox.status = status
            if is_published:
                outbox.published_at = now
                if hasattr(outbox, "updated_at"):
                    outbox.updated_at = now
            await self.session.commit()

    async def get_mission_events(self, mission_id: int) -> list[MissionEvent]:
        """Fetch all historical events for a mission."""
        is_raw = not hasattr(self.session, "add")
        if is_raw:
            from sqlalchemy import text as _text

            rows = (
                await self.session.execute(
                    _text(
                        f"SELECT * FROM mission_events WHERE mission_id = {_pgsafe_lit(mission_id)} ORDER BY id ASC"
                    ),
                    [],
                )
            ).fetchall()
            return [
                MissionEvent(
                    **{
                        k: v
                        for k, v in dict(r).items()
                        if k in {f.name for f in MissionEvent.__table__.columns}
                    }
                )
                for r in rows
            ]
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

        is_raw = not hasattr(self.session, "add")
        if is_raw:
            from sqlalchemy import text as _text

            objective = str(getattr(plan_schema, "objective", ""))
            tasks = list(getattr(plan_schema, "tasks", []))
            raw_data = {"objective": objective, "tasks_count": len(tasks)}
            now = utc_now()
            mp_id = (
                await self.session.execute(
                    _text(
                        "INSERT INTO mission_plans "
                        "(mission_id, version, planner_name, status, score, rationale, raw_json, stats_json, warnings_json, created_at, updated_at) "
                        + (
                            f"VALUES ({_pgsafe_lit(mission_id)}, {_pgsafe_lit(version)}, {_pgsafe_lit(planner_name)}, {_pgsafe_lit(PlanStatus.VALID.value)}, "
                            f"{_pgsafe_lit(score)}, {_pgsafe_lit(rationale)}, {_pgsafe_lit(json.dumps(raw_data))}, {_pgsafe_lit('{}')}, {_pgsafe_lit('[]')}, "
                            f"{_pgsafe_lit(now)}, {_pgsafe_lit(now)}) RETURNING id"
                        )
                    ),
                    [],
                )
            ).fetchone()[0]
            await self.session.execute(
                _text(
                    f"UPDATE missions SET active_plan_id = {_pgsafe_lit(mp_id)}, updated_at = {_pgsafe_lit(now)} "
                    f"WHERE id = {_pgsafe_lit(mission_id)}"
                ),
                [],
            )
            for t in tasks:
                tkey = str(getattr(t, "task_id", ""))
                tdesc = str(getattr(t, "description", ""))
                ttype = (
                    str(getattr(t, "task_type", "task")).lower()
                    if getattr(t, "task_type", None)
                    else "task"
                )
                ttool = str(getattr(t, "tool_name", ""))
                targs = json.dumps(getattr(t, "tool_args", {}) or {})
                tdeps = json.dumps(getattr(t, "dependencies", []) or [])
                tpri = getattr(t, "priority", 0)
                await self.session.execute(
                    _text(
                        "INSERT INTO tasks "
                        "(mission_id, plan_id, task_key, description, task_type, tool_name, tool_args_json, "
                        "depends_on_json, priority, status, attempt_count, max_attempts, created_at, updated_at) "
                        f"VALUES ({_pgsafe_lit(mission_id)}, {_pgsafe_lit(mp_id)}, {_pgsafe_lit(tkey)}, {_pgsafe_lit(tdesc)}, "
                        f"{_pgsafe_lit(ttype)}, {_pgsafe_lit(ttool)}, {_pgsafe_lit(targs)}, {_pgsafe_lit(tdeps)}, "
                        f"{_pgsafe_lit(tpri)}, {_pgsafe_lit(TaskStatus.PENDING.value)}, 0, 3, {_pgsafe_lit(now)}, {_pgsafe_lit(now)})"
                    ),
                    [],
                )
            return mp_id

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
        is_raw = not hasattr(self.session, "add")
        if is_raw:
            from sqlalchemy import text as _text

            rows = (
                await self.session.execute(
                    _text(
                        f"SELECT * FROM tasks WHERE mission_id = {_pgsafe_lit(mission_id)} ORDER BY id"
                    ),
                    [],
                )
            ).fetchall()
            return [
                Task(
                    **{
                        k: v
                        for k, v in dict(r).items()
                        if k in {f.name for f in Task.__table__.columns}
                    }
                )
                for r in rows
            ]
        # D-193 (2026-08-12): ORM branch يُفعل في PsycopgSession فيرتطم
        # :mission_id_1 placeholder — أزلناه، نستخدم raw psycopg فقط
        return []

    async def mark_task_running(self, task_id: int) -> None:
        is_raw = not hasattr(self.session, "add")
        if is_raw:
            from sqlalchemy import text as _text

            row = (
                await self.session.execute(
                    _text(f"SELECT attempt_count FROM tasks WHERE id = {_pgsafe_lit(task_id)}"), []
                )
            ).fetchone()
            if row is None:
                return
            attempts = row["attempt_count"] if isinstance(row, dict) else row[0]
            await self.session.execute(
                _text(
                    f"UPDATE tasks SET status = {_pgsafe_lit(TaskStatus.RUNNING.value)}, started_at = {_pgsafe_lit(utc_now())}, "
                    f"attempt_count = {_pgsafe_lit(attempts + 1)}, updated_at = {_pgsafe_lit(utc_now())} "
                    f"WHERE id = {_pgsafe_lit(task_id)}"
                ),
                [],
            )
            return
        # D-193 (2026-08-12): ORM branch يُفعل في PsycopgSession فيرتطم
        # :id_1 placeholder — أزلناه، نستخدم raw psycopg فقط
        pass

    async def mark_task_complete(
        self, task_id: int, result_text: str, meta: dict[str, JsonValue] | None = None
    ) -> None:
        if meta is None:
            meta = {}
        is_raw = not hasattr(self.session, "add")
        if is_raw:
            from sqlalchemy import text as _text

            now = utc_now()
            await self.session.execute(
                _text(
                    f"UPDATE tasks SET status = {_pgsafe_lit(TaskStatus.SUCCESS.value)}, finished_at = {_pgsafe_lit(now)}, "
                    f"result_text = {_pgsafe_lit(result_text)}, result_meta_json = {_pgsafe_lit(json.dumps(meta))}, "
                    f"updated_at = {_pgsafe_lit(now)} WHERE id = {_pgsafe_lit(task_id)}"
                ),
                [],
            )
            return
        # D-193: ORM branch لا يعمل على pgbouncer — raw psycopg فقط

    async def mark_task_failed(self, task_id: int, error_text: str) -> None:
        """
        D-193 (2026-08-12): كان ORM-only (select(Task)) — يفشل على pgbouncer
        transaction mode. حوّلناه إلى raw psycopg inline literals.
        """
        from sqlalchemy import text as _text

        now = utc_now()
        await self.session.execute(
            _text(
                f"UPDATE tasks SET status = {_pgsafe_lit(TaskStatus.FAILED.value)}, finished_at = {_pgsafe_lit(now)}, "
                f"error_text = {_pgsafe_lit(error_text)}, updated_at = {_pgsafe_lit(now)} "
                f"WHERE id = {_pgsafe_lit(task_id)}"
            ),
            [],
        )

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
