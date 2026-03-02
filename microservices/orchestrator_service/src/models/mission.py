"""
Mission Domain Models (Microservice Version).
Decoupled from User Service.
"""

from __future__ import annotations

import json
from datetime import datetime
from enum import Enum, StrEnum

from sqlalchemy import Column, DateTime, MetaData, Text, func
from sqlalchemy.orm import relationship
from sqlmodel import Field, Relationship, SQLModel


def utc_now():
    return datetime.utcnow()


class FlexibleEnum(Enum):
    """Placeholder for FlexibleEnum if needed, or just use Enum."""

    pass


class CaseInsensitiveEnum(StrEnum):
    """Case insensitive enum mixin."""

    @classmethod
    def _missing_(cls, value):
        for member in cls:
            if member.value.lower() == value.lower():
                return member
        return None  # Fix RET503


class JSONText(Text):
    """JSON type for Text column."""

    def bind_processor(self, dialect):
        def process(value):
            if value is None:
                return None
            return json.dumps(value)

        return process

    def result_processor(self, dialect, coltype):
        def process(value):
            if value is None:
                return None
            return json.loads(value)

        return process


class OrchestratorSQLModel(SQLModel):
    """قاعدة SQLModel مع metadata معزولة لخدمة المنسق."""

    metadata = MetaData()


class MissionStatus(CaseInsensitiveEnum):
    PENDING = "pending"
    PLANNING = "planning"
    PLANNED = "planned"
    RUNNING = "running"
    ADAPTING = "adapting"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    FAILED = "failed"
    CANCELED = "canceled"


class PlanStatus(CaseInsensitiveEnum):
    DRAFT = "draft"
    VALID = "valid"
    INVALID = "invalid"
    SELECTED = "selected"
    ABANDONED = "abandoned"


class TaskStatus(CaseInsensitiveEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCESS = "success"
    FAILED = "failed"
    RETRY = "retry"
    SKIPPED = "skipped"


class MissionEventType(CaseInsensitiveEnum):
    CREATED = "mission_created"
    STATUS_CHANGE = "status_change"
    ARCHITECTURE_CLASSIFIED = "architecture_classified"
    PLAN_SELECTED = "plan_selected"
    EXECUTION_STARTED = "execution_started"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    REPLAN_TRIGGERED = "replan_triggered"
    REPLAN_APPLIED = "replan_applied"
    RISK_SUMMARY = "risk_summary"
    MISSION_COMPLETED = "mission_completed"
    MISSION_FAILED = "mission_failed"
    FINALIZED = "mission_finalized"


class MicroMission(OrchestratorSQLModel, table=True):
    __tablename__ = "missions"
    id: int | None = Field(default=None, primary_key=True)
    objective: str = Field(sa_column=Column(Text))
    status: MissionStatus = Field(
        default=MissionStatus.PENDING,
    )
    initiator_id: int = Field(index=True)

    active_plan_id: int | None = Field(default=None, nullable=True, index=True)

    # Idempotency
    idempotency_key: str | None = Field(default=None, unique=True, index=True, max_length=128)

    locked: bool = Field(default=False)
    result_summary: str | None = Field(default=None, sa_column=Column(Text))
    total_cost_usd: float | None = Field(default=None)
    adaptive_cycles: int = Field(default=0)

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    # Relationships
    tasks: list[MicroTask] = Relationship(
        sa_relationship=relationship(
            "MicroTask",
            back_populates="mission",
        )
    )
    mission_plans: list[MicroMissionPlan] = Relationship(
        sa_relationship=relationship(
            "MicroMissionPlan",
            back_populates="mission",
            foreign_keys="[MicroMissionPlan.mission_id]",
        )
    )
    events: list[MicroMissionEvent] = Relationship(
        sa_relationship=relationship("MicroMissionEvent", back_populates="mission")
    )


class MicroMissionPlan(OrchestratorSQLModel, table=True):
    __tablename__ = "mission_plans"
    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    version: int = Field(default=1)
    planner_name: str = Field(max_length=100)
    status: PlanStatus = Field(default=PlanStatus.DRAFT)
    score: float = Field(default=0.0)
    rationale: str | None = Field(sa_column=Column(Text))
    raw_json: dict | None = Field(sa_column=Column(JSONText))
    stats_json: dict | None = Field(sa_column=Column(JSONText))
    warnings_json: dict | None = Field(sa_column=Column(JSONText))
    content_hash: str | None = Field(max_length=64)

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    # Relationships
    mission: MicroMission = Relationship(
        sa_relationship=relationship(
            "MicroMission",
            back_populates="mission_plans",
            foreign_keys="[MicroMissionPlan.mission_id]",
        )
    )
    tasks: list[MicroTask] = Relationship(
        sa_relationship=relationship("MicroTask", back_populates="plan")
    )


class MicroTask(OrchestratorSQLModel, table=True):
    __tablename__ = "tasks"
    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    plan_id: int | None = Field(default=None, foreign_key="mission_plans.id", index=True)
    task_key: str = Field(max_length=5)
    description: str | None = Field(sa_column=Column(Text))
    tool_name: str | None = Field(max_length=100)
    tool_args_json: dict | None = Field(default=None, sa_column=Column(JSONText))
    status: TaskStatus = Field(default=TaskStatus.PENDING)
    attempt_count: int = Field(default=0)
    max_attempts: int = Field(default=3)
    priority: int = Field(default=0)
    risk_level: str | None = Field(max_length=50)
    criticality: str | None = Field(max_length=50)
    depends_on_json: list | None = Field(default=None, sa_column=Column(JSONText))
    result_text: str | None = Field(sa_column=Column(Text))
    result_meta_json: dict | None = Field(default=None, sa_column=Column(JSONText))
    error_text: str | None = Field(sa_column=Column(Text))

    started_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True)))
    finished_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True)))
    next_retry_at: datetime | None = Field(sa_column=Column(DateTime(timezone=True)))
    duration_ms: int | None = Field(default=0)

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    updated_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now()),
    )

    # Relationships
    mission: MicroMission = Relationship(
        sa_relationship=relationship(
            "MicroMission",
            back_populates="tasks",
        )
    )
    plan: MicroMissionPlan = Relationship(
        sa_relationship=relationship(
            "MicroMissionPlan",
            back_populates="tasks",
        )
    )


