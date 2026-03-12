"""اختبارات التدهور العادل وتعقيم الأخطاء لعميل orchestrator."""

from __future__ import annotations

import json

import httpx
import pytest

from app.infrastructure.clients.orchestrator_client import OrchestratorClient


class _AlwaysFailClient:
    def build_request(self, *_args, **_kwargs):
        return object()

    async def send(self, *_args, **_kwargs):
        raise httpx.ConnectError("lookup orchestrator-service:8006 failed")


@pytest.mark.asyncio
async def test_user_facing_error_is_sanitized(monkeypatch: pytest.MonkeyPatch) -> None:
    """يتأكد من عدم تسريب hostnames أو المنافذ أو سلسلة المحاولات لواجهة المستخدم."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _AlwaysFailClient()

    async def no_local_fallback(_question: str):
        return None

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_build_local_file_count_response", no_local_fallback)
    monkeypatch.setattr(client, "_build_local_retrieval_response", no_local_fallback)

    chunks: list[str] = []
    async for item in client.chat_with_agent(question="أعطني تمرين الاحتمالات", user_id=1):
        if isinstance(item, str):
            chunks.append(item)

    assert len(chunks) == 1
    payload = json.loads(chunks[0])
    content = payload["payload"]["content"]

    assert "localhost" not in content
    assert "orchestrator-service" not in content
    assert ":8006" not in content
    assert "diagnostic" not in content.lower()
    assert payload["payload"].get("request_id")


@pytest.mark.asyncio
async def test_local_fallback_still_works_for_file_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """يحافظ على مسار التدهور المحلي الحالي عندما يكون السؤال من نمط عدّ الملفات."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _AlwaysFailClient()

    async def local_fallback(_question: str):
        return "عدد ملفات بايثون في المشروع هو: 10 ملف."

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_build_local_file_count_response", local_fallback)

    results: list[str] = []
    async for item in client.chat_with_agent(question="كم عدد ملفات بايثون؟", user_id=1):
        if isinstance(item, str):
            results.append(item)

    assert results == ["عدد ملفات بايثون في المشروع هو: 10 ملف."]


@pytest.mark.asyncio
async def test_local_retrieval_fallback_for_exercise_request(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يستخدم مسار الاسترجاع المحلي عند تعطل control-plane لطلب تمرين تعليمي."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _AlwaysFailClient()

    async def no_file_count(_question: str):
        return None

    async def local_retrieval(_question: str):
        return "تم العثور على تمرين الاحتمالات المطلوب من المسار المحلي."

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_build_local_file_count_response", no_file_count)
    monkeypatch.setattr(client, "_build_local_retrieval_response", local_retrieval)

    results: list[str] = []
    async for item in client.chat_with_agent(question="أعطني تمرين الاحتمالات", user_id=1):
        if isinstance(item, str):
            results.append(item)

    assert results == ["تم العثور على تمرين الاحتمالات المطلوب من المسار المحلي."]
