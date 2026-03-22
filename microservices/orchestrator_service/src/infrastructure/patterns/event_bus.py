"""حافلة أحداث مصغرة تدعم النشر والاشتراك بأسلوب آمن وقابل للتتبع."""

import logging
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass
class Event:
    """نموذج حدث أساسي يتضمن هوية ونوع وبيانات وصفية."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    event_type: str = ""
    data: dict[str, object] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: dict[str, object] = field(default_factory=dict)


class EventBus:
    """قناة نشر/اشتراك خفيفة مع سجل أحداث اختياري."""

    def __init__(self):
        self._subscribers: dict[str, list[Callable[[Event], object]]] = defaultdict(list)
        self._async_subscribers: dict[str, list[Callable[[Event], object]]] = defaultdict(list)
        self._event_history: list[Event] = []
        self._max_history = 1000

    def subscribe(self, event_type: str, handler: Callable[[Event], object]) -> None:
        """يسجل معالجًا تزامنيًا لنوع حدث محدد."""
        self._subscribers[event_type].append(handler)
        logger.debug("Subscribed handler to %s", event_type)

    def unsubscribe(self, event_type: str, handler: Callable[[Event], object]) -> None:
        """يلغي اشتراك معالج معين لنوع حدث."""
        if handler in self._subscribers[event_type]:
            self._subscribers[event_type].remove(handler)
        if handler in self._async_subscribers[event_type]:
            self._async_subscribers[event_type].remove(handler)

    def publish(self, event: Event) -> None:
        """يبث الحدث لجميع المشتركين مع حماية من أعطال المعالجات."""
        self._add_to_history(event)

        # تحسين الكفاءة عبر تقليل استدعاءات القواميس وتجنب الحلقات الفارغة
        # Optimized by reducing dict lookups and avoiding empty loops

        subscribers = self._subscribers

        # Specific handlers
        if specific_handlers := subscribers.get(event.event_type):
            for handler in specific_handlers:
                try:
                    handler(event)
                except Exception as exc:  # pragma: no cover - دفاعي
                    logger.error("Error in event handler: %s", exc)

        # Wildcard handlers
        if wildcard_handlers := subscribers.get("*"):
            for handler in wildcard_handlers:
                try:
                    handler(event)
                except Exception as exc:  # pragma: no cover - دفاعي
                    logger.error("Error in wildcard handler: %s", exc)

    async def _safe_async_call(self, handler: Callable[[Event], object], event: Event) -> None:
        """يستدعي معالجًا غير متزامنًا بأمان مع تسجيل الأخطاء."""
        try:
            await handler(event)
        except Exception as exc:  # pragma: no cover - دفاعي
            logger.error("Error in async event handler: %s", exc)

    def _add_to_history(self, event: Event) -> None:
        """يضيف الحدث إلى السجل مع الحفاظ على الحد الأقصى."""
        self._event_history.append(event)
        if len(self._event_history) > self._max_history:
            self._event_history = self._event_history[-self._max_history :]

    def get_history(self, event_type: str | None = None, limit: int = 100) -> list[Event]:
        """يعيد قائمة بأحدث الأحداث مع إمكانية التصفية بنوع معين."""
        if event_type:
            events = [event for event in self._event_history if event.event_type == event_type]
        else:
            events = self._event_history
        return events[-limit:]


def get_event_bus() -> EventBus:
    """يعيد نسخة الحافلة العالمية للاستخدام عبر النظام."""
    return _global_event_bus


_global_event_bus = EventBus()
