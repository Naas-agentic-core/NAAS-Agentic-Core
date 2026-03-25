"""
البروتوكولات والواجهات الأساسية (Core Protocols & Interfaces).

يحدد الفئات الأساسية المجردة والبروتوكولات للتطبيق.
يطبق مبدأ Abstraction Barriers من SICP لفصل التعريف عن التطبيق.

المبادئ (Principles):
- Harvard CS50 2025: توثيق عربي، صرامة الأنواع
- Berkeley SICP: Abstraction Barriers (الواجهات تخفي التطبيق)
- SOLID: Interface Segregation (واجهات صغيرة ومحددة)

الاستخدام (Usage):
    class MyService:
        def __init__(self, repo: RepositoryProtocol):
            self.repo = repo  # يعمل مع أي تطبيق للبروتوكول
"""

import asyncio
from collections.abc import AsyncGenerator
from typing import Protocol, runtime_checkable

# Consolidated to use the microservice models
from microservices.orchestrator_service.src.models.mission import (
    Mission,
    MissionEvent,
    MissionEventType,
    MissionStatus,
    Task,
)


@runtime_checkable
class LifecycleProtocol(Protocol):
    """
    بروتوكول دورة الحياة (Lifecycle Protocol).
    """

    async def initialize(self) -> None:
        """Initialize the component"""
        ...

    async def shutdown(self) -> None:
        """Shutdown the component"""
        ...


@runtime_checkable
class BaseService(LifecycleProtocol, Protocol):
    """
    بروتوكول أساسي لجميع خدمات التطبيق.

    يحدد الواجهة الأساسية التي يجب أن تلتزم بها جميع الخدمات.
    """

    @property
    def name(self) -> str:
        """Service unique name"""
        ...

    @property
    def version(self) -> str:
        """Service version"""
        ...

    async def health_check(self) -> dict[str, object]:
        """Check service health"""
        ...


@runtime_checkable
class PluginProtocol(BaseService, Protocol):
    """
    بروتوكول الإضافة (Plugin Protocol).

    يحل محل IPlugin القديم.
    """

    @property
    def plugin_type(self) -> str:
        """Type of plugin (service, processor, etc.)"""
        ...

    @property
    def dependencies(self) -> list[str]:
        """List of required dependencies"""
        ...

    def configure(self, config: dict[str, object]) -> None:
        """Configure the plugin"""
        ...


@runtime_checkable
class EventBusProtocol(Protocol):
    """
    بروتوكول ناقل الأحداث (Event Bus Protocol).

    يحدد واجهة بسيطة للنشر والاشتراك لضمان عزل الطبقات العليا
    عن التنفيذ الفعلي لناقل الأحداث.
    """

    async def publish(self, channel: str, event: object) -> None:
        """ينشر حدثاً داخل قناة محددة."""
        ...

    def subscribe_queue(self, channel: str) -> asyncio.Queue[object]:
        """ينشئ اشتراكاً عبر صف لهذه القناة."""
        ...

    async def subscribe(self, channel: str) -> AsyncGenerator[object, None]:
        """يشترك في القناة كتدفق غير متزامن."""
        ...


@runtime_checkable
class PlannerProtocol(Protocol):
    """
    بروتوكول التخطيط (Planner Protocol).

    يحل محل PlannerInterface القديم.
    """

    def generate_plan(
        self,
        objective: str,
        context: dict[str, object] | None = None,
        max_tasks: int | None = None,
    ) -> dict[str, object]:
        """Generate a plan for the given objective."""
        ...

    def validate_plan(self, plan: dict[str, object]) -> bool:
        """Validate a generated plan."""
        ...

    def get_capabilities(self) -> set[str]:
        """Get planner capabilities."""
        ...


@runtime_checkable
class StrategyProtocol[TInput, TOutput](Protocol):
    """
    بروتوكول الاستراتيجية (Strategy Protocol).

    يحل محل StrategyInterface القديم.
    """

    def execute(self, input_data: TInput) -> TOutput:
        """Execute strategy algorithm."""
        ...

    def get_name(self) -> str:
        """Get strategy name."""
        ...

    def is_applicable(self, context: dict[str, object]) -> bool:
        """Check if strategy is applicable in given context."""
        ...


@runtime_checkable
class RepositoryProtocol[T](Protocol):
    """
    بروتوكول أساسي للمستودعات (Repositories).

    يحدد الواجهة الأساسية لعمليات الوصول للبيانات (Data Access Layer).
    يحل محل RepositoryInterface القديم.
    """

    def save(self, entity: T) -> T:
        """Save an entity."""
        ...

    def find_by_id(self, entity_id: str) -> T | None:
        """Find entity by ID."""
        ...

    def find_all(self, filters: dict[str, object] | None = None) -> list[T]:
        """Find all entities matching filters."""
        ...

    def delete(self, entity_id: str) -> bool:
        """Delete entity by ID."""
        ...

    def update(self, entity_id: str, updates: dict[str, object]) -> T | None:
        """Update entity fields."""
        ...


@runtime_checkable
class CollaborationContext(Protocol):
    """
    بروتوكول سياق التعاون بين الوكلاء (Collaboration Context).

    يوفر آلية آمنة للخيوط (thread-safe) لتخزين واسترجاع السياق المشترك
    بين الوكلاء المختلفين في النظام.
    """

    shared_memory: dict[str, object]

    def update(self, key: str, value: dict[str, str | int | bool]) -> None: ...

    def get(self, key: str) -> object | None: ...


