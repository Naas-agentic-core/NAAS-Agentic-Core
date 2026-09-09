"""
اختبارات التخزين المؤقت الموزع مع Pub/Sub.
"""

import asyncio
from unittest.mock import AsyncMock

import pytest

from app.caching.base import CacheBackend, PubSubBackend
from app.caching.distributed_cache import MultiLevelCache


@pytest.fixture
def l1_mock():
    return AsyncMock(spec=CacheBackend)


class MockRedisBackend(CacheBackend, PubSubBackend):
    pass


@pytest.fixture
def l2_mock():
    m = AsyncMock(spec=MockRedisBackend)
    m.pubsub.return_value = AsyncMock()  # Mock PubSub object
    return m


@pytest.fixture
def multi_cache(l1_mock, l2_mock):
    return MultiLevelCache(l1_mock, l2_mock, sync_l1=True)


@pytest.mark.asyncio
async def test_set_publishes_invalidation(multi_cache, l1_mock, l2_mock):
    """التحقق من أن set ينشر رسالة إبطال."""
    l2_mock.set.return_value = True

    await multi_cache.set("key", "val")

    # Verify publish called
    expected_msg = f"{multi_cache.node_id}:key"
    l2_mock.publish.assert_awaited_once_with("cache:invalidation", expected_msg)


@pytest.mark.asyncio
async def test_delete_publishes_invalidation(multi_cache, l1_mock, l2_mock):
    """التحقق من أن delete ينشر رسالة إبطال."""
    l2_mock.delete.return_value = True

    await multi_cache.delete("key")

    expected_msg = f"{multi_cache.node_id}:key"
    l2_mock.publish.assert_awaited_once_with("cache:invalidation", expected_msg)


@pytest.mark.asyncio
async def test_listener_processes_message(l1_mock, l2_mock):
    """التحقق من أن المستمع يحذف من L1 عند استلام رسالة من عقدة أخرى."""
    # Setup pubsub mock to yield one message then wait
    pubsub_mock = AsyncMock()
    l2_mock.pubsub.return_value = pubsub_mock

    # Mock listen iterator
    async def msg_gen():
        yield {"type": "message", "data": "other_node:key_to_delete"}
        # Stop iteration

    pubsub_mock.listen.side_effect = msg_gen

    cache = MultiLevelCache(l1_mock, l2_mock, node_id="my_node")

    # Wait briefly for the task to process
    await asyncio.sleep(0.01)

    l1_mock.delete.assert_awaited_with("key_to_delete")

    await cache.close()


@pytest.mark.asyncio
async def test_listener_ignores_own_message(l1_mock, l2_mock):
    """التحقق من أن المستمع يتجاهل الرسائل الصادرة من نفس العقدة."""
    pubsub_mock = AsyncMock()
    l2_mock.pubsub.return_value = pubsub_mock

    async def msg_gen():
        yield {"type": "message", "data": "my_node:key_to_delete"}

    pubsub_mock.listen.side_effect = msg_gen

    cache = MultiLevelCache(l1_mock, l2_mock, node_id="my_node")

    await asyncio.sleep(0.01)

    l1_mock.delete.assert_not_awaited()

    await cache.close()