class MicroMissionEvent(OrchestratorSQLModel, table=True):
    __tablename__ = "mission_events"
    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(foreign_key="missions.id", index=True)
    event_type: MissionEventType = Field()
    payload_json: dict | None = Field(default=None, sa_column=Column(JSONText))

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )

    # Relationships
    mission: MicroMission = Relationship(
        sa_relationship=relationship("MicroMission", back_populates="events")
    )


class MicroMissionOutbox(OrchestratorSQLModel, table=True):
    """
    Transactional Outbox for Mission Events.
    Ensures that events are published to the Event Bus (Redis) reliably.
    """

    __tablename__ = "mission_outbox"
    id: int | None = Field(default=None, primary_key=True)
    mission_id: int = Field(index=True)
    event_type: str = Field(index=True)
    payload_json: dict | None = Field(default=None, sa_column=Column(JSONText))
    status: str = Field(default="pending", index=True)  # pending, published, failed

    created_at: datetime = Field(
        default_factory=utc_now,
        sa_column=Column(DateTime(timezone=True), server_default=func.now()),
    )
    published_at: datetime | None = Field(default=None, sa_column=Column(DateTime(timezone=True)))


# Aliases
Mission = MicroMission
MissionPlan = MicroMissionPlan
Task = MicroTask
MissionEvent = MicroMissionEvent
MissionOutbox = MicroMissionOutbox


# Helpers
def log_mission_event(
    mission: Mission, event_type: MissionEventType, payload: dict, session=None
) -> None:
    """
    Log a mission event to the database.
    """
    evt = MissionEvent(mission_id=mission.id, event_type=event_type, payload_json=payload)
    if session:
        session.add(evt)


def update_mission_status(
    mission: Mission, status: MissionStatus, note: str | None = None, session=None
) -> None:
    """
    Update mission status.
    """
    mission.status = status
    mission.updated_at = utc_now()
