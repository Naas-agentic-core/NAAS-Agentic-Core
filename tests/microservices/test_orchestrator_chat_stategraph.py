"""اختبارات سلوكية لمسارات chat داخل orchestrator مع عمود StateGraph."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import HTTPException
from fastapi.testclient import TestClient

from microservices.orchestrator_service.main import app
from microservices.orchestrator_service.src.api import routes


class _FakeTimelineEvent:
    """يمثل حدثًا زمنيًا بسيطًا متوافقًا مع واجهة النموذج."""

    def __init__(self, agent: str) -> None:
        self._agent = agent

    def model_dump(self, mode: str = "json") -> dict[str, str]:
        """يعيد تمثيل الحدث بصيغة قاموس JSON."""
        return {"agent": self._agent, "mode": mode}


class _FakeRunData:
    """يمثل نتيجة تشغيل مبسطة لمحاكاة LangGraph."""

    def __init__(self) -> None:
        self.run_id = "run-test"
        self.execution = {"summary": "stategraph-response"}
        self.timeline = [_FakeTimelineEvent("supervisor")]


class _FakeLangGraphService:
    """خدمة مزيفة تعيد نتيجة ثابتة للتحقق من سلوك المسارات."""

    async def run(self, payload: object) -> _FakeRunData:
        """تشغّل محاكاة وتعيد بيانات ثابتة دون تبعيات خارجية."""
        _ = payload
        return _FakeRunData()


def test_chat_http_messages_uses_stategraph(monkeypatch) -> None:
    """يتأكد أن POST /api/chat/messages يعيد استجابة موحدة من مسار StateGraph."""
    monkeypatch.setattr(routes, "create_langgraph_service", _FakeLangGraphService)

    client = TestClient(app)
    response = client.post("/api/chat/messages", json={"question": "hello"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["response"] == "stategraph-response"
    assert payload["graph_mode"] == "stategraph"


import jwt

from microservices.orchestrator_service.src.core.config import get_settings


def test_chat_ws_customer_uses_stategraph(monkeypatch) -> None:
    """يتأكد أن WS العميل يمر عبر نفس مسار StateGraph ويرجع route_id الصحيح."""
    monkeypatch.setattr(routes, "create_langgraph_service", _FakeLangGraphService)

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")
    with TestClient(app).websocket_connect(f"/api/chat/ws?token={token}") as ws:
        ws.send_json({"question": "hello"})
        payload = ws.receive_json()

    assert payload["status"] == "ok"
    assert payload["route_id"] == "chat_ws_customer"
    assert payload["graph_mode"] == "stategraph"


def test_chat_ws_admin_uses_stategraph(monkeypatch) -> None:
    """يتأكد أن WS الإداري يستخدم StateGraph ويرجع route_id الإداري."""
    monkeypatch.setattr(routes, "create_langgraph_service", _FakeLangGraphService)

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")
    with TestClient(app).websocket_connect(f"/admin/api/chat/ws?token={token}") as ws:
        ws.send_json({"question": "hello"})
        payload = ws.receive_json()

    assert payload["status"] == "ok"
    assert payload["route_id"] == "chat_ws_admin"
    assert payload["graph_mode"] == "stategraph"


def test_chat_ws_customer_mission_complex_uses_json_contract(monkeypatch) -> None:
    """يتأكد أن mission_complex على WS العميل يرسل أحداث JSON متوافقة مع الواجهة."""

    captured: dict[str, object] = {}

    async def fake_ensure_conversation(**kwargs: object) -> int:
        captured.update(kwargs)
        return 42

    async def fake_persist(**kwargs: object) -> None:
        captured["persist"] = kwargs

    async def fake_stream(
        question: str,
        context: dict[str, object],
        user_id: int,
    ) -> AsyncGenerator[dict[str, object], None]:
        captured["question"] = question
        captured["context"] = context
        captured["user_id"] = user_id
        yield {"type": "mission_created", "payload": {"mission_id": 900}}
        yield {"type": "assistant_final", "payload": {"content": "done"}}

    monkeypatch.setattr(routes, "handle_mission_complex_stream", fake_stream)
    monkeypatch.setattr(routes, "_ensure_conversation", fake_ensure_conversation)
    monkeypatch.setattr(routes, "_persist_assistant_message", fake_persist)

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")
    with TestClient(app).websocket_connect(f"/api/chat/ws?token={token}") as ws:
        ws.send_json(
            {
                "question": "run mission",
                "conversation_id": 42,
                "metadata": {"mission_type": "mission_complex"},
            }
        )
        init_event = ws.receive_json()
        mission_event = ws.receive_json()
        final_event = ws.receive_json()

    assert init_event == {"type": "conversation_init", "payload": {"conversation_id": 42}}
    assert mission_event["type"] == "mission_created"
    assert final_event["type"] == "assistant_final"
    assert isinstance(captured.get("context"), dict)
    assert captured["context"]["conversation_id"] == 42
    assert captured["context"]["mission_type"] == "mission_complex"
    assert captured["context"]["chat_scope"] == "customer"


def test_chat_ws_admin_mission_complex_normalizes_mission_type(monkeypatch) -> None:
    """يتأكد أن mission_type المباشر يصل لمسار super agent في WS الإداري."""

    captured: dict[str, object] = {}

    async def fake_ensure_conversation(**kwargs: object) -> int:
        captured.update(kwargs)
        return 77

    async def fake_persist(**kwargs: object) -> None:
        captured["persist"] = kwargs

    async def fake_stream(
        question: str,
        context: dict[str, object],
        user_id: int,
    ) -> AsyncGenerator[dict[str, object], None]:
        captured["question"] = question
        captured["context"] = context
        captured["user_id"] = user_id
        yield {"type": "assistant_error", "payload": {"content": "failed"}}

    monkeypatch.setattr(routes, "handle_mission_complex_stream", fake_stream)
    monkeypatch.setattr(routes, "_ensure_conversation", fake_ensure_conversation)
    monkeypatch.setattr(routes, "_persist_assistant_message", fake_persist)

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")
    with TestClient(app).websocket_connect(f"/admin/api/chat/ws?token={token}") as ws:
        ws.send_json(
            {
                "question": "run admin mission",
                "conversation_id": 77,
                "mission_type": "MISSION_COMPLEX",
            }
        )
        init_event = ws.receive_json()
        final_event = ws.receive_json()

    assert init_event == {"type": "conversation_init", "payload": {"conversation_id": 77}}
    assert final_event["type"] == "assistant_error"
    assert isinstance(captured.get("context"), dict)
    assert captured["context"]["conversation_id"] == 77
    assert captured["context"]["mission_type"] == "mission_complex"
    assert captured["context"]["chat_scope"] == "admin"


def test_chat_ws_mission_complex_emits_error_when_conversation_forbidden(monkeypatch) -> None:
    """يتأكد أن فشل ربط المحادثة يُرسل assistant_error بدل إسقاط جلسة WS."""

    async def fake_ensure_conversation(**kwargs: object) -> int:
        _ = kwargs
        raise HTTPException(status_code=403, detail="conversation does not belong to user")

    monkeypatch.setattr(routes, "_ensure_conversation", fake_ensure_conversation)

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")
    with TestClient(app).websocket_connect(f"/api/chat/ws?token={token}") as ws:
        ws.send_json(
            {
                "question": "mission with wrong conversation",
                "conversation_id": 999,
                "mission_type": "mission_complex",
            }
        )
        payload = ws.receive_json()

    assert payload["type"] == "assistant_error"
    assert payload["payload"]["content"] == "conversation does not belong to user"


def test_chat_ws_mission_complex_emits_fallback_terminal_error_when_stream_ends(monkeypatch) -> None:
    """يتأكد أن انتهاء بث mission_complex دون حدث نهائي ينتج assistant_error محفوظًا."""

    captured: dict[str, object] = {}

    async def fake_ensure_conversation(**kwargs: object) -> int:
        _ = kwargs
        return 55

    async def fake_persist(**kwargs: object) -> None:
        captured["persist"] = kwargs

    async def fake_stream(
        question: str,
        context: dict[str, object],
        user_id: int,
    ) -> AsyncGenerator[dict[str, object], None]:
        _ = (question, context, user_id)
        yield {"type": "mission_created", "payload": {"mission_id": 901}}

    monkeypatch.setattr(routes, "_ensure_conversation", fake_ensure_conversation)
    monkeypatch.setattr(routes, "_persist_assistant_message", fake_persist)
    monkeypatch.setattr(routes, "handle_mission_complex_stream", fake_stream)

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")
    with TestClient(app).websocket_connect(f"/api/chat/ws?token={token}") as ws:
        ws.send_json(
            {
                "question": "mission stream ends",
                "conversation_id": 55,
                "mission_type": "mission_complex",
            }
        )
        init_event = ws.receive_json()
        mission_event = ws.receive_json()
        fallback_event = ws.receive_json()

    assert init_event == {"type": "conversation_init", "payload": {"conversation_id": 55}}
    assert mission_event["type"] == "mission_created"
    assert fallback_event["type"] == "assistant_error"
    assert isinstance(captured.get("persist"), dict)
    persisted = captured["persist"]
    assert persisted["conversation_id"] == 55
    assert persisted["mission_id"] == 901
