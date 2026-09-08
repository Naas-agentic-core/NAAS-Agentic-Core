import logging
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI, Request
from fastapi.responses import StreamingResponse

from microservices.orchestrator_service.src.api import routes


@pytest.fixture
def mock_dependencies(monkeypatch):
    monkeypatch.setattr(routes, "_decode_auth_payload_or_401", lambda _x: (1, {"sub": "1"}))

    async def mock_ensure_conversation(*args, **kwargs):
        return (42, [])  # conversation_id, history_messages

    monkeypatch.setattr(routes, "_ensure_conversation", mock_ensure_conversation)

    # Mock the DB session context manager
    class MockSessionContextManager:
        async def __aenter__(self):
            return AsyncMock()

        async def __aexit__(self, exc_type, exc_val, exc_tb):
            pass

    monkeypatch.setattr(
        routes,
        "_psycopg_session_factory_proxy",
        lambda **_kw: MockSessionContextManager(),
    )

    async def mock_persist(*args, **kwargs):
        pass

    monkeypatch.setattr(routes, "_persist_assistant_message", mock_persist)


@pytest.mark.asyncio
async def test_generator_persistence_logging(caplog, mock_dependencies, monkeypatch):
    """
    Test that stream parsing errors in _generator_with_persistence are correctly logged
    and do not break the streaming response, as per health requirements.
    """
    caplog.set_level(logging.DEBUG)

    async def mock_generator(*args, **kwargs):
        yield '{"type": "assistant_delta", "payload": {"content": "Hello"}}'
        yield "invalid json 1"
        yield '{"type": "assistant_delta", "payload": {"content": " World"}}'
        yield "invalid json 2"
        yield '{"type": "assistant_final", "payload": {"content": "Hello World"}}'

    monkeypatch.setattr(routes, "_run_chat_langgraph", mock_generator)

    app = FastAPI()
    app.state.app_graph = None
    request = Request({"type": "http", "app": app, "headers": []})

    payload = {"question": "Test?", "context": {}}

    response = await routes.chat_messages_endpoint(
        payload=payload, request=request, authorization="Bearer dummy"
    )

    assert isinstance(response, StreamingResponse)

    # Consume the streaming response body
    chunks = []
    async for chunk in response.body_iterator:
        chunks.append(chunk)

    # 1. Assert all chunks are yielded regardless of parse errors
    assert len(chunks) == 5
    assert chunks[0] == '{"type": "assistant_delta", "payload": {"content": "Hello"}}'
    assert chunks[1] == "invalid json 1"
    assert chunks[2] == '{"type": "assistant_delta", "payload": {"content": " World"}}'
    assert chunks[3] == "invalid json 2"
    assert chunks[4] == '{"type": "assistant_final", "payload": {"content": "Hello World"}}'

    # 2. Assert exactly one WARNING is emitted for the first failure
    warnings = [
        r
        for r in caplog.records
        if r.levelname == "WARNING" and "stream_chunk_content_extraction_failed" in r.getMessage()
    ]
    assert len(warnings) == 1

    # Check that error_type is present in the warning record
    first_warning = warnings[0]
    assert hasattr(first_warning, "error_type")
    assert first_warning.error_type == "JSONDecodeError"

    # 3. Assert no raw chunk content appears at WARNING level
    assert "invalid json 1" not in first_warning.getMessage()

    # 4. Assert subsequent failures are logged at DEBUG
    debugs = [
        r
        for r in caplog.records
        if r.levelname == "DEBUG"
        and "stream_chunk_content_extraction_failed_subsequent" in r.getMessage()
    ]
    assert len(debugs) == 1
    assert "invalid json 2" in debugs[0].chunk_snippet

    # 5. Assert summary warning is logged
    summary_warnings = [
        r
        for r in caplog.records
        if r.levelname == "WARNING"
        and "Multiple chunks failed content extraction in stream" in r.getMessage()
    ]
    assert len(summary_warnings) == 1
    assert summary_warnings[0].total_failures == 2
