import pytest

from app.core.domain.models import Mission
from microservices.orchestrator_service.src.services.overmind.agents.auditor import AuditorAgent
from microservices.orchestrator_service.src.services.overmind.domain.cognitive import CognitiveState, SuperBrain
from microservices.orchestrator_service.src.services.overmind.domain.exceptions import StalemateError
from tests.unit.services.overmind.test_super_brain import (
    StubArchitect,
    StubAuditor,
    StubOperator,
    StubPlanner,
)


@pytest.mark.asyncio
async def test_detect_loop_raises_stalemate():
    """
    Test that the AuditorAgent correctly raises StalemateError when hashes repeat.
    """
    auditor = AuditorAgent(MockAI())

    plan = {"steps": ["do_something"]}
    history = [auditor._compute_hash(plan), auditor._compute_hash(plan)]

    # Third time's a charm (or a curse)
    with pytest.raises(StalemateError):
        auditor.detect_loop(history, plan)


@pytest.mark.asyncio
async def test_superbrain_stalemate_recovery():
    """
    Test that SuperBrain catches StalemateError and updates context.
    """
    # Mocks
    strategist = StubPlanner(plans=[{"action": "same_old_thing"}] * 3)
    architect = StubArchitect(design={"design": "noop"})
    operator = StubOperator(result={})
    auditor = StubAuditor(
        reviews=[{"approved": False, "feedback": "retry"}] * 3,
        detect_loop_sequence=[None, StalemateError("Loop!")],
    )

    brain = SuperBrain(
        strategist=strategist, architect=architect, operator=operator, auditor=auditor
    )

    mission = Mission(id=1, objective="Fix bugs")

    # Mock log function
    logs = []

    async def log_event(evt, _data):
        logs.append(evt)

    # We expect the loop to run, catch the error, and retry
    # We set max_iterations to 3 to prevent infinite test loop
    # Iteration 1: Plan created -> Auditor.detect_loop(OK) -> Review(False) -> Retry
    # Iteration 2: Plan created (same) -> Auditor.detect_loop(ERROR) -> Catch Stalemate -> Update Context -> Retry
    # Iteration 3: ... we just want to verify the catch

    try:
        # Reduce iterations for test speed
        state = CognitiveState(mission_id=1, objective="test")
        state.max_iterations = 2

        # We can't easily inject state into process_mission, so we run process_mission and catch the final failure
        await brain.process_mission(mission, log_event=log_event)
    except RuntimeError:
        pass  # Expected "Mission failed after N iterations"

    # Verify that "stalemate_detected" was logged
    assert "stalemate_detected" in logs or any("stalemate" in str(log_entry) for log_entry in logs)


class MockAI:
    """كائن ذكاء اصطناعي تجريبي لتلبية متطلبات AuditorAgent."""

    async def stream(
        self, *_: object, **__: object
    ) -> None:  # pragma: no cover - مساعدة للاختبارات فقط
        return None
