"""
تنفيذ التخزين المؤقت في الذاكرة (In-Memory Cache).

يستخدم هذا التنفيذ قاموس Python بسيط مع دعم لانتهاء الصلاحية (TTL)
والحجم الأقصى (Max Size) باستخدام خوارزمية LRU (Least Recently Used) مبسطة.

المبادئ:
- البساطة: استخدام أدوات اللغة الأساسية.
- الكفاءة: عمليات O(1) في معظم الحالات.
- الأمان: استخدام AsyncIO Lock لضمان سلامة البيانات في البيئة غير المتزامنة.
"""

from __future__ import annotations

import asyncio
import fnmatch
import inspect
import random
import time
from collections import OrderedDict
from collections.abc import Awaitable, Callable

from app.caching.base import CacheBackend
from app.caching.stats import CacheCounters, CacheStatsSnapshot


class InMemoryCache(CacheBackend):
    """
    تخزين مؤقت في الذاكرة المحلية.

    المميزات:
    - سريع جداً (بدون شبكة).
    - يدعم TTL (مدة الصلاحية).
    - يدعم الحد الأقصى للعناصر (LRU Eviction).
    - آمن للتزامن (Thread-safe via asyncio.Lock).
    """

    def __init__(
        self,
        max_size: int = 1000,
        default_ttl: int = 300,
        ttl_jitter_ratio: float = 0.0,
    ) -> None:
        """
        تهيئة الذاكرة المؤقتة.

        Args:
            max_size: الحد الأقصى لعدد العناصر.
            default_ttl: مدة الصلاحية الافتراضية بالثواني.
            ttl_jitter_ratio: نسبة العشوائية المضافة لـ TTL لتقليل التدافع.
        """
        if not 0.0 <= ttl_jitter_ratio <= 1.0:
            raise ValueError("ttl_jitter_ratio يجب أن يكون بين 0.0 و 1.0")

        self._cache: OrderedDict[str, tuple[object, float]] = OrderedDict()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._ttl_jitter_ratio = ttl_jitter_ratio
        self._stats = CacheCounters()
        self._lock = asyncio.Lock()
        self._key_locks: dict[str, asyncio.Lock] = {}

    def _resolve_ttl(self, ttl: int | None) -> int:
        """تحديد TTL فعلي مع إضافة عشوائية اختيارية."""

        ttl_val = ttl if ttl is not None else self._default_ttl
        if ttl_val <= 0:
            return 0
        if self._ttl_jitter_ratio == 0.0:
            return ttl_val
        jitter = int(ttl_val * self._ttl_jitter_ratio * random.random())
        return ttl_val + jitter

    def _get_key_lock(self, key: str) -> asyncio.Lock:
        """الحصول على قفل خاص بالمفتاح لتجميع الطلبات المتزامنة."""

        if key not in self._key_locks:
            self._key_locks[key] = asyncio.Lock()
        return self._key_locks[key]

    def _remove_key_lock(self, key: str) -> None:
        """إزالة القفل الخاص بمفتاح عند عدم الحاجة إليه."""

        self._key_locks.pop(key, None)

    async def get(self, key: str) -> object | None:
        """
        استرجاع قيمة.

        يتحقق من انتهاء الصلاحية ويحدث ترتيب LRU.
        """
        async with self._lock:
            if key not in self._cache:
                self._stats.record_miss()
                return None

            value, expire_at = self._cache[key]

            # التحقق من انتهاء الصلاحية
            if time.time() > expire_at:
                del self._cache[key]
                self._remove_key_lock(key)
                self._stats.record_miss()
                return None

            # تحديث ترتيب LRU (نقل للنهاية)
            self._cache.move_to_end(key)
            self._stats.record_hit()
            return value

    async def set(
        self,
        key: str,
        value: object,
        ttl: int | None = None,
    ) -> bool:
        """
        تخزين قيمة.

        يطبق سياسة الطرد (Eviction) إذا امتلأت الذاكرة.
        """
        ttl_val = self._resolve_ttl(ttl)
        if ttl_val <= 0:
            await self.delete(key)
            return True
        expire_at = time.time() + ttl_val

        async with self._lock:
            # إذا كان المفتاح موجوداً، نقوم بتحديثه ونقله للنهاية
            if key in self._cache:
                self._cache.move_to_end(key)

            self._cache[key] = (value, expire_at)

            # تطبيق سياسة الحجم الأقصى (LRU Eviction)
            if len(self._cache) > self._max_size:
                # حذف أقدم عنصر (الأول)
                evicted_key, _ = self._cache.popitem(last=False)
                self._remove_key_lock(evicted_key)
                self._stats.record_eviction()

            self._stats.record_set()
            return True

    async def delete(self, key: str) -> bool:
        """حذف عنصر."""
        async with self._lock:
            if key in self._cache:
                del self._cache[key]
                self._stats.record_delete()
                self._remove_key_lock(key)
                return True
            return False

    async def exists(self, key: str) -> bool:
        """التحقق من الوجود مع مراعاة الصلاحية."""
        async with self._lock:
            if key not in self._cache:
                return False

            _, expire_at = self._cache[key]
            if time.time() > expire_at:
                del self._cache[key]
                self._remove_key_lock(key)
                return False

            return True

    async def clear(self) -> bool:
        """مسح الكل."""
        async with self._lock:
            self._cache.clear()
            self._key_locks.clear()
            return True

    async def get_stats(self) -> CacheStatsSnapshot:
        """الحصول على لقطة إحصائية للكاش."""

        async with self._lock:
            return self._stats.snapshot(
                cache_type="memory",
                size=len(self._cache),
                max_size=self._max_size,
            )

    async def get_or_set(
        self,
        key: str,
        factory: Callable[[], object] | Callable[[], Awaitable[object]],
        ttl: int | None = None,
    ) -> object:
        """
        جلب القيمة من الكاش أو حسابها مع تجميع الطلبات (Request Coalescing).

        يتجنب تدافع الكاش عبر قفل خاص بالمفتاح ثم تحديث الكاش مرة واحدة.
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
        البحث عن مفاتيح تطابق نمطاً معيناً.

        Args:
            pattern: نمط البحث (e.g., "user:*"). يدعم fnmatch.

        Returns:
            list[str]: قائمة المفاتيح المطابقة الصالحة.
        """
        async with self._lock:
            keys = []
            to_delete = []
            now = time.time()
            # نتجنب نسخ القاموس بأكمله باستخدام حلقة تمريرتين
            # لتجنب مشكلة تغيير حجم القاموس أثناء التكرار
            for key, (_, expire_at) in self._cache.items():
                if now > expire_at:
                    to_delete.append(key)
                    continue

                if fnmatch.fnmatch(key, pattern):
                    keys.append(key)

            # تنظيف الكسول (Lazy cleanup) للعناصر المنتهية
            for key in to_delete:
                del self._cache[key]
                self._remove_key_lock(key)

            return keys

    async def set_add(self, key: str, members: list[str], ttl: int | None = None) -> bool:
        """إضافة عناصر إلى مجموعة (Internal Set)."""
        ttl_val = self._resolve_ttl(ttl)
        expire_at = time.time() + ttl_val if ttl_val > 0 else float("inf")

        async with self._lock:
            # إذا كان المفتاح موجوداً ولكنه ليس مجموعة، نقوم بالكتابة فوقه
            if key in self._cache:
                current_val, _ = self._cache[key]
                if not isinstance(current_val, set):
                    # Overwrite
                    val_set = set(members)
                    self._cache[key] = (val_set, expire_at)
                    return True
                # Update existing set
                current_val.update(members)
                # Update Expiry? Usually yes on write.
                if ttl_val > 0:
                    self._cache[key] = (current_val, expire_at)
                return True
            # Create new set
            val_set = set(members)
            self._cache[key] = (val_set, expire_at)
            self._stats.record_set()
            return True

    async def set_remove(self, key: str, members: list[str]) -> bool:
        """حذف عناصر من مجموعة."""
        async with self._lock:
            if key in self._cache:
                current_val, _expire_at = self._cache[key]
                if isinstance(current_val, set):
                    current_val.difference_update(members)
                    # إذا أصبحت المجموعة فارغة، هل نحذف المفتاح؟
                    # Redis يبقي المفتاح فارغاً (أحياناً) أو يحذفه. SREM يحذف المفتاح إذا فرغ.
                    if not current_val:
                        del self._cache[key]
                        self._remove_key_lock(key)
                return True
            return False

    async def set_members(self, key: str) -> set[str]:
        """الحصول على عناصر المجموعة."""
        async with self._lock:
            if key not in self._cache:
                return set()

            current_val, expire_at = self._cache[key]
            if time.time() > expire_at:
                del self._cache[key]
                self._remove_key_lock(key)
                return set()

            if isinstance(current_val, set):
                return current_val.copy()  # Return copy to be safe
            return set()
