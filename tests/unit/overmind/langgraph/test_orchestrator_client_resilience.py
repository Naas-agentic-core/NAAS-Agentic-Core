import json

import httpx
import pytest

from app.infrastructure.clients.orchestrator_client import OrchestratorClient


class _AlwaysFailClient:
    """عميل مزيف يفشل دائماً لمحاكاة انقطاع الشبكة عن خدمة orchestrator."""

    def build_request(self, method: str, url: str, json: dict[str, object]) -> httpx.Request:
        return httpx.Request(method, url, json=json)

    async def send(self, request: httpx.Request, stream: bool = False) -> httpx.Response:
        raise httpx.ConnectError("network down", request=request)


@pytest.mark.asyncio
async def test_build_chat_url_candidates_prefers_local_then_container(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يتحقق من أولوية مسار localhost ثم مسارات Docker الاحتياطية في بناء endpoints."""
    monkeypatch.delenv("ORCHESTRATOR_SERVICE_FALLBACK_URLS", raising=False)
    client = OrchestratorClient(base_url="http://localhost:8006")

    candidates = client._build_chat_url_candidates()

    assert candidates[0] == "http://localhost:8006/agent/chat"
    assert "http://orchestrator-service:8006/agent/chat" in candidates
    assert "http://host.docker.internal:8006/agent/chat" in candidates


@pytest.mark.asyncio
async def test_chat_with_agent_returns_file_count_on_connectivity_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يثبت سلوك الطوارئ: عند تعذر الاتصال تُعاد نتيجة عدد ملفات بايثون كنص قابل للعرض."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_FALLBACK_URLS", "http://extra-host:9000")
    client = OrchestratorClient(base_url="http://localhost:8006")

    async def _fake_get_client() -> _AlwaysFailClient:
        return _AlwaysFailClient()

    monkeypatch.setattr(client, "_get_client", _fake_get_client)

    events: list[dict[str, object] | str] = []
    async for event in client.chat_with_agent("كم عدد ملفات بايثون في المشروع؟", user_id=1):
        events.append(event)

    assert len(events) == 1
    assert isinstance(events[0], str)
    assert "عدد ملفات بايثون في المشروع هو" in events[0]
    assert "وضع الطوارئ المحلي" in events[0]


@pytest.mark.asyncio
async def test_chat_with_agent_returns_structured_error_for_other_questions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يضمن بقاء مسار الخطأ المنظم للأسئلة العامة التي لا تندرج ضمن عدّ الملفات."""
    client = OrchestratorClient(base_url="http://localhost:8006")

    async def _fake_get_client() -> _AlwaysFailClient:
        return _AlwaysFailClient()

    monkeypatch.setattr(client, "_get_client", _fake_get_client)

    events: list[dict[str, object] | str] = []
    async for event in client.chat_with_agent("مرحباً", user_id=1):
        events.append(event)

    assert len(events) == 1
    payload = json.loads(events[0])
    assert payload["type"] == "assistant_error"
    assert "تعذر الوصول إلى خدمة الوكيل" in payload["payload"]["content"]
