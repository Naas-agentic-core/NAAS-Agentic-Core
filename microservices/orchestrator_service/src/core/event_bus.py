import json
import logging

import redis.asyncio as redis

from microservices.orchestrator_service.src.core.config import settings

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self.redis = redis.from_url(settings.REDIS_URL, encoding="utf-8", decode_responses=True)

    async def publish(self, channel: str, message: dict[str, object]) -> None:
        try:
            await self.redis.publish(channel, json.dumps(message))
        except Exception as e:
            logger.error(f"Failed to publish to {channel}: {e}")
            raise

    async def subscribe(self, channel: str):
        """
        Yields messages from a channel.
        Context manager usage recommended if possible, or ensure close.
        """
        pubsub = self.redis.pubsub()
        await pubsub.subscribe(channel)
        try:
            async for message in pubsub.listen():
                if message["type"] == "message":
                    try:
                        yield json.loads(message["data"])
                    except json.JSONDecodeError:
                        yield message["data"]
        finally:
            await pubsub.unsubscribe(channel)
            await pubsub.close()

    async def close(self):
        await self.redis.close()


event_bus = EventBus()


def get_event_bus():
    return event_bus
