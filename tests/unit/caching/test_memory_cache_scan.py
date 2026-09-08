import time

import pytest

from app.caching.memory_cache import InMemoryCache


@pytest.mark.asyncio
async def test_scan_keys_regression_and_cleanup():
    cache = InMemoryCache(default_ttl=10)

    await cache.set("user:1:a", "v1")
    await cache.set("user:1:b", "v2")
    await cache.set("user:2:c", "v3")
    await cache.set("system:config", "v4")

    # Manually expire "user:2:c" and "system:config" to test cleanup during scan
    cache._cache["user:2:c"] = ("v3", time.time() - 10)
    cache._cache["system:config"] = ("v4", time.time() - 10)

    # Ensure they have associated locks to verify _remove_key_lock is called
    cache._get_key_lock("user:2:c")
    cache._get_key_lock("system:config")

    # 1. Matching non-expired keys are returned ("user:1:a", "user:1:b")
    # 2. Non-matching keys are excluded (even if non-expired)
    # 3. Expired keys are removed, and _remove_key_lock is called
    keys = await cache.scan_keys("user:*")

    assert sorted(keys) == ["user:1:a", "user:1:b"], "Should return only non-expired, matching keys"

    # Assert expired keys were removed
    assert "user:2:c" not in cache._cache
    assert "system:config" not in cache._cache

    # Assert locks were cleaned up for expired keys
    assert "user:2:c" not in cache._key_locks
    assert "system:config" not in cache._key_locks

    # Test empty cache behavior
    await cache.clear()
    assert len(cache._cache) == 0
    assert len(cache._key_locks) == 0

    empty_keys = await cache.scan_keys("user:*")
    assert empty_keys == [], "Should handle empty cache correctly"
