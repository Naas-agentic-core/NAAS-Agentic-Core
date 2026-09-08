import asyncio
import json
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocket

from app.api.routers.ws_proxy import _proxy_websocket

# Provide a stub for the invalid status exception if not present
try:
    from websockets.exceptions import InvalidStatus as InvalidStatusError
except ImportError:
    class InvalidStatusError(Exception):
        pass

@pytest.fixture
def mock_client_ws():
    ws = AsyncMock(spec=WebSocket)
    # Fast paths out of wait
    ws.receive_text.side_effect = asyncio.CancelledError()
    return ws


@pytest.fixture
def mock_websockets_connect(monkeypatch):
    connect_mock = MagicMock()
    context_mgr = AsyncMock()
    connect_mock.return_value = context_mgr

    # mock upstream_ws inside the context
    upstream_ws = AsyncMock()
    context_mgr.__aenter__.return_value = upstream_ws

    monkeypatch.setattr("app.api.routers.ws_proxy.websockets.connect", connect_mock)

    return connect_mock, upstream_ws


@pytest.mark.asyncio
async def test_html_bleed_detection_in_message_loop(
    mock_client_ws, mock_websockets_connect, caplog
):
    """
    Test that the HTML bleed detector correctly intercepts HTML messages,
    sends the proper error, and closes the client connection.
    """
    caplog.set_level(logging.ERROR)

    _connect_mock, upstream_ws = mock_websockets_connect

    # In order to trigger the tasks, we need client_to_upstream to exit cleanly
    # so we don't just hang or cancel upstream_to_client immediately
    # Let's mock receive_text to block until cancelled
    async def infinite_receive():
        await asyncio.sleep(1)
        raise asyncio.CancelledError()
    mock_client_ws.receive_text.side_effect = infinite_receive

    # Create an async generator that yields an HTML bleed message
    async def message_generator():
        yield '   <HTML><head><title>500 Internal Server Error</title></head><body>error</body></html>   '
        await asyncio.sleep(1)

    upstream_ws.__aiter__.side_effect = message_generator

    await _proxy_websocket(mock_client_ws, "ws://localhost:8003/chat", ["jwt"])
    # give tasks a moment to complete
    await asyncio.sleep(0.1)

    # Verify that the structured error was sent
    mock_client_ws.send_text.assert_called_with(
        json.dumps(
            {
                "type": "error",
                "payload": {
                    "code": "WS_HTML_BLEED",
                    "details": "Upstream returned HTML instead of JSON",
                },
            }
        )
    )

    # Verify client connection was closed with code 1011
    mock_client_ws.close.assert_called_with(code=1011)

    # Verify logger snippet contains title
    assert "ws_proxy.html_bleed_intercepted snippet=title='500 Internal Server Error'" in caplog.text


@pytest.mark.asyncio
async def test_html_bleed_detection_in_invalid_status(
    mock_client_ws, mock_websockets_connect, caplog
):
    """
    Test that an InvalidStatusError exception with an HTML body is caught
    and converted to a structured error correctly.
    """
    caplog.set_level(logging.ERROR)

    connect_mock, _upstream_ws = mock_websockets_connect

    # Create a mock exception with response body
    class MockResponse:
        status_code = 500
        body = b'<!DOCTYPE html>\n<html><body>500 Error</body></html>'

    class MockInvalidStatusError(Exception):
        response = MockResponse()
        status_code = 500

    # Ensure the code treats this mock as the imported InvalidStatusError
    # Since we are mocking websockets.connect, we just raise the mock exception
    connect_mock.side_effect = MockInvalidStatusError("Invalid status")

    # We also need to patch InvalidStatusError inside ws_proxy to be MockInvalidStatusError
    import app.api.routers.ws_proxy
    original_invalid_status = getattr(app.api.routers.ws_proxy, "InvalidStatusError", None) or app.api.routers.ws_proxy.InvalidStatus
    app.api.routers.ws_proxy.InvalidStatus = MockInvalidStatusError
    app.api.routers.ws_proxy.InvalidStatusError = MockInvalidStatusError

    try:
        await _proxy_websocket(mock_client_ws, "ws://localhost:8003/chat", ["jwt"])
    finally:
        app.api.routers.ws_proxy.InvalidStatus = original_invalid_status

    # Verify that the structured error was sent
    mock_client_ws.send_text.assert_called_with(
        json.dumps(
            {
                "type": "error",
                "payload": {
                    "code": "WS_HTML_BLEED",
                    "details": "Upstream returned HTML instead of JSON",
                },
            }
        )
    )

    # Verify client connection was closed with code 1011
    mock_client_ws.close.assert_called_with(code=1011)


@pytest.mark.asyncio
async def test_html_bleed_various_payloads(
    mock_client_ws, mock_websockets_connect, caplog
):
    """
    Test other payload combinations that should trigger the bleed detection
    """
    _connect_mock, upstream_ws = mock_websockets_connect

    payloads = [
        ' {"foo": "bar"} \n <body ... ',
        '<!Doctype html><html>',
        '   <HEAD><title>err</title></head>',
    ]

    for payload in payloads:
        mock_client_ws.reset_mock()

        async def infinite_receive():
            await asyncio.sleep(1)
            raise asyncio.CancelledError()
        mock_client_ws.receive_text.side_effect = infinite_receive

        async def message_generator(p=payload):
            yield p
            await asyncio.sleep(1)

        upstream_ws.__aiter__.side_effect = message_generator

        await _proxy_websocket(mock_client_ws, "ws://localhost:8003/chat", ["jwt"])
        await asyncio.sleep(0.1)

        mock_client_ws.send_text.assert_called()
        args = mock_client_ws.send_text.call_args[0][0]
        assert "WS_HTML_BLEED" in args
        mock_client_ws.close.assert_called_with(code=1011)
