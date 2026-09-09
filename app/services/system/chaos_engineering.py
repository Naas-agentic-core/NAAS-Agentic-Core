from __future__ import annotations

import logging
import random
import threading
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class FaultType(Enum):
    """أنواع الأعطال التي يمكن حقنها."""

    LATENCY = "latency"
    ERROR = "error"
    TIMEOUT = "timeout"
    CIRCUIT_BREAKER = "circuit_breaker"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    NETWORK_PARTITION = "network_partition"
    SERVICE_UNAVAILABLE = "service_unavailable"


class ExperimentStatus(Enum):
    """حالات تنفيذ التجارب."""

    SCHEDULED = "scheduled"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class BlastRadiusLevel(Enum):
    """مستويات نطاق تأثير التجارب."""

    MINIMAL = "minimal"
    LIMITED = "limited"
    MODERATE = "moderate"
    EXTENSIVE = "extensive"


@dataclass
class SteadyStateHypothesis:
    """فرضية الحالة المستقرة للنظام."""

    hypothesis_id: str
    description: str
    validation_function: Callable[[], bool]
    tolerance_threshold: float = 0.95
    measurement_window_seconds: int = 60


@dataclass
class FaultInjection:
    """تهيئة حقن الأعطال."""

    fault_id: str
    fault_type: FaultType
    target_service: str
    parameters: dict[str, object] = field(default_factory=dict)
    probability: float = 1.0
    blast_radius: BlastRadiusLevel = BlastRadiusLevel.LIMITED
    duration_seconds: int = 60
    abort_on_metric: str | None = None
    abort_threshold: float | None = None


@dataclass
class ChaosExperiment:
    """تعريف تجربة الفوضى."""

    experiment_id: str
    name: str
    description: str
    steady_state_hypothesis: SteadyStateHypothesis
    fault_injections: list[FaultInjection]
    status: ExperimentStatus = ExperimentStatus.SCHEDULED
    started_at: datetime | None = None
    completed_at: datetime | None = None
    hypothesis_validated: bool | None = None
    observations: list[dict[str, object]] = field(default_factory=list)
    metrics: dict[str, object] = field(default_factory=dict)
    auto_rollback: bool = True
    blast_radius: BlastRadiusLevel = BlastRadiusLevel.LIMITED


@dataclass
class GameDay:
    """فعالية محاكاة يوم الفوضى."""

    game_day_id: str
    name: str
    scenario: str
    experiments: list[str]
    scheduled_at: datetime
    duration_hours: int
    participants: list[str]
    runbook_url: str | None = None


@dataclass(frozen=True)
class ExperimentConfig:
    """تهيئة موحدة لإنشاء تجربة فوضى."""

    name: str
    description: str
    steady_state_hypothesis: SteadyStateHypothesis
    fault_injections: list[FaultInjection]
    blast_radius: BlastRadiusLevel = BlastRadiusLevel.LIMITED


class ChaosMonkey:
    """
    قرد الفوضى - يحقن أعطالًا عشوائية في الخدمات.

    مستوحى من Chaos Monkey الخاص بـ Netflix.
    """

    def __init__(
        self,
        enabled: bool = False,
        probability: float = 0.01,
        blast_radius: BlastRadiusLevel = BlastRadiusLevel.MINIMAL,
    ):
        self.enabled = enabled
        self.probability = probability
        self.blast_radius = blast_radius
        self.active_faults: dict[str, FaultInjection] = {}
        self.lock = threading.RLock()

    def _get_fault_parameters(self, fault_type: FaultType) -> dict[str, object]:
        """إرجاع معلمات مناسبة لنوع العطل."""
        if fault_type == FaultType.LATENCY:
            return {"delay_ms": random.randint(100, 5000)}
        if fault_type == FaultType.ERROR:
            return {
                "error_message": "Chaos Monkey induced error",
                "error_code": random.choice([500, 503, 504]),
            }
        if fault_type == FaultType.TIMEOUT:
            return {"timeout_ms": random.randint(30000, 60000)}
        return {}


class ChaosEngineer:
    """
    خدمة هندسة الفوضى.

    تدير تجارب الفوضى وتتحقق من متانة النظام.
    """

    def __init__(self):
        self.experiments: dict[str, ChaosExperiment] = {}
        self.game_days: dict[str, GameDay] = {}
        self.chaos_monkey = ChaosMonkey()
        self.experiment_history: deque = deque(maxlen=100)
        self.lock = threading.RLock()

    def create_experiment(self, config: ExperimentConfig) -> str:
        """إنشاء تجربة فوضى اعتمادًا على تهيئة موحدة."""
        experiment_id = str(uuid.uuid4())
        experiment = ChaosExperiment(
            experiment_id=experiment_id,
            name=config.name,
            description=config.description,
            steady_state_hypothesis=config.steady_state_hypothesis,
            fault_injections=config.fault_injections,
            blast_radius=config.blast_radius,
        )
        with self.lock:
            self.experiments[experiment_id] = experiment
        logging.getLogger(__name__).info(
            f"Chaos experiment created: {config.name} ({experiment_id})"
        )
        return experiment_id

    def _activate_fault(self, fault: FaultInjection):
        """تفعيل حقن عطل محدد."""
        logging.getLogger(__name__).warning(
            f"Activating fault: {fault.fault_type.value} on {fault.target_service}"
        )

    def _rollback_faults(self, experiment: ChaosExperiment):
        """إرجاع جميع الأعطال في التجربة."""
        logging.getLogger(__name__).info(f"Rolling back faults for experiment: {experiment.name}")
        for _fault in experiment.fault_injections:
            pass

    def get_experiment_report(self, experiment_id: str) -> dict[str, object] | None:
        """الحصول على تقرير مفصل عن تجربة محددة."""
        with self.lock:
            experiment = self.experiments.get(experiment_id)
            if not experiment:
                return None
            return {
                "experiment_id": experiment.experiment_id,
                "name": experiment.name,
                "description": experiment.description,
                "status": experiment.status.value,
                "started_at": experiment.started_at.isoformat() if experiment.started_at else None,
                "completed_at": experiment.completed_at.isoformat()
                if experiment.completed_at
                else None,
                "hypothesis_validated": experiment.hypothesis_validated,
                "observations": experiment.observations,
                "fault_count": len(experiment.fault_injections),
                "blast_radius": experiment.blast_radius.value,
            }

    def get_metrics(self) -> dict[str, object]:
        """الحصول على مؤشرات هندسة الفوضى."""
        with self.lock:
            total_experiments = len(self.experiments)
            completed = sum(
                1 for e in self.experiments.values() if e.status == ExperimentStatus.COMPLETED
            )
            validated = sum(1 for e in self.experiments.values() if e.hypothesis_validated is True)
            return {
                "total_experiments": total_experiments,
                "completed": completed,
                "validated": validated,
                "validation_rate": validated / completed * 100 if completed > 0 else 0,
                "chaos_monkey_enabled": self.chaos_monkey.enabled,
                "active_faults": len(self.chaos_monkey.active_faults),
                "scheduled_game_days": len(self.game_days),
            }


_chaos_engineer_instance: ChaosEngineer | None = None
_chaos_lock = threading.Lock()


def get_chaos_engineer() -> ChaosEngineer:
    """الحصول على نسخة وحيدة لخدمة هندسة الفوضى."""
    global _chaos_engineer_instance
    if _chaos_engineer_instance is None:
        with _chaos_lock:
            if _chaos_engineer_instance is None:
                _chaos_engineer_instance = ChaosEngineer()
    return _chaos_engineer_instance