@runtime_checkable
class AgentPlanner(Protocol):
    """
    بروتوكول وكيل التخطيط الاستراتيجي (Strategist Agent).
    """

    async def create_plan(
        self, objective: str, context: CollaborationContext
    ) -> dict[str, object]: ...


@runtime_checkable
class AgentArchitect(Protocol):
    """
    بروتوكول وكيل التصميم المعماري (Architect Agent).
    """

    async def design_solution(
        self, plan: dict[str, object], context: CollaborationContext
    ) -> dict[str, object]: ...


@runtime_checkable
class AgentExecutor(Protocol):
    """
    بروتوكول وكيل التنفيذ (Operator Agent).
    """

    async def execute_tasks(
        self, design: dict[str, object], context: CollaborationContext
    ) -> dict[str, object]: ...


@runtime_checkable
class AgentReflector(Protocol):
    """
    بروتوكول وكيل المراجعة والتدقيق (Auditor Agent).
    """

    async def review_work(
        self, result: dict[str, object], original_objective: str, context: CollaborationContext
    ) -> dict[str, object]: ...


@runtime_checkable
class AgentMemory(Protocol):
    """
    بروتوكول وكيل الذاكرة (Memory Agent).
    """

    async def capture_memory(
        self,
        context: CollaborationContext,
        *,
        label: str,
        payload: dict[str, object],
    ) -> dict[str, object]: ...


@runtime_checkable
class MissionReaderProtocol(Protocol):
    """
    بروتوكول قراءة المهمة (Mission Reader Protocol).

    واجهة ISP لعمليات القراءة فقط.
    SOLID: Interface Segregation Principle
    """

    async def get_mission(self, mission_id: int) -> Mission | None:
        """استرجاع المهمة بواسطة المعرف."""
        ...


@runtime_checkable
class MissionWriterProtocol(Protocol):
    """
    بروتوكول كتابة المهمة (Mission Writer Protocol).

    واجهة ISP لعمليات تحديث المهمة.
    SOLID: Interface Segregation Principle
    """

    async def update_mission_status(
        self, mission_id: int, status: MissionStatus, note: str | None = None
    ) -> None:
        """تحديث حالة المهمة."""
        ...

    async def log_event(
        self, mission_id: int, event_type: MissionEventType, payload: dict[str, object]
    ) -> None:
        """تسجيل حدث للمهمة."""
        ...

    async def rollback(self) -> None:
        """إلغاء التغييرات الحالية في قاعدة البيانات (Rollback)."""
        ...


@runtime_checkable
class TaskStateProtocol(Protocol):
    """
    بروتوكول حالة المهام الفرعية (Task State Protocol).

    واجهة ISP لإدارة حالة المهام الفرعية.
    SOLID: Interface Segregation Principle
    """

    async def mark_task_running(self, task_id: int) -> None:
        """تحديث حالة المهمة إلى قيد التشغيل."""
        ...

    async def mark_task_complete(
        self, task_id: int, result_text: str, meta: dict[str, object] | None = None
    ) -> None:
        """تحديث حالة المهمة إلى مكتملة."""
        ...

    async def mark_task_failed(self, task_id: int, error_text: str) -> None:
        """تحديث حالة المهمة إلى فاشلة."""
        ...


@runtime_checkable
class MissionMonitorProtocol(Protocol):
    """
    بروتوكول مراقبة المهمة (Mission Monitor Protocol).

    واجهة ISP لعمليات المراقبة.
    SOLID: Interface Segregation Principle
    """

    async def monitor_mission_events(
        self, mission_id: int, poll_interval: float = 1.0
    ) -> AsyncGenerator[MissionEvent, None]:
        """مراقبة أحداث المهمة."""
        ...


@runtime_checkable
class MissionStateManagerProtocol(
    MissionReaderProtocol,
    MissionWriterProtocol,
    TaskStateProtocol,
    MissionMonitorProtocol,
    Protocol,
):
    """
    بروتوكول مدير حالة المهمة الكامل (Full Mission State Manager Protocol).

    يجمع جميع واجهات إدارة المهمة للخدمات التي تحتاج الوصول الكامل.
    يحدد العمليات اللازمة لإدارة حالة المهمة دون الاعتماد على التطبيق المباشر.

    SOLID: Interface Segregation Principle - يمكن للمكونات استخدام
    الواجهات الأصغر (MissionReaderProtocol, TaskStateProtocol, إلخ)
    بدلاً من هذه الواجهة الكاملة.
    """

    ...


@runtime_checkable
class TaskExecutorProtocol(Protocol):
    """
    بروتوكول منفذ المهام (Task Executor Protocol).
    """

    async def execute_task(self, task: Task) -> dict[str, object]:
        """تنفيذ مهمة واحدة."""
        ...


@runtime_checkable
class AIClientProtocol(Protocol):
    """
    بروتوكول عميل الذكاء الاصطناعي (AI Client Protocol).
    """

    async def generate(self, prompt: str, **kwargs) -> str: ...

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]: ...


@runtime_checkable
class HealthCheckService(Protocol):
    """بروتوكول خدمة فحص الصحة."""

    async def check_health(self) -> dict[str, object]: ...


@runtime_checkable
class SystemService(Protocol):
    """بروتوكول خدمة النظام."""

    async def get_system_info(self) -> dict[str, object]: ...
