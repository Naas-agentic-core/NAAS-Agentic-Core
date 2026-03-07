import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.services.chat.context import ChatContext
from app.services.chat.orchestrator import ChatOrchestrator


@pytest.mark.asyncio
async def test_process_passes_session_factory():
    orchestrator = ChatOrchestrator()
    mock_ai = AsyncMock()
    mock_factory = MagicMock()

    # We can inspect the context passed to handlers by mocking the handlers registry
    # But since we modified the code, we can also trust manual inspection or integration test.
    # Let's try to subclass ChatOrchestrator to inspect context creation

    orchestrator = ChatOrchestrator()

    # Force MissionComplexHandler to be the only handler for a specific intent
    # Actually Orchestrator uses IntentDetector.
    # Let's mock IntentDetector to return MISSION_COMPLEX

    orchestrator._intent_detector = AsyncMock()
    orchestrator._intent_detector.detect.return_value = MagicMock(
        intent="MISSION_COMPLEX", confidence=1.0, params={}
    )

    # Mock the handler execution to just return the context for verification
    # or let it run MissionComplexHandler logic which we can partially mock.

    # Let's mock the handlers registry execution
    orchestrator._handlers = MagicMock()
    orchestrator._handlers.execute = AsyncMock()
    orchestrator._handlers.execute.return_value = None  # Don't yield anything

    # Run process
    async for _ in orchestrator.process("test", 1, 1, mock_ai, [], session_factory=mock_factory):
        pass

    # Verify execute was called with a context containing session_factory
    call_args = orchestrator._handlers.execute.call_args
    assert call_args is not None
    context = call_args[0][0]

    assert isinstance(context, ChatContext)
    assert context.session_factory == mock_factory


if __name__ == "__main__":
    asyncio.run(test_process_passes_session_factory())
