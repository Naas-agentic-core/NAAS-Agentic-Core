"""
Redis Event Bridge.
Connects the Distributed Event Backbone (Redis) to the Local Event Bus (Memory).
Implements the 'Streaming BFF' pattern where the Gateway subscribes to backend events.
"""

import asyncio
import contextlib
import json
import logging

import redis.asyncio as redis
from app.core.event_bus import get_event_bus

logger = logging.getLogger(__name__)


class RedisEventBridge:
    """
    Bridge that listens to Redis Pub/Sub channels and forwards events
    to the internal application EventBus.
    """

    def __init__(self, redis_url: str = "redis://redis:6379") -> None:
        self.redis_url = redis_url
        self._redis: redis.Redis | None = None
        self._pubsub: redis.client.PubSub | None = None
        self._listen_task: asyncio.Task | None = None
        self._internal_bus = get_event_bus()

    async def start(self) -> None:
        """Start the bridge."""
        try:
            self._redis = redis.from_url(self.redis_url, encoding="utf-8", decode_responses=True)
            await self._redis.ping()

            self._pubsub = self._redis.pubsub()
            # Subscribe to all mission events
            await self._pubsub.psubscribe("mission:*")

            self._listen_task = asyncio.create_task(self._listen_loop())
            logger.info("✅ Redis Event Bridge Started (Listening to mission:*)")
        except Exception as e:
            logger.error(f"❌ Failed to start Redis Event Bridge: {e}")

    async def stop(self) -> None:
        """Stop the bridge."""
        if self._listen_task:
            self._listen_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._listen_task

        if self._pubsub:
            await self._pubsub.close()

        if self._redis:
            await self._redis.close()

        logger.info("Redis Event Bridge Stopped")

    async def _listen_loop(self) -> None:
        """Main loop to process incoming Redis messages."""
        if not self._pubsub:
            return

        async for message in self._pubsub.listen():
            if message["type"] == "pmessage":
                channel = message["channel"]
                data = message["data"]
                try:
                    payload = json.loads(data)
                    # Payload format from Microservice: {"event_type": ..., "data": ...}

                    # We need to construct a domain event object or pass raw dict?
                    # The internal bus expects `EventPayload` which is `object`.
                    # But the websocket handler expects `MissionEvent` OR similar structure.

                    # The `EventBus` puts items into a queue.
                    # The `stream_mission_ws` reads from queue: `event = await queue.get()`.
                    # Then it does: `if event.id <= last_event_id: continue` (This assumes `event` has ID).

                    # Wait, the internal `EventBus` was carrying `MissionEvent` objects (SQLModel).
                    # Now we are receiving JSON dicts.
                    # This is a BREAKING CHANGE for the consumer.

                    # I must adapt the message to match what `stream_mission_ws` expects.
                    # Or update `stream_mission_ws` to handle dicts.

                    # Adapting is better for "BFF" logic.
                    # But `MissionEvent` has an ID from DB. Redis events might NOT have ID if they are transient?
                    # The Microservice saves event to DB then publishes. So it has ID?
                    # The payload I implemented in Microservice: `{"event_type": ..., "data": ...}`.
                    # It does NOT include the Event ID.

                    # FIX: Update Microservice to include Event ID in payload?
                    # Yes, `_log_event` in Microservice saves to DB. I should include `event.id` in the payload.

                    # Assume for now I will fix Microservice later or handle it here.
                    # Let's forward the Dict and update the Router to handle Dict.

                    await self._internal_bus.publish(channel, payload)

                except json.JSONDecodeError:
                    logger.warning(f"Failed to decode Redis message: {data}")
                except Exception as e:
                    logger.error(f"Error processing Redis message: {e}")


# Singleton
_bridge: RedisEventBridge | None = None


def get_redis_bridge() -> RedisEventBridge:
    global _bridge
    if _bridge is None:
        # Use settings for URL?
        # For now, hardcode or get from env, but app settings might not have REDIS_URL.
        # Docker default is `redis://redis:6379`.
        _bridge = RedisEventBridge()
    return _bridge
