"""
اختبارات وحدة لنظام الذكاء الجماعي الفائق.
"""

from unittest.mock import MagicMock

import pytest

from microservices.orchestrator_service.src.services.overmind.domain.super_intelligence.analyzer import SituationAnalyzer
from microservices.orchestrator_service.src.services.overmind.domain.super_intelligence.models import (
    Decision,
    DecisionCategory,
    DecisionImpact,
    DecisionPriority,
)
from microservices.orchestrator_service.src.services.overmind.domain.super_intelligence.synthesizer import DecisionSynthesizer
from microservices.orchestrator_service.src.services.overmind.domain.super_intelligence.system import SuperCollectiveIntelligence


@pytest.fixture
def mock_council():
    return MagicMock()


@pytest.fixture
def mock_hub():
    hub = MagicMock()
    hub.record_contribution = MagicMock()
    hub.store_data = MagicMock()
    return hub


@pytest.mark.asyncio
async def test_make_autonomous_decision_flow(mock_council, mock_hub):
    """
    اختبار التدفق الكامل لاتخاذ القرار.
    """
    sci = SuperCollectiveIntelligence(mock_council, mock_hub)

    situation = "System load is critical"
    context = {"constraints": ["no_downtime"], "metrics": {"cpu": 95}}

    decision = await sci.make_autonomous_decision(situation, context)

    assert isinstance(decision, Decision)
    assert decision.title.startswith("Autonomous Decision")
    assert decision.confidence_score > 0
    assert len(sci.decision_history) == 1

    # Verify Hub interaction
    assert mock_hub.store_data.called


def test_decision_model_confidence():
    """
    اختبار منطق حساب الثقة في نموذج القرار.
    """
    decision = Decision(
        category=DecisionCategory.TECHNICAL,
        priority=DecisionPriority.HIGH,
        impact=DecisionImpact.MEDIUM_TERM,
        title="Test Decision",
        description="Test",
        reasoning="Because...",
        agents_involved=["A1", "A2"],
    )

    initial_score = decision.calculate_confidence()

    # Add factors
    decision.alternatives_considered = [{"option": "A"}]
    decision.risks = [{"risk": "R"}]

    new_score = decision.calculate_confidence()
    assert new_score > initial_score


@pytest.mark.asyncio
async def test_analyzer_logic():
    """
    اختبار منطق المحلل.
    """
    situation = "This is a very complex and urgent situation"
    context = {"threats": ["security breach"]}

    analysis = await SituationAnalyzer.analyze(situation, context)

    assert analysis["complexity_level"] == "high"  # Contains 'complex'
    assert analysis["urgency"] == "high"  # Contains 'urgent'
    assert "security breach" in analysis["threats"]


@pytest.mark.asyncio
async def test_synthesizer_logic():
    """
    اختبار منطق المركب.
    """
    situation = "Simple task"
    analysis = {"complexity_level": "low", "urgency": "low"}
    consultations = {
        "agent1": {"confidence": 90},
        "agent2": {"confidence": 80},
    }

    decision = await DecisionSynthesizer.synthesize(situation, analysis, consultations)

    assert decision.priority == DecisionPriority.MEDIUM
    assert decision.impact == DecisionImpact.SHORT_TERM
    assert len(decision.agents_involved) == 2
