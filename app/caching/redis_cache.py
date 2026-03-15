"""
تنفيذ التخزين المؤقت باستخدام Redis (Redis Cache).

يستخدم مكتبة redis-py (asyncio) لتوفير تخزين مؤقت موزع وعالي الأداء.
مناسب للبيئات الموزعة حيث تشترك عدة خدمات في نفس حالة التخزين المؤقت.
يتضمن حماية Circuit Breaker لضمان عدم تعطل النظام عند فشل Redis.

المتطلبات:
- خادم Redis يعمل.
- مكتبة redis-py مثبتة.
"""

from __future__ import annotations

import hashlib
import json
import logging
import random

import redis.asyncio as redis
from app.caching.base import CacheBackend
from app.caching.stats import CacheCounters, CacheStatsSnapshot
from app.core.resilience.circuit_breaker import (
    CircuitBreakerConfig,
    get_circuit_breaker,
)

logger = logging.getLogger(__name__)


class RedisCache(CacheBackend):
    """
    تخزين مؤقت باستخدام Redis مع حماية Circuit Breaker.

    المميزات:
    - موزع (مشترك بين الخدمات).
    - دائم (اختياري).
    - محمي بـ Circuit Breaker لتجنب التأخير عند فشل الاتصال.
    """

    def __init__(
        self,
        redis_url: str,
        default_ttl: int = 300,
        ttl_jitter_ratio: float = 0.0,
        breaker_config: CircuitBreakerConfig | None = None,
        socket_timeout: float | None = None,
        socket_connect_timeout: float | None = None,
        health_check_interval: int | None = None,
    ) -> None:
        """
        تهيئة عميل Redis.

        Args:
            redis_url: رابط الاتصال بـ Redis (e.g., redis://localhost:6379/0)
            default_ttl: مدة الصلاحية الافتراضية بالثواني.
            ttl_jitter_ratio: نسبة عشوائية مضافة إلى TTL لتقليل التدافع.
            breaker_config: إعدادات قاطع الدائرة (اختياري).
            socket_timeout: مهلة القراءة/الكتابة للمقبس (اختياري).
            socket_connect_timeout: مهلة اتصال المقبس (اختياري).
            health_check_interval: فترة فحص الصحة للاتصال (اختياري).
        """
        self._redis = redis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=socket_timeout,
            socket_connect_timeout=socket_connect_timeout,
            health_check_interval=health_check_interval,
        )
        if not 0.0 <= ttl_jitter_ratio <= 1.0:
            raise ValueError("ttl_jitter_ratio يجب أن يكون بين 0.0 و 1.0")

        self._default_ttl = default_ttl
        self._ttl_jitter_ratio = ttl_jitter_ratio
        self._stats = CacheCounters()

        # إعداد قاطع الدائرة
        config = breaker_config or CircuitBreakerConfig(
            failure_threshold=5, timeout=30.0, success_threshold=2
        )
        # استخدام MD5 لضمان ثبات الاسم عبر التشغيلات المختلفة
        url_hash = hashlib.md5(redis_url.encode()).hexdigest()
        self._breaker = get_circuit_breaker(f"redis_cache_breaker_{url_hash}", config)

        logger.info(f"✅ Redis Cache initialized with URL: {redis_url}")

    def _resolve_ttl(self, ttl: int | None) -> int:
        """تحديد TTL فعلي مع عشوائية اختيارية لتفادي انتهاء متزامن."""

        ttl_val = ttl if ttl is not None else self._default_ttl
        if ttl_val <= 0:
            return 0
        if self._ttl_jitter_ratio == 0.0:
            return ttl_val
        jitter = int(ttl_val * self._ttl_jitter_ratio * random.random())
        return ttl_val + jitter

    async def _execute_with_breaker(
        self, operation_name: str, func: object, *args: object, **kwargs: object
    ) -> object | None:
        """
        تنفيذ عملية Redis داخل قاطع الدائرة.
        """
        if not self._breaker.allow_request():
            logger.warning(f"⚠️ Redis Circuit Breaker is OPEN. Skipping {operation_name}.")
            return None

        try:
            result = await func(*args, **kwargs)
            self._breaker.record_success()
            return result
        except Exception as e:
            self._breaker.record_failure()
            logger.error(f"❌ Redis {operation_name} error: {e}")
            return None

    async def get(self, key: str) -> object | None:
        """
        استرجاع قيمة.
        """

        # دالة مساعدة لتغليف الاستدعاء
        async def _do_get() -> object:
            value = await self._redis.get(key)
            if value is None:
                return None
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value

        result = await self._execute_with_breaker("get", _do_get)
        if result is None:
            self._stats.record_miss()
        else:
            self._stats.record_hit()
        return result

    async def set(
        self,
        key: str,
        value: object,
        ttl: int | None = None,
    ) -> bool:
        """
        تخزين قيمة.
        """
        ttl_val = self._resolve_ttl(ttl)
        if ttl_val <= 0:
            await self.delete(key)
            return True

        async def _do_set() -> bool:
            try:
                serialized_value = json.dumps(value)
            except (TypeError, ValueError):
                serialized_value = str(value)

            await self._redis.set(key, serialized_value, ex=ttl_val)
            return True

        result = await self._execute_with_breaker("set", _do_set)
        if result is True:
            self._stats.record_set()
        return result is True

    async def delete(self, key: str) -> bool:
        """حذف عنصر."""

        async def _do_delete() -> bool:
            await self._redis.delete(key)
            return True

        result = await self._execute_with_breaker("delete", _do_delete)
        if result is True:
            self._stats.record_delete()
        return result is True

    async def exists(self, key: str) -> bool:
        """التحقق من الوجود."""

        async def _do_exists() -> bool:
            return await self._redis.exists(key) > 0

        result = await self._execute_with_breaker("exists", _do_exists)
        return result is True

    async def clear(self) -> bool:
        """مسح قاعدة البيانات الحالية."""

        async def _do_clear() -> bool:
            await self._redis.flushdb()
            return True

        result = await self._execute_with_breaker("clear", _do_clear)
        return result is True

    async def scan_keys(self, pattern: str) -> list[str]:
        """
        البحث عن مفاتيح.
        """

        async def _do_scan() -> list[str]:
            keys: list[str] = []
            async for key in self._redis.scan_iter(match=pattern):
                keys.append(key)
            return keys

        result = await self._execute_with_breaker("scan", _do_scan)
        return result if result is not None else []

    async def set_add(self, key: str, members: list[str], ttl: int | None = None) -> bool:
        """إضافة عناصر إلى مجموعة Redis."""
        if not members:
            return True

        ttl_val = self._resolve_ttl(ttl)

        async def _do_sadd() -> bool:
            pipe = self._redis.pipeline()
            pipe.sadd(key, *members)
            if ttl_val > 0:
                pipe.expire(key, ttl_val)
            await pipe.execute()
            return True

        result = await self._execute_with_breaker("set_add", _do_sadd)
        return result is True

    async def set_remove(self, key: str, members: list[str]) -> bool:
        """حذف عناصر من مجموعة Redis."""
        if not members:
            return True

        async def _do_srem() -> bool:
            await self._redis.srem(key, *members)
            return True

        result = await self._execute_with_breaker("set_remove", _do_srem)
        return result is True

    async def set_members(self, key: str) -> set[str]:
        """الحصول على عناصر مجموعة Redis."""

        async def _do_smembers() -> set[str]:
            return await self._redis.smembers(key)

        result = await self._execute_with_breaker("set_members", _do_smembers)
        return result if result is not None else set()

    async def publish(self, channel: str, message: str) -> int:
        """
        نشر رسالة إلى قناة (Pub/Sub).
        """

        async def _do_publish() -> int:
            return await self._redis.publish(channel, message)

        result = await self._execute_with_breaker("publish", _do_publish)
        return result if result is not None else 0

    def pubsub(self) -> object:
        """
        الحصول على كائن PubSub.
        ملاحظة: لا يخضع لقاطع الدائرة لأنه يتطلب اتصالاً مستمراً.
        """
        return self._redis.pubsub()

    async def get_stats(self) -> CacheStatsSnapshot:
        """الحصول على لقطة إحصائية (الحجم غير متاح في Redis)."""

        return self._stats.snapshot(
            cache_type="redis",
            size=-1,
            max_size=-1,
        )

    async def close(self) -> None:
        """إغلاق الاتصال."""
        await self._redis.close()
