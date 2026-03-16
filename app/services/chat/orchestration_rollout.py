"""أدوات التفعيل التدريجي لمسار تنسيق الدردشة نحو خدمة Orchestrator."""

from __future__ import annotations

import hashlib
import os

_ALLOWED_CAPABILITY_LEVELS = {"parity_ready", "production_eligible"}


def _read_env_flag(name: str, *, default: bool = False) -> bool:
    """يقرأ قيمة من البيئة بصيغة منطقية بطريقة صريحة وآمنة."""
    raw_value = os.getenv(name, "1" if default else "0").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _rollout_bucket(identity: str) -> int:
    """يُنتج Bucket حتميًا بين 0 و99 لضمان Canary ثابت لكل هوية."""
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _get_canary_percent() -> int:
    """يقرأ نسبة التفعيل التدريجي من البيئة مع تطبيع آمن إلى [0, 100]."""
    raw = os.getenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "0")
    try:
        numeric = int(raw)
    except ValueError:
        return 0
    return max(0, min(100, numeric))


def _is_rollout_guard_open() -> bool:
    """يتحقق من جاهزية التحويل عبر بوابات التفعيل والتوافق قبل أي تفويض."""
    if not _read_env_flag("CHAT_ORCHESTRATOR_ROLLOUT_ENABLED", default=False):
        return False

    if not _read_env_flag("CHAT_ORCHESTRATOR_PARITY_VERIFIED", default=False):
        return False

    capability_level = os.getenv("CHAT_ORCHESTRATOR_CAPABILITY_LEVEL", "stub").strip().lower()
    return capability_level in _ALLOWED_CAPABILITY_LEVELS


def should_delegate_to_orchestrator(*, user_id: int, is_agent_intent: bool) -> bool:
    """يقرر تفويض الطلب إلى الخدمة المصغّرة وفق النية وبوابات الجاهزية وCanary."""
    if not is_agent_intent:
        return False

    if not _is_rollout_guard_open():
        return False

    canary_percent = _get_canary_percent()
    if canary_percent == 100:
        return True
    if canary_percent == 0:
        return False

    identity = f"chat_orchestration:{user_id}"
    return _rollout_bucket(identity) < canary_percent
