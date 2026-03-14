"""اختبارات سلوكية لضمان عقد /agent/chat عند مسار المهمة الخارقة."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator

from fastapi.testclient import TestClient

from microservices.orchestrator_service.main import app
from microservices.orchestrator_service.src.api import routes
from microservices.orchestrator_service.src.services.overmind.agents import (
    orchestrator as orch_module,
)


def test_agent_chat_mission_complex_stream_is_text_encodable(monkeypatch) -> None:
    """يتأكد أن /agent/chat يعيد chunks نصية قابلة للترميز حتى مع أحداث mission dict."""

    async def fake_mission_stream(
        question: str,
        context: dict[str, object],
        user_id: int,
    ) -> AsyncGenerator[dict[str, object], None]:
        _ = (question, context, user_id)
        yield {"type": "assistant_delta", "payload": {"content": "start"}}
        yield {"type": "assistant_final", "payload": {"content": "done"}}

    monkeypatch.setattr(orch_module, "handle_mission_complex_stream", fake_mission_stream)
    monkeypatch.setattr(routes, "get_ai_client", object)

    client = TestClient(app)
    with client.stream(
        "POST",
        "/agent/chat",
        json={
            "question": "run mission",
            "user_id": 7,
            "context": {"intent": "MISSION_COMPLEX"},
        },
    ) as response:
        assert response.status_code == 200
        chunks = [line for line in response.iter_lines() if line]

    assert chunks
    parsed = [json.loads(chunk) for chunk in chunks]
    assert parsed[0]["type"] == "assistant_delta"
    assert parsed[-1]["type"] == "assistant_final"
    assert parsed[-1]["payload"]["content"] == "done"


def test_agent_chat_admin_path_forwards_aligned_admin_state(monkeypatch) -> None:
    """يتأكد أن مسار /agent/chat الإداري يمرر حقول العقد المتوافقة مع بوابة الإدارة."""

    class FakeAdminApp:
        def __init__(self) -> None:
            self.last_inputs: dict[str, object] | None = None

        async def ainvoke(self, inputs: dict[str, object]):
            self.last_inputs = inputs
            return {"final_response": {"ok": True}}

    fake_admin = FakeAdminApp()
    app.state.admin_app = fake_admin

    client = TestClient(app)
    with client.stream(
        "POST",
        "/agent/chat",
        json={
            "question": "count python files",
            "user_id": 11,
            "context": {
                "chat_scope": "admin",
                "is_admin": True,
                "role": "admin",
                "scope": "admin:tool",
            },
        },
    ) as response:
        assert response.status_code == 200
        chunks = [line for line in response.iter_lines() if line]

    assert chunks
    assert fake_admin.last_inputs is not None
    assert fake_admin.last_inputs["query"] == "count python files"
    assert fake_admin.last_inputs["is_admin"] is True
    assert fake_admin.last_inputs["user_role"] == "admin"


def test_agent_chat_admin_path_is_fail_closed_without_admin_identity(monkeypatch) -> None:
    """يتأكد أن مسار /agent/chat الإداري لا يمرر وصولاً إدارياً ضمنياً دون إثبات."""

    class FakeAdminApp:
        def __init__(self) -> None:
            self.last_inputs: dict[str, object] | None = None

        async def ainvoke(self, inputs: dict[str, object]):
            self.last_inputs = inputs
            return {"final_response": {"ok": True}}

    fake_admin = FakeAdminApp()
    app.state.admin_app = fake_admin

    client = TestClient(app)
    with client.stream(
        "POST",
        "/agent/chat",
        json={
            "question": "count python files",
            "user_id": 12,
            "context": {"chat_scope": "admin"},
        },
    ) as response:
        assert response.status_code == 200
        _ = [line for line in response.iter_lines() if line]

    assert fake_admin.last_inputs is not None
    assert fake_admin.last_inputs["is_admin"] is False
