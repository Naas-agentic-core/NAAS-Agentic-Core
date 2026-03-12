"""اختبارات سياسة التوجيه المركزية لمسار chat."""

from __future__ import annotations

from app.infrastructure.clients.routing_policy import ChatRoutingPolicy


def test_policy_defaults_to_single_canonical_candidate(monkeypatch) -> None:
    """يفرض مرشحًا وحيدًا افتراضيًا دون breakglass."""
    monkeypatch.delenv("ORCHESTRATOR_ALLOW_MULTI_TARGET_CHAT", raising=False)
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_FALLBACK_URLS", "http://a:1,http://b:2")

    policy = ChatRoutingPolicy.from_environment("http://orchestrator-service:8006")

    assert policy.candidate_urls() == ["http://orchestrator-service:8006/agent/chat"]
    assert policy.breakglass_multi_target is False


def test_policy_allows_multi_target_in_breakglass(monkeypatch) -> None:
    """يفعل تعدد المرشحات فقط عند التصريح الصريح بوضع الطوارئ."""
    monkeypatch.setenv("ORCHESTRATOR_ALLOW_MULTI_TARGET_CHAT", "1")
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_FALLBACK_URLS", "http://a:1,http://b:2")

    policy = ChatRoutingPolicy.from_environment("http://orchestrator-service:8006")

    assert policy.candidate_urls() == [
        "http://orchestrator-service:8006/agent/chat",
        "http://a:1/agent/chat",
        "http://b:2/agent/chat",
    ]
    assert policy.breakglass_multi_target is True
