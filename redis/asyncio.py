"""تنفيذ Redis Async مبسط يحاكي الواجهة المطلوبة فقط."""

from __future__ import annotations

from collections import defaultdict


class PubSub:
    """يحاكي قناة Pub/Sub بواجهة غير متزامنة."""

    def __init__(self) -> None:
        self._subscriptions: set[str] = set()

    async def subscribe(self, *channels: str) -> None:
        self._subscriptions.update(channels)

    async def psubscribe(self, *patterns: str) -> None:
        self._subscriptions.update(patterns)

    async def unsubscribe(self, *channels: str) -> None:
        if channels:
            self._subscriptions.difference_update(channels)
        else:
            self._subscriptions.clear()

    async def listen(self):
        if False:
            yield None

    async def close(self) -> None:
        self._subscriptions.clear()


class Redis:
    """عميل Redis مبسط بالحد الأدنى المطلوب في الوحدة الحالية."""

    def __init__(self) -> None:
        self._store: dict[str, str] = {}
        self._channels: dict[str, list[str]] = defaultdict(list)

    async def ping(self) -> bool:
        return True

    def pubsub(self) -> PubSub:
        return PubSub()

    async def publish(self, channel: str, message: str) -> int:
        self._channels[channel].append(message)
        return 1

    async def get(self, key: str):
        return self._store.get(key)

    async def set(self, key: str, value, ex: int | None = None) -> bool:
        _ = ex
        self._store[key] = value
        return True

    async def delete(self, key: str) -> int:
        return 1 if self._store.pop(key, None) is not None else 0

    async def exists(self, key: str) -> int:
        return 1 if key in self._store else 0

    async def close(self) -> None:
        self._store.clear()


class ClientNamespace:
    """مساحة أسماء للتوافق مع redis.asyncio.client.PubSub."""

    PubSub = PubSub


client = ClientNamespace


def from_url(*_args, **_kwargs) -> Redis:
    return Redis()
