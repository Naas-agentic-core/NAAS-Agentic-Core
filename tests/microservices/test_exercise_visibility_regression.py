"""اختبار انحدار يضمن ظهور نص التمرين للمستخدم عند تدهور مسار control-plane."""

from __future__ import annotations

import httpx
import pytest

from app.infrastructure.clients.orchestrator_client import OrchestratorClient


class _FailingClient:
    def build_request(self, *_args, **_kwargs):
        return object()

    async def send(self, *_args, **_kwargs):
        raise httpx.ConnectError("forced orchestrator outage")


@pytest.mark.asyncio
async def test_exercise_request_is_visible_on_stream(monkeypatch: pytest.MonkeyPatch) -> None:
    """يتأكد أن طلب تمرين يُرجع نصاً قابلاً للعرض مباشرة على الشاشة عند fallback المحلي."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _FailingClient()

    async def no_file_count(_question: str):
        return None

    expected_exercise_text = (
        "تمرين احتمالات: لدينا 3 كرات حمراء و5 زرقاء. احسب احتمال سحب كرة حمراء."
    )

    async def local_retrieval(_question: str):
        return expected_exercise_text

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_build_local_file_count_response", no_file_count)
    monkeypatch.setattr(client, "_build_local_retrieval_response", local_retrieval)

    rendered_chunks: list[str] = []
    async for item in client.chat_with_agent(question="أعطني تمرين الاحتمالات", user_id=1001):
        if isinstance(item, str):
            rendered_chunks.append(item)

    assert rendered_chunks
    full_text = "\n".join(rendered_chunks)
    assert "تمرين احتمالات" in full_text
    assert "احتمال سحب كرة حمراء" in full_text
