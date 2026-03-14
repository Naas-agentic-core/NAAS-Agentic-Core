import asyncio

import pytest

from app.core.event_bus import EventBus


@pytest.fixture
def bus():
    return EventBus()


@pytest.mark.asyncio
async def test_publish_subscribe_cycle(bus):
    queue = bus.subscribe_queue("test_channel")

    await bus.publish("test_channel", "hello")

    event = await queue.get()
    assert event == "hello"

    bus.unsubscribe_queue("test_channel", queue)
    assert not bus._subscribers.get("test_channel")


@pytest.mark.asyncio
async def test_multiple_subscribers(bus):
    q1 = bus.subscribe_queue("channel")
    q2 = bus.subscribe_queue("channel")

    await bus.publish("channel", "broadcast")

    e1 = await q1.get()
    e2 = await q2.get()

    assert e1 == "broadcast"
    assert e2 == "broadcast"


@pytest.mark.asyncio
async def test_async_generator_subscription(bus):
    # Run subscriber in background
    received = []

    async def subscriber():
        async for event in bus.subscribe("stream"):
            received.append(event)
            if len(received) == 2:
                break

    task = asyncio.create_task(subscriber())
    await asyncio.sleep(0.01)  # Yield

    await bus.publish("stream", 1)
    await bus.publish("stream", 2)

    await task
    assert received == [1, 2]


@pytest.mark.asyncio
async def test_subscriber_queue_is_bounded_and_drops_oldest(bus):
    queue = bus.subscribe_queue("bounded")

    for i in range(bus._max_pending_events + 5):
        await bus.publish("bounded", i)

    assert queue.qsize() == bus._max_pending_events
    first = await queue.get()
    assert first == 5
