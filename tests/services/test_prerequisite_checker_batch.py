import pytest

from app.services.knowledge.prerequisite_checker import PrerequisiteChecker
from app.services.learning.student_profile import StudentProfile


class MockMemoryClient:
    async def get_batch_prerequisites(self, concept_ids):
        # target graph:
        # A requires B, C
        # B requires C, D
        # C requires E
        # D requires []
        # E requires []
        # C should come after E. B should come after C, D. A should come after B, C.

        graph = {
            "A": ["B", "C"],
            "B": ["C", "D"],
            "C": ["E"],
            "D": [],
            "E": [],
        }
        return {k: [p for p in graph.get(k, []) if p in concept_ids] for k in concept_ids}

    async def check_readiness(self, concept_id, mastery):
        class R:
            def __init__(self):
                self.concept_id = "test"
                self.concept_name = "test"
                self.is_ready = False
                self.readiness_score = 0.0
                self.missing_prerequisites = []
                self.weak_prerequisites = []
                self.recommendation = ""

        r = R()

        # return missings for the first level to add them to target
        if concept_id == "A":
            r.missing_prerequisites = ["B", "C"]
        elif concept_id == "B":
            r.missing_prerequisites = ["D", "E"]  # let's just make it simpler
        return r

    async def find_concept_by_topic(self, topic):
        class C:
            def __init__(self):
                self.concept_id = topic

        return C()


@pytest.mark.asyncio
async def test_get_learning_order_topological_sort():
    checker = PrerequisiteChecker(memory_client=MockMemoryClient())
    profile = StudentProfile(student_id="1", current_level="BAC", topic_mastery={})

    # We ask for all explicitly
    target = ["A", "B", "C", "D", "E"]

    # Disable check_readiness side-effects for this test since we already provide all targets
    async def fake_check(*args, **kwargs):
        class R:
            def __init__(self):
                self.missing_prerequisites = []

        return R()

    checker.check_readiness = fake_check

    order = await checker.get_learning_order(profile, target)

    # E and D have 0 in-degree. Alphabetical means D comes before E
    # After D, E are processed, C becomes 0
    # After C, B becomes 0
    # After B, A becomes 0
    assert order == ["D", "E", "C", "B", "A"]


@pytest.mark.asyncio
async def test_get_learning_order_cycle():
    class CycleMockClient:
        async def get_batch_prerequisites(self, concept_ids):
            # A requires B
            # B requires C
            # C requires A
            graph = {
                "A": ["B"],
                "B": ["C"],
                "C": ["A"],
            }
            return {k: [p for p in graph.get(k, []) if p in concept_ids] for k in concept_ids}

    checker = PrerequisiteChecker(memory_client=CycleMockClient())
    profile = StudentProfile(student_id="1", current_level="BAC", topic_mastery={})
    target = ["C", "B", "A"]

    async def fake_check(*args, **kwargs):
        class R:
            def __init__(self):
                self.missing_prerequisites = []

        return R()

    checker.check_readiness = fake_check

    order = await checker.get_learning_order(profile, target)

    # Cycle detected -> fallback to alphabetical
    assert order == ["A", "B", "C"]
