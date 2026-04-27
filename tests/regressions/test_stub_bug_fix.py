import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.main import app

client = TestClient(app)


@pytest.mark.skip(reason="Legacy monolith WS route disabled")
def test_chat_stream_is_real_implementation():
    """
    Verifies that the WebSocket chat endpoint enforces authentication.

    If a stub existed, it would accept unauthenticated connections.
    """
    with pytest.raises(WebSocketDisconnect) as exc:
        with client.websocket_connect("/admin/api/chat/ws"):
            pass

    assert exc.value.code == 4401, (
        f"Expected 4401 Unauthorized, but got {exc.value.code}. "
        "The stub implementation might still be active."
    )
