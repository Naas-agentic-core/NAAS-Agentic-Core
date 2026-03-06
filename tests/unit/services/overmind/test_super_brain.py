# tests/services/overmind/test_super_brain.py
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.domain.models import Mission
from microservices.orchestrator_service.src.services.overmind.domain.cognitive import SuperBrain, _extract_exercise_request
from microservices.orchestrator_service.src.services.overmind.domain.context import InMemoryCollaborationContext
from microservices.orchestrator_service.src.services.overmind.domain.enums import CognitivePhase

AUDITOR_EXPECTED_REVIEWS = 2
STRATEGIST_EXPECTED_CALLS = 2


class StubPlanner:
    """مخطط تجريبي يعيد خططاً محددة مع تتبع السياق."""

    def __init__(self, plans: list[dict]) -> None:
        self._plans = plans
        self.calls = 0
        self.contexts: list[InMemoryCollaborationContext] = []
        self.objectives: list[str] = []

    async def create_plan(self, objective: str, context: InMemoryCollaborationContext) -> dict:
        self.calls += 1
        self.objectives.append(objective)
        self.contexts.append(context)
        return self._plans[min(self.calls - 1, len(self._plans) - 1)]


class StubArchitect:
    """معماري تجريبي يعيد تصميمًا ثابتًا مع توثيق مرّات الاستدعاء."""

    def __init__(self, design: dict) -> None:
        self._design = design
        self.calls = 0
        self.contexts: list[InMemoryCollaborationContext] = []

    async def design_solution(self, plan: dict, context: InMemoryCollaborationContext) -> dict:
        self.calls += 1
        self.last_plan = plan
        self.contexts.append(context)
        return self._design


class StubOperator:
    """منفذ تجريبي يعيد نتيجة تنفيذ ثابتة."""

    def __init__(self, result: dict) -> None:
        self._result = result
        self.calls = 0
        self.contexts: list[InMemoryCollaborationContext] = []

    async def execute_tasks(self, design: dict, context: InMemoryCollaborationContext) -> dict:
        self.calls += 1
        self.last_design = design
        self.contexts.append(context)
        return self._result


class StubAuditor:
    """مدقق تجريبي يسمح بحقن مراجعات متتالية وكشف الحلقات."""

    def __init__(
        self,
        reviews: list[dict],
        detect_loop_sequence: list[Exception | None] | None = None,
        hash_value: str = "noop-hash",
    ) -> None:
        self._reviews = reviews
        self._detect_loop_sequence = detect_loop_sequence or []
        self._hash_value = hash_value
        self.review_calls = 0
        self.detect_calls = 0
        self.review_contexts: list[InMemoryCollaborationContext] = []
        self.reviewed_results: list[dict] = []
        self.reviewed_objectives: list[str] = []

    def detect_loop(self, history_hashes: list[str], plan: dict) -> None:
        self.last_history = history_hashes
        self.last_detected_plan = plan
        if self.detect_calls < len(self._detect_loop_sequence):
            effect = self._detect_loop_sequence[self.detect_calls]
            self.detect_calls += 1
            if effect:
                raise effect
            return
        self.detect_calls += 1
        return

    def _compute_hash(self, plan: dict) -> str:
        self.last_hashed_plan = plan
        return self._hash_value

    async def review_work(
        self, result: dict, original_objective: str, context: InMemoryCollaborationContext
    ) -> dict:
        self.review_calls += 1
        self.reviewed_results.append(result)
        self.reviewed_objectives.append(original_objective)
        self.review_contexts.append(context)
        return self._reviews[min(self.review_calls - 1, len(self._reviews) - 1)]


@pytest.mark.asyncio
async def test_super_brain_loop_success():
    # 1. Setup Mocks
    strategist = StubPlanner(plans=[{"steps": ["do_something"]}])
    architect = StubArchitect(design={"tasks": [{"id": 1}]})
    operator = StubOperator(result={"status": "success"})
    auditor = StubAuditor(
        reviews=[
            {"approved": True, "feedback": "Plan Good"},
            {"approved": True, "feedback": "Execution Good"},
        ]
    )

    brain = SuperBrain(
        strategist=strategist, architect=architect, operator=operator, auditor=auditor
    )

    mission = Mission(id=1, objective="Build a spaceship")

    # 2. Execute
    with patch(
        "app.services.chat.tools.retrieval.search_educational_content",
        new=AsyncMock(return_value=""),
    ):
        result = await brain.process_mission(mission)

    # 3. Verify
    assert result == {"status": "success"}

    # Verify collaborative context was passed
    assert strategist.calls == 1
    assert isinstance(strategist.contexts[0], InMemoryCollaborationContext)

    assert architect.calls == 1
    assert operator.calls == 1

    # Auditor called twice (Plan Review + Final Review)
    assert auditor.review_calls == AUDITOR_EXPECTED_REVIEWS


