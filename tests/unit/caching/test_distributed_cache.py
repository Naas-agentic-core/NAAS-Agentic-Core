"""
اختبارات التخزين المؤقت الموزع (MultiLevelCache).

تتضمن هذه الاختبارات سلوكيات الكاش متعدد المستويات، بما في ذلك
التزامن بين L1 و L2، نشر إشعارات الإبطال (Pub/Sub)، ومعالجة الأخطاء.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.caching.base import CacheBackend, PubSubBackend
from app.caching.distributed_cache import MultiLevelCache


class MockPubSubBackend(CacheBackend, PubSubBackend):
    pass


@pytest.fixture
def l1_mock() -> AsyncMock:
    return AsyncMock(spec=CacheBackend)


@pytest.fixture
def l2_mock() -> AsyncMock:
    return AsyncMock(spec=CacheBackend)


@pytest.fixture
def l2_pubsub_mock() -> AsyncMock:
    m = AsyncMock(spec=MockPubSubBackend)
    m.pubsub.return_value = AsyncMock()
    return m


@pytest.fixture
def multi_cache(l1_mock: AsyncMock, l2_mock: AsyncMock) -> MultiLevelCache:
    return MultiLevelCache(l1_mock, l2_mock, sync_l1=True)


@pytest.fixture
def multi_cache_pubsub(
    l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> MultiLevelCache:
    return MultiLevelCache(l1_mock, l2_pubsub_mock, sync_l1=True, node_id="test_node")


# --- Ported from test_distributed.py ---


@pytest.mark.asyncio
async def test_get_hit_l1(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """إذا وجد في L1، لا يذهب لـ L2."""
    l1_mock.get.return_value = "val_l1"

    val = await multi_cache.get("key")

    assert val == "val_l1"
    l1_mock.get.assert_awaited_once_with("key")
    l2_mock.get.assert_not_awaited()


@pytest.mark.asyncio
async def test_get_miss_l1_hit_l2(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """إذا لم يوجد في L1 ووجد في L2، يعيد القيمة ويملأ L1."""
    l1_mock.get.return_value = None
    l2_mock.get.return_value = "val_l2"

    val = await multi_cache.get("key")

    assert val == "val_l2"
    l1_mock.get.assert_awaited_once_with("key")
    l2_mock.get.assert_awaited_once_with("key")
    l1_mock.set.assert_awaited_once_with("key", "val_l2", ttl=60)


@pytest.mark.asyncio
async def test_set_propagates(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """التخزين يكتب في L2 ثم L1."""
    l2_mock.set.return_value = True

    res = await multi_cache.set("key", "val", ttl=100)

    assert res is True
    l2_mock.set.assert_awaited_once_with("key", "val", ttl=100)
    l1_mock.set.assert_awaited_once_with("key", "val", ttl=100)


# --- Ported from test_distributed_pubsub.py ---


@pytest.mark.asyncio
async def test_set_publishes_invalidation(
    multi_cache_pubsub: MultiLevelCache, l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> None:
    """التحقق من أن set ينشر رسالة إبطال."""
    l2_pubsub_mock.set.return_value = True

    await multi_cache_pubsub.set("key", "val")

    expected_msg = f"{multi_cache_pubsub.node_id}:key"
    l2_pubsub_mock.publish.assert_awaited_once_with("cache:invalidation", expected_msg)


@pytest.mark.asyncio
async def test_delete_publishes_invalidation(
    multi_cache_pubsub: MultiLevelCache, l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> None:
    """التحقق من أن delete ينشر رسالة إبطال."""
    l2_pubsub_mock.delete.return_value = True

    await multi_cache_pubsub.delete("key")

    expected_msg = f"{multi_cache_pubsub.node_id}:key"
    l2_pubsub_mock.publish.assert_awaited_once_with("cache:invalidation", expected_msg)


@pytest.mark.asyncio
async def test_listener_processes_message(
    l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> None:
    """التحقق من أن المستمع يحذف من L1 عند استلام رسالة من عقدة أخرى."""
    pubsub_mock = l2_pubsub_mock.pubsub.return_value

    async def msg_gen():
        yield {"type": "message", "data": "other_node:key_to_delete"}

    pubsub_mock.listen.side_effect = msg_gen

    cache = MultiLevelCache(l1_mock, l2_pubsub_mock, node_id="my_node")

    await asyncio.sleep(0.01)

    l1_mock.delete.assert_awaited_with("key_to_delete")

    await cache.close()


@pytest.mark.asyncio
async def test_listener_ignores_own_message(
    l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> None:
    """التحقق من أن المستمع يتجاهل الرسائل الصادرة من نفس العقدة."""
    pubsub_mock = l2_pubsub_mock.pubsub.return_value

    async def msg_gen():
        yield {"type": "message", "data": "my_node:key_to_delete"}

    pubsub_mock.listen.side_effect = msg_gen

    cache = MultiLevelCache(l1_mock, l2_pubsub_mock, node_id="my_node")

    await asyncio.sleep(0.01)

    l1_mock.delete.assert_not_awaited()

    await cache.close()


# --- New missing tests (Error handling, operations, etc) ---


@pytest.mark.asyncio
async def test_get_l1_error_falls_back_to_l2(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """في حال فشل L1، يجب أن يحاول الجلب من L2."""
    l1_mock.get.side_effect = Exception("L1 Error")
    l2_mock.get.return_value = "val_l2"

    val = await multi_cache.get("key")

    assert val == "val_l2"
    l2_mock.get.assert_awaited_once_with("key")
    l1_mock.set.assert_awaited_once_with("key", "val_l2", ttl=60)


@pytest.mark.asyncio
async def test_get_miss_all(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """إذا لم يوجد في أي منهما، يعيد None."""
    l1_mock.get.return_value = None
    l2_mock.get.return_value = None

    val = await multi_cache.get("key")

    assert val is None


@pytest.mark.asyncio
async def test_get_l2_error(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """في حال فشل L2 وعدم وجود في L1، يعيد None ويصطاد الخطأ."""
    l1_mock.get.return_value = None
    l2_mock.get.side_effect = Exception("L2 Error")

    val = await multi_cache.get("key")

    assert val is None


@pytest.mark.asyncio
async def test_set_l2_fails(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """إذا فشل التخزين في L2 (المصدر الأساسي)، يفشل التخزين كلياً."""
    l2_mock.set.side_effect = Exception("L2 Write Error")

    res = await multi_cache.set("key", "val")

    assert res is False
    l1_mock.set.assert_not_awaited()


@pytest.mark.asyncio
async def test_set_l1_fails_still_succeeds(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """إذا نجح التخزين في L2 وفشل في L1، تعتبر العملية ناجحة بشكل عام."""
    l2_mock.set.return_value = True
    l1_mock.set.side_effect = Exception("L1 Write Error")

    res = await multi_cache.set("key", "val")

    assert res is True
    l2_mock.set.assert_awaited_once_with("key", "val", ttl=None)


@pytest.mark.asyncio
async def test_delete_both_succeed(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """الحذف يمرر لكلا المستويين."""
    l2_mock.delete.return_value = True
    l1_mock.delete.return_value = True

    res = await multi_cache.delete("key")

    assert res is True
    l2_mock.delete.assert_awaited_once_with("key")
    l1_mock.delete.assert_awaited_once_with("key")


@pytest.mark.asyncio
async def test_delete_errors_handled(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """استثناءات الحذف يتم اصطيادها."""
    l2_mock.delete.side_effect = Exception("L2 Delete Error")
    l1_mock.delete.side_effect = Exception("L1 Delete Error")

    res = await multi_cache.delete("key")

    assert res is False


@pytest.mark.asyncio
async def test_exists_l1(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l1_mock.exists.return_value = True

    assert await multi_cache.exists("key") is True
    l2_mock.exists.assert_not_awaited()


@pytest.mark.asyncio
async def test_exists_l2(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l1_mock.exists.return_value = False
    l2_mock.exists.return_value = True

    assert await multi_cache.exists("key") is True


@pytest.mark.asyncio
async def test_exists_errors(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l1_mock.exists.side_effect = Exception("L1 err")
    l2_mock.exists.side_effect = Exception("L2 err")

    assert await multi_cache.exists("key") is False


@pytest.mark.asyncio
async def test_clear(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l1_mock.clear.return_value = True
    l2_mock.clear.return_value = True

    assert await multi_cache.clear() is True
    l1_mock.clear.assert_awaited_once()
    l2_mock.clear.assert_awaited_once()


@pytest.mark.asyncio
async def test_get_stats(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l1_mock.get.return_value = "val"
    await multi_cache.get("k1")
    l1_mock.get.return_value = None
    l2_mock.get.return_value = "val"
    await multi_cache.get("k2")
    l2_mock.get.return_value = None
    await multi_cache.get("k3")

    stats = await multi_cache.get_stats()
    assert stats.l1_hits == 1
    assert stats.l2_hits == 1
    assert stats.misses == 1
    assert stats.hit_ratio > 0.6


@pytest.mark.asyncio
async def test_get_or_set(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l1_mock.get.return_value = None
    l2_mock.get.return_value = None
    l2_mock.set.return_value = True

    factory = AsyncMock(return_value="computed")

    val = await multi_cache.get_or_set("key", factory, ttl=10)

    assert val == "computed"
    factory.assert_awaited_once()
    l2_mock.set.assert_awaited_once_with("key", "computed", ttl=10)


@pytest.mark.asyncio
async def test_get_or_set_already_cached(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l1_mock.get.return_value = "cached_val"
    factory = AsyncMock()

    val = await multi_cache.get_or_set("key", factory)

    assert val == "cached_val"
    factory.assert_not_awaited()


@pytest.mark.asyncio
async def test_scan_keys(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l2_mock.scan_keys.return_value = ["k1", "k2"]

    assert await multi_cache.scan_keys("k*") == ["k1", "k2"]

    l2_mock.scan_keys.side_effect = Exception("error")
    assert await multi_cache.scan_keys("k*") == []


@pytest.mark.asyncio
async def test_set_add(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l2_mock.set_add.return_value = True
    assert await multi_cache.set_add("group", ["m1", "m2"]) is True

    l2_mock.set_add.side_effect = Exception("err")
    assert await multi_cache.set_add("group", ["m1", "m2"]) is False


@pytest.mark.asyncio
async def test_set_remove(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l2_mock.set_remove.return_value = True
    assert await multi_cache.set_remove("group", ["m1"]) is True

    l2_mock.set_remove.side_effect = Exception("err")
    assert await multi_cache.set_remove("group", ["m1"]) is False


@pytest.mark.asyncio
async def test_set_members(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    l2_mock.set_members.return_value = {"m1", "m2"}
    assert await multi_cache.set_members("group") == {"m1", "m2"}

    l2_mock.set_members.side_effect = Exception("err")
    assert await multi_cache.set_members("group") == set()


# --- Extra Pub/Sub Listener Edge Cases & Cleanup ---


@pytest.mark.asyncio
async def test_listener_handles_malformed_messages(
    l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> None:
    pubsub_mock = l2_pubsub_mock.pubsub.return_value

    async def msg_gen():
        yield {"type": "subscribe", "data": 1}
        yield {"type": "message", "data": b"badformat"}
        yield {"type": "message", "data": "badformat2"}
        yield {"type": "message", "data": 123}

    pubsub_mock.listen.side_effect = msg_gen

    cache = MultiLevelCache(l1_mock, l2_pubsub_mock, node_id="my_node")
    await asyncio.sleep(0.01)

    l1_mock.delete.assert_not_awaited()
    await cache.close()


@pytest.mark.asyncio
async def test_publish_invalidation_fails(
    multi_cache_pubsub: MultiLevelCache, l2_pubsub_mock: AsyncMock
) -> None:
    """إذا فشل النشر، يجب التقاط الاستثناء بصمت."""
    l2_pubsub_mock.set.return_value = True
    l2_pubsub_mock.publish.side_effect = Exception("Publish Error")

    res = await multi_cache_pubsub.set("key", "val")
    assert res is True


@pytest.mark.asyncio
async def test_close_cancels_task(
    l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> None:
    pubsub_mock = l2_pubsub_mock.pubsub.return_value

    async def infinite_listen():
        await asyncio.sleep(10)
        yield {"type": "message", "data": "..."}

    pubsub_mock.listen.side_effect = infinite_listen

    cache = MultiLevelCache(l1_mock, l2_pubsub_mock)
    assert cache._pubsub_task is not None
    assert not cache._pubsub_task.done()

    await cache.close()

    assert cache._pubsub_task.cancelled()


@pytest.mark.asyncio
async def test_listener_exception_caught(
    l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> None:
    """إذا رمى pubsub_mock.listen استثناء، يجب التقاطه وإغلاق المورد."""
    pubsub_mock = l2_pubsub_mock.pubsub.return_value
    pubsub_mock.listen.side_effect = Exception("Listen crash")

    cache = MultiLevelCache(l1_mock, l2_pubsub_mock)
    await asyncio.sleep(0.01)

    assert cache._pubsub_task.done()
    pubsub_mock.unsubscribe.assert_awaited_once()
    pubsub_mock.close.assert_awaited_once()


def test_no_event_loop_skips_listener(
    l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> None:
    """إذا لم تكن هناك حلقة أحداث قيد التشغيل (مثلاً استدعاء متزامن)، يتم تجاهل إنشاء المستمع."""
    import unittest.mock

    with unittest.mock.patch(
        "asyncio.get_running_loop", side_effect=RuntimeError("no loop")
    ):
        cache = MultiLevelCache(l1_mock, l2_pubsub_mock)
        assert cache._pubsub_task is None


# --- Extra coverage for the remaining 3% ---


@pytest.mark.asyncio
async def test_listen_for_invalidation_not_pubsub(
    l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """إذا كان l2 لا يدعم PubSubBackend يتم تجاهل المستمع."""
    cache = MultiLevelCache(l1_mock, l2_mock)
    await cache._listen_for_invalidation()
    assert True


@pytest.mark.asyncio
async def test_get_l2_hit_l1_set_fails(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """عند نجاح L2 وفشل ملء L1 بالبيانات، يجب التقاط الخطأ وإرجاع القيمة بشكل طبيعي."""
    l1_mock.get.return_value = None
    l2_mock.get.return_value = "val"
    l1_mock.set.side_effect = Exception("L1 Set Backfill Error")

    val = await multi_cache.get("key")
    assert val == "val"


@pytest.mark.asyncio
async def test_get_or_set_cached_inside_lock(
    multi_cache: MultiLevelCache, l1_mock: AsyncMock, l2_mock: AsyncMock
) -> None:
    """عند التنافس على نفس المفتاح، بعد الحصول على القفل إذا وجدنا القيمة نرجعها دون حسابها."""
    l1_mock.get.side_effect = [None, "val"]
    l2_mock.get.return_value = None

    factory = AsyncMock()
    val = await multi_cache.get_or_set("key", factory)

    assert val == "val"
    factory.assert_not_awaited()


@pytest.mark.asyncio
async def test_listener_cancelled_error(
    l1_mock: AsyncMock, l2_pubsub_mock: AsyncMock
) -> None:
    """اختبار التقاط CancelledError بشكل صحيح في الـ listener"""
    pubsub_mock = l2_pubsub_mock.pubsub.return_value
    pubsub_mock.listen.side_effect = asyncio.CancelledError()

    cache = MultiLevelCache(l1_mock, l2_pubsub_mock)
    await asyncio.sleep(0.01)

    assert cache._pubsub_task.done()
    pubsub_mock.unsubscribe.assert_awaited_once()
