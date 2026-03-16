"""اختبارات سلوك Canary لتفويض تنسيق الدردشة إلى الخدمة المصغّرة."""

from __future__ import annotations

from app.services.chat import orchestration_rollout


def _enable_rollout_guards(monkeypatch) -> None:
    """يفتح جميع بوابات الجاهزية المطلوبة قبل التفعيل التدريجي."""
    monkeypatch.setenv("CHAT_ORCHESTRATOR_ROLLOUT_ENABLED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_PARITY_VERIFIED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CAPABILITY_LEVEL", "parity_ready")


def test_delegate_disabled_for_non_agent_intent(monkeypatch) -> None:
    """يمنع التفويض عندما لا تكون النية ضمن فئة مهام الوكلاء."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "100")
    decision = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=42,
        is_agent_intent=False,
    )
    assert decision.should_delegate is False
    assert decision.reason == "non_agent_intent"


def test_delegate_disabled_when_rollout_guards_closed(monkeypatch) -> None:
    """يبقي الطلبات على المونوليث إذا لم تكتمل بوابات الأمان والتوافق."""
    monkeypatch.setenv("CHAT_ORCHESTRATOR_ROLLOUT_ENABLED", "0")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_PARITY_VERIFIED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CAPABILITY_LEVEL", "parity_ready")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "100")

    decision = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=42,
        is_agent_intent=True,
    )
    assert decision.should_delegate is False
    assert decision.reason == "rollout_disabled"


def test_delegate_disabled_when_parity_not_verified(monkeypatch) -> None:
    """يحظر التفويض عندما لا تكون parity موثقة بعد."""
    monkeypatch.setenv("CHAT_ORCHESTRATOR_ROLLOUT_ENABLED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_PARITY_VERIFIED", "0")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CAPABILITY_LEVEL", "parity_ready")

    decision = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=42,
        is_agent_intent=True,
    )
    assert decision.should_delegate is False
    assert decision.reason == "parity_not_verified"


def test_delegate_disabled_when_capability_not_ready(monkeypatch) -> None:
    """يحظر التفويض إذا لم تصل الخدمة إلى مستوى capability معتمد."""
    monkeypatch.setenv("CHAT_ORCHESTRATOR_ROLLOUT_ENABLED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_PARITY_VERIFIED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CAPABILITY_LEVEL", "stub")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "100")

    decision = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=42,
        is_agent_intent=True,
    )
    assert decision.should_delegate is False
    assert decision.reason == "capability_not_ready"


def test_delegate_enabled_when_canary_full(monkeypatch) -> None:
    """يفعّل التفويض الكامل عند ضبط النسبة إلى 100% مع استيفاء البوابات."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "100")
    decision = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=42,
        is_agent_intent=True,
    )
    assert decision.should_delegate is True
    assert decision.reason == "canary_full"


def test_delegate_disabled_when_canary_zero(monkeypatch) -> None:
    """يعيد كل الطلبات إلى المونوليث عند نسبة Canary تساوي 0%."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "0")
    decision = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=42,
        is_agent_intent=True,
    )
    assert decision.should_delegate is False
    assert decision.reason == "canary_off"


def test_delegate_uses_deterministic_bucket_for_partial_canary(monkeypatch) -> None:
    """يحافظ على قرار حتمي لنفس المستخدم عند النسبة الجزئية."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "50")
    first = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=314159,
        is_agent_intent=True,
    )
    second = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=314159,
        is_agent_intent=True,
    )
    assert first.should_delegate is second.should_delegate
    assert first.bucket == second.bucket


def test_delegate_supports_stage_based_rollout(monkeypatch) -> None:
    """يدعم مراحل Canary المعيارية بدل النسبة الرقمية المباشرة."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_STAGE", "canary_25")
    monkeypatch.delenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", raising=False)
    decision = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=7,
        is_agent_intent=True,
    )
    assert decision.canary_percent == 25


def test_delegate_defaults_to_safe_legacy_when_percent_invalid(monkeypatch) -> None:
    """يفرض سلوكًا آمنًا عند نسبة غير صالحة عبر الرجوع إلى 0%."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "invalid")
    decision = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=42,
        is_agent_intent=True,
    )
    assert decision.should_delegate is False
    assert decision.reason == "canary_off"


def test_legacy_wrapper_matches_decision(monkeypatch) -> None:
    """يحافظ على التوافق الخلفي لدالة should_delegate_to_orchestrator القديمة."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "100")
    value = orchestration_rollout.should_delegate_to_orchestrator(user_id=42, is_agent_intent=True)
    decision = orchestration_rollout.get_orchestration_rollout_decision(
        user_id=42,
        is_agent_intent=True,
    )
    assert value is decision.should_delegate
