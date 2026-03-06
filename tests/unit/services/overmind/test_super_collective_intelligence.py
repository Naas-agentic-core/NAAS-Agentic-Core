from __future__ import annotations

import pytest

from microservices.orchestrator_service.src.services.overmind.agents import AgentCouncil
from microservices.orchestrator_service.src.services.overmind.collaboration import CollaborationHub
from microservices.orchestrator_service.src.services.overmind.domain.super_intelligence.models import (
    Decision,
    DecisionCategory,
    DecisionImpact,
    DecisionPriority,
)
from microservices.orchestrator_service.src.services.overmind.domain.super_intelligence.system import SuperCollectiveIntelligence


class StubAgent:
    """وكيل تجريبي يقدم استشارة متزامنة."""

    def __init__(self, response: dict[str, object]) -> None:
        self._response = response

    def consult(self, situation: str, analysis: dict[str, object]) -> dict[str, object]:
        return {"situation": situation, "analysis": analysis, **self._response}


class AsyncStubAgent:
    """وكيل تجريبي يقدم استشارة غير متزامنة."""

    def __init__(self, response: dict[str, object]) -> None:
        self._response = response

    async def consult(self, situation: str, analysis: dict[str, object]) -> dict[str, object]:
        return {"situation": situation, "analysis": analysis, **self._response}


class StubHub(CollaborationHub):
    """مركز تعاون مزيف يرفع خطأ عند التخزين لاختبار المسار الآمن."""

    def store_data(self, key: str, value: object) -> None:
        raise RuntimeError("boom")


def build_decision(confidence: float) -> Decision:
    """يبني قراراً تجريبياً مبسطاً لاختبارات التنفيذ."""
    return Decision(
        category=DecisionCategory.TECHNICAL,
        priority=DecisionPriority.HIGH,
        impact=DecisionImpact.IMMEDIATE,
        title="قرار تجريبي",
        description="وصف مختصر",
        reasoning="سبب مختصر",
        agents_involved=["strategist", "architect"],
        confidence_score=confidence,
    )


def build_council(agent: object) -> AgentCouncil:
    """يبني مجلس وكلاء باستخدام وكيل واحد لكل الأدوار."""
    return AgentCouncil(
        strategist=agent,
        architect=agent,
        operator=agent,
        auditor=agent,
    )


@pytest.mark.asyncio
async def test_consult_agent_supports_sync_and_async():
    hub = CollaborationHub()
    sync_agent = StubAgent({"mode": "sync"})
    async_agent = AsyncStubAgent({"mode": "async"})
    system = SuperCollectiveIntelligence(build_council(sync_agent), hub)

    sync_result = await system._consult_agent(
        agent_name="strategist",
        agent=sync_agent,
        situation="sync",
        analysis={"a": 1},
    )
    async_result = await system._consult_agent(
        agent_name="strategist",
        agent=async_agent,
        situation="async",
        analysis={"b": 2},
    )

    assert sync_result["mode"] == "sync"
    assert async_result["mode"] == "async"


@pytest.mark.asyncio
async def test_consult_agent_requires_consult_method():
    hub = CollaborationHub()
    system = SuperCollectiveIntelligence(build_council(StubAgent({})), hub)

    with pytest.raises(ValueError, match="does not implement consult"):
        await system._consult_agent(
            agent_name="ghost",
            agent=object(),
            situation="missing",
            analysis={},
        )


@pytest.mark.asyncio
async def test_consultations_are_recorded_in_hub():
    hub = CollaborationHub()
    agent = StubAgent({"answer": "ok"})
    system = SuperCollectiveIntelligence(build_council(agent), hub)

    await system._consult_agents("situation", {"signal": "high"})

    assert hub.stats["total_contributions"] == 4
    assert hub.contributions[0].action == "consultation"


def test_execute_decision_updates_success_and_failure():
    hub = CollaborationHub()
    agent = StubAgent({"answer": "ok"})
    system = SuperCollectiveIntelligence(build_council(agent), hub)

    success_decision = build_decision(confidence=90.0)
    failure_decision = build_decision(confidence=10.0)

    success_result = system._build_execution_result(success_decision, True)
    assert success_result["success"] is True

    failure_result = system._build_execution_result(failure_decision, False)
    assert failure_result["success"] is False

    system._update_execution_outcome(success_decision, True)
    system._update_execution_outcome(failure_decision, False)

    assert system.successful_decisions == 1
    assert system.failed_decisions == 1
    assert success_decision.outcome == "success"
    assert failure_decision.outcome == "failed"


def test_safe_ratio_and_truncate_text_behavior():
    hub = CollaborationHub()
    agent = StubAgent({})
    system = SuperCollectiveIntelligence(build_council(agent), hub)

    assert system._safe_ratio(5, 0) == 0.0
    assert system._safe_ratio(5, 10) == 0.5
    assert system._truncate_text("مرحبا", 0) == ""
    assert system._truncate_text("مرحبا", 2) == "مر"

    long_text = "x" * 80
    payload = system._build_consultation_input(long_text)
    assert payload["situation"] == "x" * 50


def test_store_decision_in_hub_handles_failure():
    agent = StubAgent({})
    hub = StubHub()
    system = SuperCollectiveIntelligence(build_council(agent), hub)

    decision = build_decision(confidence=80.0)

    system._store_decision_in_hub(decision)
