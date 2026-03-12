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
async def test_local_fallback_supports_generic_extension_file_count(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يتحقق أن مسار التدهور يدعم صيغ ملفات متعددة لخدمة عدّ الملفات الإدارية."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _AlwaysFailClient()

    async def fake_count_files(extension: str | None = None) -> int | None:
        if extension == "pdf":
            return 7
        return None

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_count_files_in_project", fake_count_files)

    results: list[str] = []
    async for item in client.chat_with_agent(question="احسب عدد ملفات pdf", user_id=1):
        if isinstance(item, str):
            results.append(item)

    assert results == ["عدد الملفات بامتداد .pdf في المشروع هو: 7 ملف."]


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


@pytest.mark.asyncio
async def test_local_fallback_can_be_disabled_with_flag(monkeypatch: pytest.MonkeyPatch) -> None:
    """يعطل fallback المحلي عند تفعيل العلم لضمان تحكم تشغيل آمن أثناء الـ canary."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    monkeypatch.setenv("ORCHESTRATOR_LOCAL_FALLBACK_ENABLED", "0")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _AlwaysFailClient()

    async def local_fallback(_question: str):
        return "عدد ملفات بايثون في المشروع هو: 99 ملف."

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_build_local_file_count_response", local_fallback)
    monkeypatch.setattr(client, "_build_local_retrieval_response", local_fallback)

    chunks: list[str] = []
    async for item in client.chat_with_agent(question="كم عدد ملفات بايثون؟", user_id=1):
        if isinstance(item, str):
            chunks.append(item)

    assert len(chunks) == 1
    payload = json.loads(chunks[0])
    assert payload["type"] == "assistant_error"


@pytest.mark.asyncio
async def test_local_fallback_supports_csv_and_json_file_count(monkeypatch: pytest.MonkeyPatch) -> None:
    """يتحقق من دعم CSV/JSON كصيغ مطلوبة ضمن ذكاء الملفات الإداري."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _AlwaysFailClient()

    async def fake_count_files(extension: str | None = None) -> int | None:
        mapping = {"csv": 11, "json": 5}
        return mapping.get(extension)

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_count_files_in_project", fake_count_files)

    csv_results: list[str] = []
    async for item in client.chat_with_agent(question="count csv files", user_id=2):
        if isinstance(item, str):
            csv_results.append(item)

    json_results: list[str] = []
    async for item in client.chat_with_agent(question="احسب عدد ملفات json", user_id=2):
        if isinstance(item, str):
            json_results.append(item)

    assert csv_results == ["عدد الملفات بامتداد .csv في المشروع هو: 11 ملف."]
    assert json_results == ["عدد الملفات بامتداد .json في المشروع هو: 5 ملف."]


@pytest.mark.asyncio
async def test_unsupported_extension_returns_sanitized_error_when_count_fails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """يضمن أن الامتدادات غير المدعومة لا تعطي نجاحًا كاذبًا وتعود بخطأ آمن."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _AlwaysFailClient()

    async def failed_count(extension: str | None = None) -> int | None:
        return None

    async def no_retrieval(_question: str):
        return None

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_count_files_in_project", failed_count)
    monkeypatch.setattr(client, "_build_local_retrieval_response", no_retrieval)

    chunks: list[str] = []
    async for item in client.chat_with_agent(question="احسب عدد ملفات xlsx", user_id=2):
        if isinstance(item, str):
            chunks.append(item)

    payload = json.loads(chunks[-1])
    assert payload["type"] == "assistant_error"


@pytest.mark.asyncio
async def test_normalize_stream_event_sanitizes_topology_tokens() -> None:
    """يتحقق أن event normalization يمنع تسريب localhost وhost.docker للمستخدم."""
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    event = {
        "type": "assistant_error",
        "payload": {
            "content": "failed via host.docker.internal and localhost:8006",
            "details": "diagnostic: orchestrator-service unreachable",
        },
    }

    normalized = client._normalize_stream_event(event)
    payload = normalized["payload"]
    assert "localhost" not in str(payload.get("content", "")).lower()
    assert "host.docker.internal" not in str(payload.get("content", "")).lower()
    assert "orchestrator-service" not in str(payload.get("details", "")).lower()


def test_multi_target_candidates_disabled_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """يفرض مرشح URL وحيد افتراضيًا لمنع split-brain إلا في وضع breakglass."""
    monkeypatch.setenv("ORCHESTRATOR_SERVICE_FALLBACK_URLS", "http://a:1,http://b:2")
    monkeypatch.delenv("ORCHESTRATOR_ALLOW_MULTI_TARGET_CHAT", raising=False)

    client = OrchestratorClient(base_url="http://orchestrator-service:8006")
    candidates = client._build_chat_url_candidates()

    assert candidates == ["http://orchestrator-service:8006/agent/chat"]


def test_multi_target_candidates_enabled_only_in_breakglass(monkeypatch: pytest.MonkeyPatch) -> None:
    """يسمح بتعدد المرشحات فقط عند تفعيل breakglass صراحة."""
    monkeypatch.setenv("ORCHESTRATOR_ALLOW_MULTI_TARGET_CHAT", "1")
    monkeypatch.setenv(
        "ORCHESTRATOR_SERVICE_FALLBACK_URLS",
        "http://orchestrator-service:8006,http://backup-orchestrator:8016",
    )

    client = OrchestratorClient(base_url="http://orchestrator-service:8006")
    candidates = client._build_chat_url_candidates()

    assert candidates == [
        "http://orchestrator-service:8006/agent/chat",
        "http://backup-orchestrator:8016/agent/chat",
    ]


@pytest.mark.asyncio
async def test_file_intelligence_fallback_concurrency_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """اختبار smoke للتوازي: يحافظ fallback على الاستجابة المتوقعة تحت طلبات متزامنة."""
    import asyncio

    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _AlwaysFailClient()

    async def fake_count_files(extension: str | None = None) -> int | None:
        return 3 if extension == "pdf" else None

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_count_files_in_project", fake_count_files)

    async def run_once() -> str:
        items: list[str] = []
        async for item in client.chat_with_agent(question="count pdf files", user_id=9):
            if isinstance(item, str):
                items.append(item)
        return items[-1]

    results = await asyncio.gather(*[run_once() for _ in range(8)])
    assert all(result == "عدد الملفات بامتداد .pdf في المشروع هو: 3 ملف." for result in results)


@pytest.mark.asyncio
async def test_exercise_retrieval_fallback_concurrency_smoke(monkeypatch: pytest.MonkeyPatch) -> None:
    """اختبار smoke للتوازي: degraded retrieval يبقى متسقًا عبر الطلبات المتزامنة."""
    import asyncio

    monkeypatch.setenv("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006")
    client = OrchestratorClient(base_url="http://orchestrator-service:8006")

    async def fake_get_client():
        return _AlwaysFailClient()

    async def no_file_count(_question: str):
        return None

    async def local_retrieval(_question: str):
        return "تم العثور على تمرين محلي."

    monkeypatch.setattr(client, "_get_client", fake_get_client)
    monkeypatch.setattr(client, "_build_local_file_count_response", no_file_count)
    monkeypatch.setattr(client, "_build_local_retrieval_response", local_retrieval)

    async def run_once() -> str:
        items: list[str] = []
        async for item in client.chat_with_agent(question="أعطني تمرين تكامل", user_id=9):
            if isinstance(item, str):
                items.append(item)
        return items[-1]

    results = await asyncio.gather(*[run_once() for _ in range(8)])
    assert all(result == "تم العثور على تمرين محلي." for result in results)