@pytest.mark.asyncio
async def test_super_brain_seeds_exercise_context():
    strategist = StubPlanner(plans=[{"steps": ["do_something"]}])
    architect = StubArchitect(design={"tasks": [{"id": 1}]})
    operator = StubOperator(result={"status": "success"})
    auditor = StubAuditor(
        reviews=[
            {"approved": True, "feedback": "Plan Good"},
            {"approved": True, "feedback": "Execution Good"},
        ]
    )

    brain = SuperBrain(
        strategist=strategist, architect=architect, operator=operator, auditor=auditor
    )

    mission = Mission(
        id=3,
        objective="اعطني تمرين الاحتمالات بكالوريا شعبة علوم تجريبية الموضوع الاول التمرين الأول لسنة 2024 في مادة الرياضيات",
    )

    with patch(
        "app.services.chat.tools.retrieval.search_educational_content",
        new=AsyncMock(return_value="نص التمرين"),
    ):
        await brain.process_mission(mission)

    seeded_context = strategist.contexts[0]
    assert seeded_context.get("exercise_content") == "نص التمرين"
    assert seeded_context.get("exercise_metadata")["year"] == "2024"


def test_extract_exercise_request_handles_arabic_digits():
    payload = _extract_exercise_request("أعطني تمرين بكالوريا ٢٠٢٤ الموضوع الثاني التمرين ٢")

    assert payload is not None
    assert payload["year"] == "2024"
    assert payload["exam_ref"] == "الموضوع الثاني"
    assert payload["exercise_id"] == "2"


@pytest.mark.asyncio
async def test_super_brain_self_correction():
    # 1. Setup Mocks
    strategist = StubPlanner(plans=[{"steps": ["bad_plan"]}, {"steps": ["bad_plan"]}])
    architect = StubArchitect(design={"tasks": []})
    operator = StubOperator(result={})
    auditor = StubAuditor(
        reviews=[
            {"approved": False, "feedback": "Bad Plan"},
            {"approved": True, "feedback": "Good Plan"},
            {"approved": True, "feedback": "Done"},
        ]
    )

    brain = SuperBrain(
        strategist=strategist, architect=architect, operator=operator, auditor=auditor
    )

    mission = Mission(id=2, objective="Fix bugs")

    # 2. Execute
    await brain.process_mission(mission)

    # 3. Verify
    # Strategist should be called twice (Initial + Re-planning)
    assert strategist.calls == STRATEGIST_EXPECTED_CALLS

    # Check if context carried the feedback
    context_2 = strategist.contexts[1]
    assert context_2.get("feedback_from_previous_attempt") == "Bad Plan"


@pytest.mark.asyncio
async def test_execute_phase_timeout_logs_event():
    strategist = StubPlanner(plans=[{"steps": ["noop"]}])
    architect = StubArchitect(design={"tasks": []})
    operator = StubOperator(result={})
    auditor = StubAuditor(reviews=[{"approved": True, "feedback": "Ok"}])

    brain = SuperBrain(
        strategist=strategist, architect=architect, operator=operator, auditor=auditor
    )

    events: list[tuple[str, dict[str, object]]] = []

    async def log_event(event_type: str, payload: dict[str, object]) -> None:
        events.append((event_type, payload))

    async def slow_action() -> dict[str, object]:
        await asyncio.sleep(0.01)
        return {"status": "slow"}

    with pytest.raises(RuntimeError, match="timeout"):
        await brain._execute_phase(
            phase_name=CognitivePhase.EXECUTION,
            agent_name="Tester",
            action=slow_action,
            timeout=0.001,
            log_func=log_event,
        )

    assert events[0][0] == "phase_start"
    assert events[-1][0] == "execution_timeout"
