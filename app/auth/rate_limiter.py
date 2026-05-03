"""وسيط تحديد معدل الطلبات المتقدم."""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)


class AdvancedRateLimiter:
    """محدد معدل الطلبات مع دعم النوافذ المنزلقة والحد الأقصى للطلبات."""

    def __init__(self, max_requests: int = 100, window_seconds: int = 60) -> None:
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self._counters: dict[str, list[float]] = {}

    def is_allowed(self, key: str) -> bool:
        """يتحقق إذا كان الطلب مسموحاً به."""
        import time

        now = time.time()
        window_start = now - self.window_seconds
        requests = self._counters.get(key, [])
        requests = [t for t in requests if t > window_start]
        if len(requests) >= self.max_requests:
            return False
        requests.append(now)
        self._counters[key] = requests
        return True

    def reset(self, key: str) -> None:
        """يعيد تعيين العداد لمفتاح معين."""
        self._counters.pop(key, None)


__all__ = ["AdvancedRateLimiter"]
