from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.domain.models import Mission
from microservices.orchestrator_service.src.services.overmind.agents.architect import ArchitectAgent
from microservices.orchestrator_service.src.services.overmind.agents.auditor import AuditorAgent
from microservices.orchestrator_service.src.services.overmind.agents.operator import OperatorAgent
from microservices.orchestrator_service.src.services.overmind.agents.strategist import StrategistAgent
from microservices.orchestrator_service.src.services.overmind.domain.cognitive import SuperBrain


@pytest.mark.asyncio
async def test_council_of_wisdom_flow():
    """
    Verifies the Super Agent's cognitive loop:
    Strategist -> Architect -> Operator -> Auditor.
    """
    # 1. Mock Agents
    strategist = MagicMock(spec=StrategistAgent)
    strategist.create_plan = AsyncMock(return_value={"strategy": "Winning"})

    architect = MagicMock(spec=ArchitectAgent)
    architect.design_solution = AsyncMock(return_value={"tasks": [{"id": 1}]})

    operator = MagicMock(spec=OperatorAgent)
    operator.execute_tasks = AsyncMock(return_value={"status": "success", "results": ["done"]})

    auditor = MagicMock(spec=AuditorAgent)
    # First review (Plan): Approved
    # Second review (Result): Approved
    auditor.review_work = AsyncMock(side_effect=[{"approved": True}, {"approved": True}])

    # 2. Setup Brain
    brain = SuperBrain(strategist, architect, operator, auditor)

    mission = Mission(id=1, objective="Change the world")

    # 3. Execute
    result = await brain.process_mission(mission)

    # 4. Verify Flow
    assert strategist.create_plan.called
    assert architect.design_solution.called
    assert operator.execute_tasks.called
    assert auditor.review_work.call_count == 2
    assert result["status"] == "success"


@pytest.mark.asyncio
async def test_self_correction_loop():
    """
    Verifies that the brain retries if the Auditor rejects the work.
    """
    strategist = MagicMock(spec=StrategistAgent)
    strategist.create_plan = AsyncMock(return_value={"strategy": "Weak"})

    architect = MagicMock(spec=ArchitectAgent)
    architect.design_solution = AsyncMock(return_value={"tasks": []})

    operator = MagicMock(spec=OperatorAgent)
    operator.execute_tasks = AsyncMock(return_value={"status": "fail"})

    auditor = MagicMock(spec=AuditorAgent)
    # 1. Plan Review: Approved
    # 2. Result Review: REJECTED
    # 3. Plan Review (Iter 2): Approved
    # 4. Result Review (Iter 2): Approved
    auditor.review_work = AsyncMock(
        side_effect=[
            {"approved": True},
            {"approved": False, "feedback": "Try harder"},
            {"approved": True},
            {"approved": True},
        ]
    )

    brain = SuperBrain(strategist, architect, operator, auditor)
    mission = Mission(id=2, objective="Fix bugs")

    await brain.process_mission(mission)

    # Should have run 2 full iterations (minus the first plan check which is once per iter)
    # Actually, logic:
    # Iter 1: Plan (called) -> Audit(Plan)=OK -> Design -> Exec -> Audit(Result)=FAIL
    # Iter 2: Plan (called because phase=RE-PLANNING) -> Audit(Plan)=OK -> Design -> Exec -> Audit(Result)=OK
    assert strategist.create_plan.call_count == 2
    assert operator.execute_tasks.call_count == 2
