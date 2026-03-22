"""
التخزين المؤقت الموزع متعدد المستويات (Distributed Multi-Level Caching).

يجمع هذا المكون بين سرعة الذاكرة المحلية (L1) وقدرة التخزين الموزع (L2 Redis)
لتحقيق أفضل أداء ممكن مع الحفاظ على الاتساق.

المعمارية:
- L1: In-Memory (سريع جداً، محلي لكل نسخة خدمة).
- L2: Redis (موزع، مشترك بين جميع النسخ).
- Pub/Sub: لإبطال L1 عند حدوث تغيير في L2 من خدمة أخرى.
"""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import logging
import uuid
from collections.abc import Awaitable, Callable

from app.caching.base import CacheBackend, PubSubBackend
from app.caching.stats import MultiLevelCacheCounters, MultiLevelCacheStatsSnapshot

logger = logging.getLogger(__name__)


class MultiLevelCache(CacheBackend):
    """
    منسق التخزين المؤقت متعدد الطبقات.
    """

    def __init__(
        self,
        l1_cache: CacheBackend,
        l2_cache: CacheBackend,
        sync_l1: bool = True,
        l1_backfill_ttl: int = 60,
        invalidation_channel: str = "cache:invalidation",
        node_id: str | None = None,
    ) -> None:
        """
        تهيئة المنسق.

        Args:
            l1_cache: المستوى الأول (Memory).
            l2_cache: المستوى الثاني (Redis).
            sync_l1: هل نقوم بملء L1 عند العثور على القيمة في L2؟
            l1_backfill_ttl: مدة صلاحية L1 عند التعبئة من L2 (بالثواني).
            invalidation_channel: اسم قناة Pub/Sub لإشعارات الإبطال.
            node_id: معرف فريد لهذه العقدة (لمنع معالجة إشعاراتها الخاصة).
        """
        self.l1 = l1_cache
        self.l2 = l2_cache
        self.sync_l1 = sync_l1
        self.l1_backfill_ttl = l1_backfill_ttl
        self.invalidation_channel = invalidation_channel
        self.node_id = node_id or str(uuid.uuid4())

        self._stats = MultiLevelCacheCounters()
        self._key_locks: dict[str, asyncio.Lock] = {}
        self._pubsub_task: asyncio.Task[None] | None = None

        # بدء الاستماع للإشعارات إذا كان L2 يدعم Pub/Sub
        if isinstance(self.l2, PubSubBackend):
            self._start_listener()

    def _get_key_lock(self, key: str) -> asyncio.Lock:
        """الحصول على قفل خاص بالمفتاح لتجميع الطلبات المتزامنة."""

        if key not in self._key_locks:
            self._key_locks[key] = asyncio.Lock()
        return self._key_locks[key]

    def _remove_key_lock(self, key: str) -> None:
        """إزالة القفل الخاص بمفتاح عند عدم الحاجة إليه."""

        self._key_locks.pop(key, None)

    def _start_listener(self) -> None:
        """بدء مهمة الخلفية للاستماع لإشعارات الإبطال."""
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            logger.warning("⚠️ No running event loop; skipping pub/sub listener startup.")
            return
        self._pubsub_task = loop.create_task(self._listen_for_invalidation())

    async def _listen_for_invalidation(self) -> None:
        """الاستماع لقناة الإبطال وحذف المفاتيح من L1."""
        if not isinstance(self.l2, PubSubBackend):
            return

        pubsub = self.l2.pubsub()
        await pubsub.subscribe(self.invalidation_channel)
        logger.info(
            f"📡 Started listening for invalidation on channel: {self.invalidation_channel}"
        )

        try:
            listen_stream = pubsub.listen()
            if inspect.isawaitable(listen_stream):
                listen_stream = await listen_stream
            async for message in listen_stream:
                if message["type"] != "message":
                    continue

                data = message["data"]
                # تنسيق الرسالة المتوقع: "source_node_id:key_to_invalidate"
                if isinstance(data, bytes):
                    data = data.decode("utf-8")

                try:
                    parts = data.split(":", 1)
                    if len(parts) != 2:
                        continue
                    source_node, key = parts

                    # تجاهل الإشعارات الصادرة من هذه العقدة نفسها
                    if source_node == self.node_id:
                        continue

                    logger.debug(f"🧹 Received invalidation for '{key}' from {source_node}")
                    await self.l1.delete(key)

                except Exception as e:
                    logger.error(f"❌ Error processing invalidation message: {e}")
        except asyncio.CancelledError:
            logger.info("🛑 Invalidation listener cancelled")
        except Exception as e:
            logger.error(f"❌ Invalidation listener failed: {e}")
        finally:
            await pubsub.unsubscribe(self.invalidation_channel)
            await pubsub.close()

    async def _publish_invalidation(self, key: str) -> None:
        """نشر إشعار إبطال."""
        if isinstance(self.l2, PubSubBackend):
            message = f"{self.node_id}:{key}"
            try:
                await self.l2.publish(self.invalidation_channel, message)
            except Exception as e:
                logger.warning(f"⚠️ Failed to publish invalidation for {key}: {e}")

    async def get(self, key: str) -> object | None:
        """
        استرجاع قيمة.

        الاستراتيجية:
        1. التحقق من L1.
        2. إذا لم توجد، التحقق من L2.
        3. إذا وجدت في L2، تحديث L1 (Read-Through).
        """
        # 1. Check L1
        try:
            val = await self.l1.get(key)
            if val is not None:
                logger.debug(f"🎯 Cache Hit L1: {key}")
                self._stats.record_l1_hit()
                return val
        except Exception as e:
            logger.warning(f"⚠️ L1 Cache get error for {key}: {e}")

        # 2. Check L2
        try:
            val = await self.l2.get(key)
            if val is not None:
                logger.debug(f"🎯 Cache Hit L2: {key}")
                self._stats.record_l2_hit()
                # 3. Populate L1 (Backfill)
                if self.sync_l1:
                    try:
                        # نستخدم TTL القابل للتكوين للـ L1 لتجنب البيانات القديمة
                        await self.l1.set(key, val, ttl=self.l1_backfill_ttl)
                    except Exception as e:
                        logger.warning(f"⚠️ Failed to populate L1 for {key}: {e}")
                return val
        except Exception as e:
            logger.warning(f"⚠️ L2 Cache get error for {key}: {e}")

        logger.debug(f"💨 Cache Miss: {key}")
        self._stats.record_miss()
        return None

    async def set(
        self,
        key: str,
        value: object,
        ttl: int | None = None,
    ) -> bool:
        """
        تخزين قيمة.

        الاستراتيجية:
        1. الكتابة في L2 أولاً (لضمان التوزيع).
        2. الكتابة في L1 (أو إبطالها).
        3. نشر إشعار إبطال لبقية العقد.
        """
        l2_success = False
        try:
            # Write to L2 (Source of Truth for distribution)
            l2_success = await self.l2.set(key, value, ttl=ttl)
        except Exception as e:
            logger.error(f"❌ L2 Cache set error for {key}: {e}")

        if l2_success:
            try:
                # Write to L1
                await self.l1.set(key, value, ttl=ttl)
            except Exception as e:
                logger.warning(f"⚠️ L1 Cache set error for {key}: {e}")

            self._stats.record_set()

            # إشعار بقية العقد بأن القيمة تغيرت
            await self._publish_invalidation(key)

            return True

        # If L2 fails, we generally consider the write failed for consistency
        return False

    async def delete(self, key: str) -> bool:
        """
        حذف قيمة.

        يحذف من كلا المستويين وينشر الإبطال.
        """
        l2_res = False
        try:
            l2_res = await self.l2.delete(key)
        except Exception as e:
            logger.error(f"❌ L2 Cache delete error for {key}: {e}")

        l1_res = False
        try:
            l1_res = await self.l1.delete(key)
        except Exception as e:
            logger.warning(f"⚠️ L1 Cache delete error for {key}: {e}")

        if l1_res or l2_res:
            self._stats.record_delete()
            self._remove_key_lock(key)
            # إشعار بقية العقد بالحذف
            await self._publish_invalidation(key)

        return l2_res or l1_res

    async def exists(self, key: str) -> bool:
        """التحقق من الوجود (في أي مستوى)."""
        try:
            if await self.l1.exists(key):
                return True
        except Exception as e:
            logger.warning(f"⚠️ L1 Cache exists error for {key}: {e}")

        try:
            return await self.l2.exists(key)
        except Exception as e:
            logger.warning(f"⚠️ L2 Cache exists error for {key}: {e}")

        return False

    async def clear(self) -> bool:
        """مسح الكل."""
        l1 = await self.l1.clear()
        l2 = await self.l2.clear()
        self._key_locks.clear()
        # ملاحظة: clear لا ينشر إبطالاً لكل مفتاح،
        # في بيئة الإنتاج يفضل تجنب clear الكاملة إلا للضرورة القصوى.
        return l1 and l2

    async def get_stats(self) -> MultiLevelCacheStatsSnapshot:
        """الحصول على إحصائيات الكاش متعدد المستويات."""

        return self._stats.snapshot()

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], object] | Callable[[], Awaitable[object]],
        ttl: int | None = None,
    ) -> object:
        """
        جلب أو حساب قيمة مع تجميع الطلبات لتجنب تدافع الكاش.
        """
        cached = await self.get(key)
        if cached is not None:
            return cached

        lock = self._get_key_lock(key)
        async with lock:
            cached = await self.get(key)
            if cached is not None:
                return cached

            result = factory()
            value = await result if inspect.isawaitable(result) else result
            await self.set(key, value, ttl=ttl)
            return value

    async def scan_keys(self, pattern: str) -> list[str]:
        """
        البحث عن المفاتيح.

        يعتمد بشكل أساسي على L2 لأنه يحتوي على المجموعة الشاملة.
        """
        try:
            return await self.l2.scan_keys(pattern)
        except Exception as e:
            logger.error(f"❌ L2 Cache scan error: {e}")
            return []

    async def set_add(self, key: str, members: list[str], ttl: int | None = None) -> bool:
        """
        إضافة عناصر إلى مجموعة.
        يتم التنفيذ في L2 فقط (باعتباره مصدر الحقيقة للمجموعات والعلامات).
        """
        try:
            return await self.l2.set_add(key, members, ttl=ttl)
        except Exception as e:
            logger.error(f"❌ L2 Cache set_add error: {e}")
            return False

    async def set_remove(self, key: str, members: list[str]) -> bool:
        """حذف عناصر من مجموعة في L2."""
        try:
            return await self.l2.set_remove(key, members)
        except Exception as e:
            logger.error(f"❌ L2 Cache set_remove error: {e}")
            return False

    async def set_members(self, key: str) -> set[str]:
        """جلب عناصر المجموعة من L2."""
        try:
            return await self.l2.set_members(key)
        except Exception as e:
            logger.error(f"❌ L2 Cache set_members error: {e}")
            return set()

    async def close(self) -> None:
        """إغلاق الموارد (مثل مستمع Pub/Sub)."""
        if self._pubsub_task:
            self._pubsub_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._pubsub_task
