"""اختبارات سلوكية لضمان عقد /agent/chat عند مسار المهمة الخارقة."""

from __future__ import annotations

from collections.abc import AsyncGenerator
import json

from fastapi.testclient import TestClient

from microservices.orchestrator_service.main import app
from microservices.orchestrator_service.src.api import routes
from microservices.orchestrator_service.src.services.overmind.agents import orchestrator as orch_module


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
    monkeypatch.setattr(routes, "get_ai_client", lambda: object())

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
