from unittest.mock import patch

from fastapi.testclient import TestClient

from microservices.conversation_service.main import app


@patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"})
def test_conversation_ws_customer_envelope_shape():
    client = TestClient(app)
    with client.websocket_connect("/api/chat/ws") as ws:
        # 1. Expect CONVERSATION_INIT
        init_event = ws.receive_json()
        assert init_event["type"] == "conversation_init"
        assert "payload" in init_event

        ws.send_json({"question": "hello"})

        # 2. Expect ASSISTANT_DELTA (normalized payload)
        response_event = ws.receive_json()
        assert response_event["type"] == "assistant_delta"
        assert "payload" in response_event
        # The content should be the json dumped dict of _response_envelope, because we disabled unified proto by default?
        # Let's check what normalize_streaming_event does when unified protocol is disabled vs enabled.
        # It's an integration test, we verify shape.

        # 3. Expect COMPLETE
        complete_event = ws.receive_json()
        assert complete_event["type"] == "complete"
        assert "payload" in complete_event


@patch.dict("os.environ", {"CHAT_USE_UNIFIED_EVENT_ENVELOPE": "1"})
def test_conversation_ws_admin_envelope_shape():
    client = TestClient(app)
    with client.websocket_connect("/admin/api/chat/ws") as ws:
        init_event = ws.receive_json()
        assert init_event["type"] == "conversation_init"
        assert "payload" in init_event

        ws.send_json({"question": "hello admin"})

        response_event = ws.receive_json()
        assert response_event["type"] == "assistant_delta"
        assert "payload" in response_event

        complete_event = ws.receive_json()
        assert complete_event["type"] == "complete"
        assert "payload" in complete_event


def test_conversation_ws_schema_validation_active_in_non_prod():
    # If ENV is not set to "production", it should validate schema and pass if correct
    client = TestClient(app)
    # We monkeypatch the os.getenv inside the function via patch if needed,
    # but ENV="development" is default.
    with patch("os.getenv", return_value="development"):
        with client.websocket_connect("/api/chat/ws") as ws:
            init = ws.receive_json()
            assert init["type"] == "conversation_init"


def test_conversation_ws_error_envelope_shape():
    client = TestClient(app)

    # We patch _response_envelope to raise an Exception to test the error block
    with patch("microservices.conversation_service.main._response_envelope", side_effect=ValueError("Boom")):
        with client.websocket_connect("/api/chat/ws") as ws:
            init_event = ws.receive_json()
            assert init_event["type"] == "conversation_init"

            ws.send_json({"question": "hello"})

            error_event = ws.receive_json()
            assert error_event["type"] == "assistant_error"
            assert "payload" in error_event
            assert error_event["payload"]["details"] == "Internal Server Error"
