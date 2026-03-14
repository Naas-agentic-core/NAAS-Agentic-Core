# app/core/event_bus.py
"""
ناقل الأحداث (Event Bus) - العمود الفقري للسرعة الفائقة
-------------------------------------------------------
يوفر هذا النظام آلية نشر واشتراك (Pub/Sub) داخل الذاكرة لتحقيق زمن استجابة منخفض جداً (Low Latency).
تطبيقاً لنظرية PACELC (في الحالة الطبيعية Else اختر Latency)، نستخدم هذا الناقل
لبث أحداث المهمة مباشرة للمستمعين دون انتظار التزام قاعدة البيانات (Database Commit).

المميزات:
- AsyncIO Queues: استخدام طوابير غير متزامنة لعدم حجب التنفيذ.
- Type Safety: تعامل صارم مع الأنواع.
- Gap-Free Streaming: دعم الاشتراك المسبق لتجنب فقدان الأحداث (Race Conditions).
"""

import asyncio
from collections.abc import AsyncGenerator

from app.core.di import get_logger
from app.core.protocols import EventBusProtocol

logger = get_logger(__name__)

type EventPayload = object
MAX_PENDING_EVENTS_PER_SUBSCRIBER = 1000


class EventBus(EventBusProtocol):
    """
    ناقل أحداث غير متزامن يربط بين المنتجين (Producers) والمستهلكين (Consumers)
    داخل نفس العملية (Process) لتحقيق سرعة استجابة آنية.
    """

    def __init__(self) -> None:
        """يهيئ الناقل مع سجل اشتراكات فارغ."""
        self._subscribers: dict[str, set[asyncio.Queue[EventPayload]]] = {}
        self._max_pending_events = MAX_PENDING_EVENTS_PER_SUBSCRIBER

    async def publish(self, channel: str, event: EventPayload) -> None:
        """
        نشر حدث جديد في قناة معينة.
        يتم توزيع الحدث على جميع المشتركين الحاليين فوراً.

        Args:
            channel: اسم القناة (مثل mission_id).
            event: الحدث المراد نشره.
        """
        queues = self._subscribers.get(channel)
        if not queues:
            return
        # نستخدم list() لإنشاء نسخة لتجنب أخطاء التعديل أثناء الدوران
        for queue in list(queues):
            try:
                if queue.full():
                    try:
                        queue.get_nowait()
                    except asyncio.QueueEmpty:
                        pass
                queue.put_nowait(event)
            except Exception as exc:
                logger.error(f"Failed to push to queue in channel {channel}: {exc}")

    def subscribe_queue(self, channel: str) -> asyncio.Queue[EventPayload]:
        """
        إنشاء صف اشتراك للقناة يدوياً.
        مفيد للحالات التي تتطلب ضمان عدم فقدان البيانات قبل بدء التكرار (Start Iteration).

        Args:
            channel: اسم القناة.

        Returns:
            asyncio.Queue: صف الأحداث الجديد.
        """
        queue: asyncio.Queue[EventPayload] = asyncio.Queue(maxsize=self._max_pending_events)
        if channel not in self._subscribers:
            self._subscribers[channel] = set()
        self._subscribers[channel].add(queue)
        logger.debug(f"New queue subscriber joined channel: {channel}")
        return queue

    def unsubscribe_queue(self, channel: str, queue: asyncio.Queue[EventPayload]) -> None:
        """
        إلغاء اشتراك صف يدوياً.

        Args:
            channel: اسم القناة.
            queue: الصف المراد إزالته.
        """
        if channel in self._subscribers:
            self._subscribers[channel].discard(queue)
            if not self._subscribers[channel]:
                del self._subscribers[channel]
            logger.debug(f"Queue subscriber left channel: {channel}")

    async def subscribe(self, channel: str) -> AsyncGenerator[EventPayload, None]:
        """
        الاشتراك في قناة واستقبال الأحداث كتدفق (Stream).
        ملاحظة: إذا كنت بحاجة لضمان عدم وجود فجوة زمنية (Race Condition) مع قاعدة البيانات،
        استخدم `subscribe_queue` يدوياً بدلاً من هذا المولد.

        Args:
            channel: اسم القناة المراد الاستماع إليها.

        Yields:
            EventPayload: الأحداث المتدفقة.
        """
        queue = self.subscribe_queue(channel)
        try:
            while True:
                # انتظار الحدث التالي
                event = await queue.get()
                yield event
        finally:
            self.unsubscribe_queue(channel, queue)


_global_event_bus: EventBus | None = None


def get_event_bus() -> EventBus:
    """
    يوفر مثيلاً واحداً لناقل الأحداث مع السماح بالحقن في الاختبارات.

    Returns:
        EventBus: ناقل الأحداث.
    """
    global _global_event_bus
    if _global_event_bus is None:
        _global_event_bus = EventBus()
    return _global_event_bus
