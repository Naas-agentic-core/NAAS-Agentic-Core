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
    should_delegate = orchestration_rollout.should_delegate_to_orchestrator(
        user_id=42,
        is_agent_intent=False,
    )
    assert should_delegate is False


def test_delegate_disabled_when_rollout_guards_closed(monkeypatch) -> None:
    """يبقي الطلبات على المونوليث إذا لم تكتمل بوابات الأمان والتوافق."""
    monkeypatch.setenv("CHAT_ORCHESTRATOR_ROLLOUT_ENABLED", "0")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_PARITY_VERIFIED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CAPABILITY_LEVEL", "parity_ready")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "100")

    should_delegate = orchestration_rollout.should_delegate_to_orchestrator(
        user_id=42,
        is_agent_intent=True,
    )
    assert should_delegate is False


def test_delegate_disabled_when_capability_not_ready(monkeypatch) -> None:
    """يحظر التفويض إذا لم تصل الخدمة إلى مستوى capability معتمد."""
    monkeypatch.setenv("CHAT_ORCHESTRATOR_ROLLOUT_ENABLED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_PARITY_VERIFIED", "1")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CAPABILITY_LEVEL", "stub")
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "100")

    should_delegate = orchestration_rollout.should_delegate_to_orchestrator(
        user_id=42,
        is_agent_intent=True,
    )
    assert should_delegate is False


def test_delegate_enabled_when_canary_full(monkeypatch) -> None:
    """يفعّل التفويض الكامل عند ضبط النسبة إلى 100% مع استيفاء البوابات."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "100")
    should_delegate = orchestration_rollout.should_delegate_to_orchestrator(
        user_id=42,
        is_agent_intent=True,
    )
    assert should_delegate is True


def test_delegate_disabled_when_canary_zero(monkeypatch) -> None:
    """يعيد كل الطلبات إلى المونوليث عند نسبة Canary تساوي 0%."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "0")
    should_delegate = orchestration_rollout.should_delegate_to_orchestrator(
        user_id=42,
        is_agent_intent=True,
    )
    assert should_delegate is False


def test_delegate_uses_deterministic_bucket_for_partial_canary(monkeypatch) -> None:
    """يحافظ على قرار حتمي لنفس المستخدم عند النسبة الجزئية."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "50")
    first = orchestration_rollout.should_delegate_to_orchestrator(
        user_id=314159,
        is_agent_intent=True,
    )
    second = orchestration_rollout.should_delegate_to_orchestrator(
        user_id=314159,
        is_agent_intent=True,
    )
    assert first is second


def test_delegate_defaults_to_safe_legacy_when_percent_invalid(monkeypatch) -> None:
    """يفرض سلوكًا آمنًا عند نسبة غير صالحة عبر الرجوع إلى 0%."""
    _enable_rollout_guards(monkeypatch)
    monkeypatch.setenv("CHAT_ORCHESTRATOR_CANARY_PERCENT", "invalid")
    should_delegate = orchestration_rollout.should_delegate_to_orchestrator(
        user_id=42,
        is_agent_intent=True,
    )
    assert should_delegate is False
