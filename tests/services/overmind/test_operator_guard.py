"""
اختبارات حراسة المنفذ ضد أدوات غير مناسبة في الطلبات التعليمية.
"""

from unittest.mock import AsyncMock

import pytest

from microservices.orchestrator_service.src.services.overmind.agents.operator import OperatorAgent
from microservices.orchestrator_service.src.services.overmind.domain.context import InMemoryCollaborationContext


@pytest.mark.asyncio
async def test_operator_skips_shell_when_exercise_context_present():
    executor = type(
        "DummyExecutor",
        (),
        {"execute_task": AsyncMock(return_value={"status": "success"})},
    )()
    operator = OperatorAgent(task_executor=executor)

    design = {
        "tasks": [
            {"name": "shell", "tool_name": "run_shell", "tool_args": {"command": "ls"}},
            {
                "name": "content",
                "tool_name": "search_educational_content",
                "tool_args": {"query": "تمرين الاحتمالات"},
            },
        ]
    }

    context = InMemoryCollaborationContext(
        {"exercise_content": "نص التمرين", "exercise_metadata": {"year": "2024"}}
    )

    result = await operator.execute_tasks(design, context)

    assert result["tasks_executed"] == 2
    assert executor.execute_task.call_count == 1

    skipped = next(item for item in result["results"] if item.get("status") == "skipped")
    assert skipped["reason"] == "unsafe_tool_for_education_request"
