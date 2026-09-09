"""
اختبارات التخزين المؤقت الموزع.
"""

from unittest.mock import AsyncMock

import pytest

from app.caching.base import CacheBackend
from app.caching.distributed_cache import MultiLevelCache


@pytest.fixture
def l1_mock():
    return AsyncMock(spec=CacheBackend)


@pytest.fixture
def l2_mock():
    return AsyncMock(spec=CacheBackend)


@pytest.fixture
def multi_cache(l1_mock, l2_mock):
    return MultiLevelCache(l1_mock, l2_mock, sync_l1=True)


@pytest.mark.asyncio
async def test_get_hit_l1(multi_cache, l1_mock, l2_mock):
    """إذا وجد في L1، لا يذهب لـ L2."""
    l1_mock.get.return_value = "val_l1"

    val = await multi_cache.get("key")

    assert val == "val_l1"
    l1_mock.get.assert_awaited_once_with("key")
    l2_mock.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_miss_l1_hit_l2(multi_cache, l1_mock, l2_mock):
    """إذا لم يوجد في L1 ووجد في L2، يعيد القيمة ويملأ L1."""
    l1_mock.get.return_value = None
    l2_mock.get.return_value = "val_l2"

    val = await multi_cache.get("key")

    assert val == "val_l2"
    l1_mock.get.assert_awaited_once_with("key")
    l2_mock.get.assert_awaited_once_with("key")

    # Verify Backfill
    l1_mock.set.assert_awaited_once_with("key", "val_l2", ttl=60)


@pytest.mark.asyncio
async def test_set_propagates(multi_cache, l1_mock, l2_mock):
    """التخزين يكتب في L2 ثم L1."""
    l2_mock.set.return_value = True

    res = await multi_cache.set("key", "val", ttl=100)

    assert res is True
    l2_mock.set.assert_awaited_once_with("key", "val", ttl=100)
    l1_mock.set.assert_awaited_once_with("key", "val", ttl=100)
