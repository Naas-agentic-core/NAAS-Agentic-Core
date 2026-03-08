"""اختبارات سلوكية لمسارات chat داخل orchestrator مع عمود StateGraph."""

from __future__ import annotations

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

    state: typing.ClassVar[dict] = {
        "execution": {"results": [{"result": "stategraph-response"}]},
        "answer": "stategraph-response",
        "timeline": [{"agent": "supervisor", "payload": {}}],
    }


class _FakeEngine:
    async def run(self, **kwargs) -> _FakeRunData:
        # Check if observer is passed and call it
        observer = kwargs.get("observer")
        if observer:
            await observer("phase_start", {"phase": "FAKE_PHASE"})
        return _FakeRunData()


class _FakeLangGraphService:
    """خدمة مزيفة تعيد نتيجة ثابتة للتحقق من سلوك المسارات."""

    def __init__(self):
        self.engine = _FakeEngine()

    async def run(self, payload: object) -> _FakeRunData:
        """تشغّل محاكاة وتعيد بيانات ثابتة دون تبعيات خارجية."""
        _ = payload
        return _FakeRunData()


def test_chat_http_messages_uses_stategraph(monkeypatch) -> None:
    """يتأكد أن POST /api/chat/messages يعيد استجابة موحدة من مسار StateGraph."""

    class FakeGraph:
        async def ainvoke(self, *args, **kwargs):
            return {"final_response": "stategraph-response"}

    def _fake_create_unified_graph():
        return FakeGraph()

    monkeypatch.setattr(routes, "create_unified_graph", _fake_create_unified_graph)

    client = TestClient(app)
    response = client.post("/api/chat/messages", json={"question": "hello"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["response"] == "stategraph-response"
    assert payload["graph_mode"] == "unified_stategraph"


import typing

import jwt

from microservices.orchestrator_service.src.core.config import get_settings


def test_chat_ws_customer_uses_stategraph(monkeypatch) -> None:
    """يتأكد أن WS العميل يمر عبر نفس مسار StateGraph ويرجع route_id الصحيح."""

    class FakeGraph:
        async def ainvoke(self, *args, **kwargs):
            return {"final_response": "Fake Graph WS Result"}

    def _fake_create_unified_graph():
        return FakeGraph()

    monkeypatch.setattr(routes, "create_unified_graph", _fake_create_unified_graph)

    async def fake_ensure_conversation(**kwargs):
        return 123

    monkeypatch.setattr(routes, "_ensure_conversation", fake_ensure_conversation)

    async def fake_persist_assistant_message(**kwargs):
        pass

    monkeypatch.setattr(routes, "_persist_assistant_message", fake_persist_assistant_message)

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")
    with TestClient(app).websocket_connect(f"/api/chat/ws?token={token}") as ws:
        ws.send_json({"question": "hello"})
        init_event = ws.receive_json()
        assert init_event["type"] == "conversation_init"
        assert init_event["payload"]["conversation_id"] == 123

        while True:
            evt = ws.receive_json()
            if evt["type"] == "assistant_final":
                assert evt["payload"]["content"] == "Fake Graph WS Result"
                assert evt["payload"]["route_id"] == "chat_ws_customer"
                assert evt["payload"]["graph_mode"] == "unified_stategraph"
                break


def test_chat_ws_admin_uses_stategraph(monkeypatch) -> None:
    """يتأكد أن WS الإداري يستخدم StateGraph ويرجع route_id الإداري."""

    class FakeGraph:
        async def ainvoke(self, *args, **kwargs):
            return {"final_response": "Fake Graph Admin WS Result"}

    def _fake_create_unified_graph():
        return FakeGraph()

    monkeypatch.setattr(routes, "create_unified_graph", _fake_create_unified_graph)

    async def fake_ensure_conversation(**kwargs):
        return 456

    monkeypatch.setattr(routes, "_ensure_conversation", fake_ensure_conversation)

    async def fake_persist_assistant_message(**kwargs):
        pass

    monkeypatch.setattr(routes, "_persist_assistant_message", fake_persist_assistant_message)

    token = jwt.encode({"sub": "1", "user_id": 1}, get_settings().SECRET_KEY, algorithm="HS256")
    with TestClient(app).websocket_connect(f"/admin/api/chat/ws?token={token}") as ws:
        ws.send_json({"question": "hello"})
        init_event = ws.receive_json()
        assert init_event["type"] == "conversation_init"
        assert init_event["payload"]["conversation_id"] == 456

        while True:
            evt = ws.receive_json()
            if evt["type"] == "assistant_final":
                assert evt["payload"]["content"] == "Fake Graph Admin WS Result"
                assert evt["payload"]["route_id"] == "chat_ws_admin"
                assert evt["payload"]["graph_mode"] == "unified_stategraph"
                break
