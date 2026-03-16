"""سياسات التفعيل التدريجي لتفويض تنسيق الدردشة نحو خدمة Orchestrator."""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass

_ALLOWED_CAPABILITY_LEVELS = {"parity_ready", "production_eligible"}
_STAGE_TO_PERCENT: dict[str, int] = {
    "off": 0,
    "canary_1": 1,
    "canary_5": 5,
    "canary_25": 25,
    "canary_50": 50,
    "full": 100,
}


@dataclass(frozen=True, slots=True)
class RolloutDecision:
    """يمثل قرار التوجيه مع سبب صريح لدعم المراقبة والتحليل."""

    should_delegate: bool
    reason: str
    canary_percent: int
    bucket: int | None


def _read_env_flag(name: str, *, default: bool = False) -> bool:
    """يقرأ قيمة من البيئة بصيغة منطقية بطريقة صريحة وآمنة."""
    raw_value = os.getenv(name, "1" if default else "0").strip().lower()
    return raw_value in {"1", "true", "yes", "on"}


def _rollout_bucket(identity: str) -> int:
    """يُنتج Bucket حتميًا بين 0 و99 لضمان Canary ثابت لكل هوية."""
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _resolve_canary_percent() -> int:
    """يحدد نسبة التفعيل من المرحلة المعلنة أو من النسبة الرقمية المباشرة."""
    stage = os.getenv("CHAT_ORCHESTRATOR_CANARY_STAGE", "").strip().lower()
    if stage:
        return _STAGE_TO_PERCENT.get(stage, 0)

    raw = os.getenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "0")
    try:
        numeric = int(raw)
    except ValueError:
        return 0
    return max(0, min(100, numeric))


def _guard_failure_reason() -> str | None:
    """يعيد سبب إغلاق بوابات الجاهزية، أو None عند الجاهزية الكاملة."""
    if not _read_env_flag("CHAT_ORCHESTRATOR_ROLLOUT_ENABLED", default=False):
        return "rollout_disabled"

    if not _read_env_flag("CHAT_ORCHESTRATOR_PARITY_VERIFIED", default=False):
        return "parity_not_verified"

    capability_level = os.getenv("CHAT_ORCHESTRATOR_CAPABILITY_LEVEL", "stub").strip().lower()
    if capability_level not in _ALLOWED_CAPABILITY_LEVELS:
        return "capability_not_ready"

    return None


def get_orchestration_rollout_decision(*, user_id: int, is_agent_intent: bool) -> RolloutDecision:
    """يبني قرارًا كاملاً للتفويض مع أسباب معيارية يمكن رصدها وتحليلها."""
    if not is_agent_intent:
        return RolloutDecision(
            should_delegate=False,
            reason="non_agent_intent",
            canary_percent=0,
            bucket=None,
        )

    guard_failure = _guard_failure_reason()
    if guard_failure is not None:
        return RolloutDecision(
            should_delegate=False,
            reason=guard_failure,
            canary_percent=0,
            bucket=None,
        )

    canary_percent = _resolve_canary_percent()
    if canary_percent <= 0:
        return RolloutDecision(
            should_delegate=False,
            reason="canary_off",
            canary_percent=0,
            bucket=None,
        )

    if canary_percent >= 100:
        return RolloutDecision(
            should_delegate=True,
            reason="canary_full",
            canary_percent=100,
            bucket=None,
        )

    identity = f"chat_orchestration:{user_id}"
    bucket = _rollout_bucket(identity)
    should_delegate = bucket < canary_percent
    return RolloutDecision(
        should_delegate=should_delegate,
        reason="canary_selected" if should_delegate else "canary_not_selected",
        canary_percent=canary_percent,
        bucket=bucket,
    )


def should_delegate_to_orchestrator(*, user_id: int, is_agent_intent: bool) -> bool:
    """واجهة متوافقة خلفيًا تُرجع قرار التفويض المنطقي فقط."""
    decision = get_orchestration_rollout_decision(user_id=user_id, is_agent_intent=is_agent_intent)
    return decision.should_delegate
