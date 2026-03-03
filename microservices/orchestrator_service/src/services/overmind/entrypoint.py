"""
Unified Entrypoint for Overmind Missions.
Implements the Command Pattern to standardize mission execution.
Ensures Single Control Plane and Source of Truth.
"""

import asyncio
import logging

import redis.asyncio as redis
from sqlalchemy.ext.asyncio import AsyncSession

from microservices.orchestrator_service.src.core.config import get_settings
from microservices.orchestrator_service.src.models.mission import (
    Mission,
    MissionEventType,
    MissionStatus,
)
from microservices.orchestrator_service.src.services.overmind.domain.types import MissionContext
from microservices.orchestrator_service.src.services.overmind.factory import create_overmind
from microservices.orchestrator_service.src.services.overmind.state import MissionStateManager

logger = logging.getLogger(__name__)


async def _dispatch_mission_task(
    *,
    state_manager: MissionStateManager,
    mission_id: int,
    force_research: bool,
    triggered_by: str,
) -> None:
    """ينفّذ إطلاق المهمة مع تسجيل حدث بدء واضح يدعم تتبع مسار التشغيل."""
    await state_manager.log_event(
        mission_id,
        MissionEventType.STATUS_CHANGE,
        {"status": "starting", "triggered_by": triggered_by},
    )
    _task = asyncio.create_task(_run_mission_task(mission_id, force_research))  # noqa: RUF006


async def start_mission(
    session: AsyncSession,
    objective: str,
    initiator_id: int,
    context: MissionContext | None = None,
    force_research: bool = False,
    idempotency_key: str | None = None,
) -> Mission:
    """
    Unified Entrypoint to Start a Mission.
    Handles Idempotency, Locking, Persistence, and Execution Trigger.

    Args:
        session: The active database session (request-scoped).
        objective: The mission objective.
        initiator_id: The ID of the user initiating the mission.
        context: Optional context dictionary.
        force_research: Flag to force research mode.
        idempotency_key: Optional key to ensure idempotency.

    Returns:
        The created Mission object.
    """
    settings = get_settings()
    # Fallback to localhost if not set (dev env)
    redis_url = getattr(settings, "REDIS_URL", "redis://redis:6379")

    # 1. Create Mission Record (Pending) in the Single Source of Truth (DB)
    state_manager = MissionStateManager(session)
    # Check if mission already exists (Idempotency) happens inside create_mission
    mission = await state_manager.create_mission(
        objective, initiator_id, context, idempotency_key=idempotency_key
    )

    # If the mission was already created and is running/terminal, we return it.
    # But we should only trigger execution if it's in a state that needs it (e.g. PENDING).
    # However, create_mission returns the object. We need to know if it was *just* created.
    # For now, we rely on the Lock. If we can't acquire lock, we assume it's running.
    # Better: check status.
    if mission.status != MissionStatus.PENDING:
        logger.info(
            f"Mission {mission.id} already exists with status {mission.status}. Returning existing instance."
        )
        return mission

    # 2. Acquire Lock (Optimistic)
    # We use a lock to ensure that if we add retry logic later, we don't spawn doubles.
    # For a NEW mission with a unique ID, collision is unlikely, but good practice.
    lock_key = f"mission_lock:{mission.id}"
    client = redis.from_url(redis_url, encoding="utf-8", decode_responses=True)

    try:
        lock = client.lock(lock_key, timeout=10)
        acquired = await lock.acquire(blocking=False)

        if not acquired:
            logger.warning(f"Mission {mission.id} is locked. Skipping execution trigger.")
            return mission

        try:
            # 3. Log Started Event + Trigger Background Execution
            await _dispatch_mission_task(
                state_manager=state_manager,
                mission_id=mission.id,
                force_research=force_research,
                triggered_by="entrypoint",
            )

            logger.info(f"Mission {mission.id} dispatched via Unified Entrypoint.")

        finally:
            await lock.release()

    except Exception as redis_error:
        logger.warning(
            "Redis lock unavailable for mission %s; dispatching in degraded mode without distributed lock: %s",
            mission.id,
            redis_error,
        )
        try:
            await _dispatch_mission_task(
                state_manager=state_manager,
                mission_id=mission.id,
                force_research=force_research,
                triggered_by="entrypoint_degraded_no_lock",
            )
            logger.info("Mission %s dispatched in degraded mode without Redis lock.", mission.id)
        except Exception as dispatch_error:
            logger.error(f"Failed to dispatch mission {mission.id}: {dispatch_error}")
            await state_manager.update_mission_status(
                mission.id,
                MissionStatus.FAILED,
                note=f"Dispatch Error: {dispatch_error}",
            )
            raise dispatch_error
    finally:
        try:
            await client.close()
        except Exception as close_error:
            logger.warning("Failed to close Redis client for mission %s: %s", mission.id, close_error)

    return mission


async def _run_mission_task(mission_id: int, force_research: bool = False) -> None:
    """
    Background Task Wrapper for Overmind Execution.
    Creates a NEW session for the execution (isolated from the request).
    """
    from microservices.orchestrator_service.src.core.database import (
        async_session_factory,  # Lazy import to avoid circular deps
    )

    async with async_session_factory() as session:
        try:
            # Re-hydrate the Overmind Service with the new session
            overmind = await create_overmind(session)

            # Execute the Logic (The Brain)
            await overmind.run_mission(mission_id, force_research=force_research)

        except Exception as e:
            logger.critical(
                f"FATAL: Mission {mission_id} background task crashed: {e}", exc_info=True
            )

            # Attempt to record failure
            try:
                state_manager = MissionStateManager(session)
                await state_manager.update_mission_status(
                    mission_id, MissionStatus.FAILED, note=f"System Crash: {e}"
                )
            except Exception as db_err:
                logger.critical(f"Failed to log crash for mission {mission_id}: {db_err}")
