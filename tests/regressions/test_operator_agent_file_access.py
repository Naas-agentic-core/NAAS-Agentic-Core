from unittest.mock import MagicMock

import pytest

from app.core.protocols import CollaborationContext
from microservices.orchestrator_service.src.services.overmind.agents.operator import OperatorAgent


class MockContext(CollaborationContext):
    def __init__(self, data=None, shared_memory=None):
        self.data = data or {}
        self.shared_memory = shared_memory or {}

    def get(self, key, default=None):
        return self.data.get(key, default)

    def update(self, key, value):
        self.data[key] = value


@pytest.fixture
def operator_agent():
    executor = MagicMock()
    return OperatorAgent(task_executor=executor)


def test_should_skip_task_allow_read_file_with_metadata_only(operator_agent):
    """
    Verify that read_file is allowed when only exercise_metadata is present (no content).
    This ensures the agent can fetch the content.
    """
    context = MockContext(
        data={"exercise_metadata": {"year": 2024, "subject": "Math"}}, shared_memory={}
    )

    should_skip, reason = operator_agent._should_skip_task("read_file", context)
    assert should_skip is False, (
        f"Should not skip read_file when only metadata is present. Reason: {reason}"
    )

    should_skip, reason = operator_agent._should_skip_task("list_dir", context)
    assert should_skip is False, (
        f"Should not skip list_dir when only metadata is present. Reason: {reason}"
    )


def test_should_skip_task_block_read_file_with_content(operator_agent):
    """
    Verify that read_file is blocked when exercise_content is already present.
    """
    context = MockContext(
        data={
            "exercise_metadata": {"year": 2024, "subject": "Math"},
            "exercise_content": "The content of the exercise...",
        },
        shared_memory={},
    )

    should_skip, reason = operator_agent._should_skip_task("read_file", context)
    assert should_skip is True
    assert reason == "redundant_with_seeded_content"


def test_should_skip_task_block_shell_always_with_context(operator_agent):
    """
    Verify that shell tools are blocked if any context is present (safety).
    """
    context = MockContext(data={"exercise_metadata": {"year": 2024}}, shared_memory={})

    should_skip, reason = operator_agent._should_skip_task("run_shell", context)
    assert should_skip is True
    assert reason == "unsafe_tool_for_education_request"


def test_should_allow_everything_without_context(operator_agent):
    """
    Verify that without educational context, tools are not blocked by this logic.
    """
    context = MockContext(data={}, shared_memory={})

    should_skip, _ = operator_agent._should_skip_task("read_file", context)
    assert should_skip is False

    should_skip, _ = operator_agent._should_skip_task("run_shell", context)
    assert should_skip is False
