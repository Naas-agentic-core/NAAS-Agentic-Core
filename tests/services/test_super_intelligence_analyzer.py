import pytest

from microservices.orchestrator_service.src.services.overmind.domain.super_intelligence.analyzer import SituationAnalyzer
from microservices.orchestrator_service.src.services.overmind.domain.super_intelligence.synthesizer import DecisionSynthesizer


@pytest.mark.asyncio
async def test_analyzer_returns_signal_scores() -> None:
    analysis = await SituationAnalyzer.analyze(
        "موقف معقد وعاجل يحتاج قرار ابتكار",
        {"opportunities": ["opt1", "opt2"]},
    )

    assert analysis["complexity_score"] >= 0.0
    assert analysis["urgency_score"] >= 0.0
    assert analysis["novelty_score"] >= 0.0
    assert analysis["risk_index"] >= 0.0
    assert analysis["strategic_value_score"] >= 0.0
    assert analysis["depth_score"] >= 0.0
    assert analysis["depth_profile"]["depth_score"] == analysis["depth_score"]
    assert analysis["depth_profile"]["context_richness"] >= 0.0
    assert analysis["depth_profile"]["signal_diversity"] >= 0.0
    assert analysis["depth_profile"]["narrative_density"] >= 0.0


@pytest.mark.asyncio
async def test_analyzer_clamps_and_rounds_scores() -> None:
    analysis = await SituationAnalyzer.analyze(
        "very complex urgent critical situation with new innovative approach",
        {
            "constraints": ["c1", "c2", "c3", "c4", "c5", "c6", "c7"],
            "opportunities": ["o1", "o2", "o3", "o4", "o5", "o6"],
            "threats": ["t1", "t2", "t3", "t4", "t5"],
        },
    )

    assert analysis["risk_index"] <= 1.0
    assert analysis["strategic_value_score"] <= 1.0
    assert analysis["depth_score"] <= 1.0
    assert analysis["risk_index"] == round(analysis["risk_index"], 2)
    assert analysis["strategic_value_score"] == round(analysis["strategic_value_score"], 2)
    assert analysis["depth_score"] == round(analysis["depth_score"], 2)


@pytest.mark.asyncio
async def test_synthesizer_uses_scores_for_priority_and_impact() -> None:
    analysis = {
        "complexity_level": "medium",
        "urgency": "normal",
        "complexity_score": 0.9,
        "urgency_score": 0.8,
    }
    decision = await DecisionSynthesizer.synthesize(
        situation="Complex urgent scenario",
        analysis=analysis,
        consultations={"planner": {"confidence": 80.0}},
    )

    assert decision.priority.value in {"critical", "high"}
    assert decision.impact.value in {"long_term", "generational"}


@pytest.mark.asyncio
async def test_synthesizer_sets_category_from_scores() -> None:
    strategic_analysis = {
        "complexity_level": "low",
        "urgency": "normal",
        "strategic_value_score": 0.75,
        "risk_index": 0.2,
    }
    strategic_decision = await DecisionSynthesizer.synthesize(
        situation="Strategic opportunity",
        analysis=strategic_analysis,
        consultations={"planner": {"confidence": 70.0}},
    )
    assert strategic_decision.category.value == "strategic"

    risk_analysis = {
        "complexity_level": "low",
        "urgency": "normal",
        "strategic_value_score": 0.3,
        "risk_index": 0.8,
    }
    risk_decision = await DecisionSynthesizer.synthesize(
        situation="Risk exposure",
        analysis=risk_analysis,
        consultations={"planner": {"confidence": 70.0}},
    )
    assert risk_decision.category.value == "risk"

    depth_analysis = {
        "complexity_level": "medium",
        "urgency": "normal",
        "strategic_value_score": 0.2,
        "risk_index": 0.3,
        "depth_score": 0.8,
    }
    depth_decision = await DecisionSynthesizer.synthesize(
        situation="Architectural refactor",
        analysis=depth_analysis,
        consultations={"planner": {"confidence": 60.0}},
    )
    assert depth_decision.category.value == "architectural"
