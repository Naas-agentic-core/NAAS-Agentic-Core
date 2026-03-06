import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from microservices.orchestrator_service.src.services.overmind.agents.auditor import AuditorAgent


@pytest.mark.asyncio
async def test_auditor_handles_empty_response():
    """Test that AuditorAgent returns safe failure on empty AI response instead of crashing."""
    mock_ai = MagicMock()
    mock_ai.send_message = AsyncMock(return_value="")

    auditor = AuditorAgent(mock_ai)

    # Mock context
    mock_context = MagicMock()

    # Execute
    result = await auditor.review_work({"some": "work"}, "objective", mock_context)

    # Assertions
    assert isinstance(result, dict)
    assert result["approved"] is False
    assert result["score"] == 0.0


@pytest.mark.asyncio
async def test_auditor_handles_malformed_text_response():
    """Test response with no JSON braces."""
    mock_ai = MagicMock()
    mock_ai.send_message = AsyncMock(return_value="I cannot do that because it violates policy.")

    auditor = AuditorAgent(mock_ai)
    mock_context = MagicMock()

    result = await auditor.review_work({"some": "work"}, "objective", mock_context)

    assert result["approved"] is False
    assert result["score"] == 0.0


@pytest.mark.asyncio
async def test_auditor_handles_markdown_wrapped_json():
    """Test standard Markdown code block."""
    valid_json = json.dumps({"approved": True, "feedback": "Good job", "score": 0.9})
    markdown_response = f"Here is the result:\n```json\n{valid_json}\n```"

    mock_ai = MagicMock()
    mock_ai.send_message = AsyncMock(return_value=markdown_response)

    auditor = AuditorAgent(mock_ai)
    mock_context = MagicMock()

    result = await auditor.review_work({"some": "work"}, "objective", mock_context)

    assert result["approved"] is True
    assert result["feedback"] == "Good job"


@pytest.mark.asyncio
async def test_auditor_handles_text_wrapped_json_no_markdown():
    """Test JSON embedded in text without code blocks."""
    valid_json = json.dumps({"approved": True, "feedback": "Good job", "score": 0.9})
    text_response = f"Sure, here is the analysis: {valid_json} ... hope this helps."

    mock_ai = MagicMock()
    mock_ai.send_message = AsyncMock(return_value=text_response)

    auditor = AuditorAgent(mock_ai)
    mock_context = MagicMock()

    result = await auditor.review_work({"some": "work"}, "objective", mock_context)

    assert result["approved"] is True
