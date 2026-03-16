"""أدوات التفعيل التدريجي لمسار تنسيق الدردشة نحو خدمة Orchestrator."""

from __future__ import annotations

import hashlib
import os


def _rollout_bucket(identity: str) -> int:
    """يُنتج Bucket حتميًا بين 0 و99 لضمان Canary ثابت لكل هوية."""
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _get_canary_percent() -> int:
    """يقرأ نسبة التفعيل التدريجي من البيئة مع تطبيع آمن إلى [0, 100]."""
    raw = os.getenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "100")
    try:
        numeric = int(raw)
    except ValueError:
        return 100
    return max(0, min(100, numeric))


def should_delegate_to_orchestrator(*, user_id: int, is_agent_intent: bool) -> bool:
    """يقرر تفويض الطلب إلى الخدمة المصغّرة وفق النية ونسبة Canary."""
    if not is_agent_intent:
        return False

    canary_percent = _get_canary_percent()
    if canary_percent == 100:
        return True
    if canary_percent == 0:
        return False

    identity = f"chat_orchestration:{user_id}"
    return _rollout_bucket(identity) < canary_percent

