from unittest.mock import AsyncMock, MagicMock

import pytest

from microservices.orchestrator_service.src.services.overmind.agents.auditor import AuditorAgent


@pytest.mark.asyncio
async def test_review_work_detects_plan_and_switches_mode():
    """
    Test that review_work detects a Plan structure and uses the Plan Review prompt.
    """
    mock_ai = MagicMock()
    mock_ai.send_message = AsyncMock(
        return_value='{"approved": true, "feedback": "Good plan", "score": 0.9}'
    )

    auditor = AuditorAgent(mock_ai)
    context = MagicMock()

    plan = {
        "strategy_name": "Test Strategy",
        "reasoning": "Reasoning",
        "steps": [{"name": "Step 1", "description": "Do it", "tool_hint": "tool"}],
    }

    await auditor.review_work(plan, "Test Objective", context)

    # Verify the prompt used was the Plan one
    call_args = mock_ai.send_message.call_args
    assert call_args is not None
    kwargs = call_args.kwargs
    system_prompt = kwargs.get("system_prompt")

    assert 'مراجعة "خطة عمل" (Action Plan)' in system_prompt
    assert "هل الخطوات منطقية وتؤدي لتحقيق الهدف؟" in system_prompt


@pytest.mark.asyncio
async def test_review_work_uses_standard_prompt_for_results():
    """
    Test that review_work uses the Standard prompt for non-plan results.
    """
    mock_ai = MagicMock()
    mock_ai.send_message = AsyncMock(
        return_value='{"approved": true, "feedback": "Good job", "score": 0.9}'
    )

    auditor = AuditorAgent(mock_ai)
    context = MagicMock()

    result = {"output": "The answer is 42", "files_created": ["answer.txt"]}

    await auditor.review_work(result, "Test Objective", context)

    # Verify the prompt used was the Standard one
    call_args = mock_ai.send_message.call_args
    assert call_args is not None
    kwargs = call_args.kwargs
    system_prompt = kwargs.get("system_prompt")

    assert "مراجعة نتائج تنفيذ المهام" in system_prompt
    assert "بدأت في تحقيق الهدف الأصلي" in system_prompt
