"""
اختبارات حقن نص التمرين داخل مهام الكتابة.
"""

from unittest.mock import AsyncMock

import pytest

from microservices.orchestrator_service.src.services.overmind.agents.operator import OperatorAgent
from microservices.orchestrator_service.src.services.overmind.domain.context import InMemoryCollaborationContext


@pytest.mark.asyncio
async def test_operator_injects_exercise_content_into_write_task():
    executor = type(
        "DummyExecutor",
        (),
        {"execute_task": AsyncMock(return_value={"status": "success"})},
    )()
    operator = OperatorAgent(task_executor=executor)

    design = {
        "tasks": [
            {
                "name": "write exercise",
                "tool_name": "write_file",
                "tool_args": {"path": "/tmp/exercise.md"},
            }
        ]
    }

    context = InMemoryCollaborationContext({"exercise_content": "نص التمرين"})

    result = await operator.execute_tasks(design, context)

    assert result["tasks_executed"] == 1
    executor.execute_task.assert_called_once()
    sent_task = executor.execute_task.call_args[0][0]
    assert "\\u0646\\u0635 \\u0627\\u0644\\u062a\\u0645\\u0631\\u064a\\u0646" in str(
        sent_task.tool_args_json
    )
