"""ISS-200 (D-288) — عميل LLM الخاص بالـ orchestrator: سلسلة سقوط حقيقية.

المسار الذي كان مكسوراً: `services/llm/client.py` كان يرسل كل طلب إلى PRIMARY
وحده. وحين أوقفت OpenRouter خدمة النموذج المُصلَّب (`"endpoints": []`) مات كل دور
دردشة بلا أي محاولة تالية، وأُجيب الطالب بسطر جاهز. هذه الاختبارات تُثبِت:

1. السلسلة تُبنى من `ai_config` (لا حرفيات في العميل) وتُتبع تجاوزات المُشغِّل.
2. نموذجٌ يفشل ⇒ الدوران إلى التالي، والمحتوى الذي وصل للطالب لا يتكرّر.
3. نموذجٌ «reasoning-only» (content=0) يُتجاوَز — حارس D-067.
4. السلسلة كلها ميتة ⇒ `AllModelsFailedError` (حالة تشغيل، لا إجابة).
5. `OPENROUTER_BASE_URL` يوجّه العميل (بوابة/وكيل/ازدواج اختبار).
"""

from __future__ import annotations

import ast
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from openai import APIConnectionError, APIStatusError

from microservices.orchestrator_service.src.services.llm.client import (
    DEFAULT_BASE_URL,
    AIClient,
    AllModelsFailedError,
)

# ── بدائل خفيفة: مزوّد OpenAI-compatible مزيف ─────────────────────────────────


def _chunk(text: str | None) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


class _Stream:
    """يمشي مع `async for chunk in stream`، ويرمي الاستثناء المضمّن حين يبلّغه."""

    def __init__(self, chunks: list[Any]) -> None:
        self._chunks = list(chunks)

    def __aiter__(self) -> _Stream:
        return self

    async def __anext__(self) -> Any:
        if not self._chunks:
            raise StopAsyncIteration
        item = self._chunks.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def _status_error(model: str, status: int = 404) -> APIStatusError:
    request = httpx.Request("POST", f"{DEFAULT_BASE_URL}/chat/completions")
    # `response` يحمل الـ request — لا يُمرَّر مرتين (توقيع openai>=1).
    response = httpx.Response(status, request=request)
    return APIStatusError(
        f"No endpoints found for model '{model}'.",
        response=response,
        body=None,
    )


def _conn_error() -> APIConnectionError:
    return APIConnectionError(request=httpx.Request("POST", DEFAULT_BASE_URL))


class _FakeCompletions:
    def __init__(self, behaviours: dict[str, Any]) -> None:
        self._behaviours = behaviours
        self.calls: list[str] = []

    async def create(self, **kwargs: Any) -> Any:
        model = str(kwargs.get("model"))
        self.calls.append(model)
        behaviour = self._behaviours.get(model, _status_error(model))
        if isinstance(behaviour, Exception):
            raise behaviour
        if kwargs.get("stream"):
            return _Stream(behaviour if isinstance(behaviour, list) else [behaviour])
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=str(behaviour)))]
        )


def _client(
    behaviours: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> tuple[AIClient, _FakeCompletions]:
    """عميل حقيقي البنية بمزوّد مزيّف — من دون لمس `ai_config` (مصدر القرار)."""
    client = AIClient.__new__(AIClient)
    completions = _FakeCompletions(behaviours)
    client.client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
    client.default_model = "test/primary:free"
    client.first_token_timeout = 5.0
    client.last_model = None
    client.base_url = DEFAULT_BASE_URL
    client.timeout = 5.0
    monkeypatch.setattr(client, "model_chain", lambda: list(behaviours))
    return client, completions


_MESSAGES = [{"role": "user", "content": "اشرح قانون نيوتن الثاني"}]


class TestModelChainResolution:
    def test_chain_is_primary_then_fallbacks_without_duplicates(self, monkeypatch) -> None:
        client = AIClient.__new__(AIClient)
        client.default_model = "test/primary:free"
        fake_config = SimpleNamespace(
            get_fallback_models=lambda: ["test/fb1:free", "test/primary:free", "test/fb2:free"]
        )
        monkeypatch.setattr(
            "microservices.orchestrator_service.src.services.llm.client.get_ai_config",
            lambda: fake_config,
        )
        assert client.model_chain() == ["test/primary:free", "test/fb1:free", "test/fb2:free"]

    def test_client_holds_no_model_literals(self) -> None:
        """البوابة `check_model_client_literals` تحرس هذا بعينه: الحرفية في الملفّ
        الثالث الذي يحمل نفس القرار هي ما أنتج ISS-157 ثم ISS-200."""
        src = Path("microservices/orchestrator_service/src/services/llm/client.py").read_text(
            encoding="utf-8"
        )
        literals = [
            node.value
            for node in ast.walk(ast.parse(src))
            if isinstance(node, ast.Constant)
            and isinstance(node.value, str)
            and "/" in node.value
            and ":free" in node.value
            and " " not in node.value
        ]
        assert not literals, f"حرفية نموذج في العميل: {literals}"


class TestStreamRotation:
    async def test_dead_primary_rotates_to_next_model(self, monkeypatch) -> None:
        client, completions = _client(
            {
                "test/primary:free": _status_error("test/primary:free"),
                "test/fb1:free": [_chunk("قانون نيوتن الثاني: "), _chunk("F = ma")],
            },
            monkeypatch,
        )
        out = [c async for c in client.stream_chat(_MESSAGES)]
        joined = "".join(c.choices[0].delta.content for c in out)
        assert joined.startswith("قانون نيوتن")
        assert completions.calls == ["test/primary:free", "test/fb1:free"]
        assert client.last_model == "test/fb1:free"

    async def test_reasoning_only_model_is_skipped(self, monkeypatch) -> None:
        """content=0 = فشل، لا إجابة فارغة (D-067 — كارثة «pepepe»)."""
        client, completions = _client(
            {
                "test/primary:free": [_chunk(None), _chunk(None)],
                "test/fb1:free": [_chunk("إجابة عربية صحيحة")],
            },
            monkeypatch,
        )
        out = [c async for c in client.stream_chat(_MESSAGES)]
        assert out and "إجابة" in out[0].choices[0].delta.content
        assert completions.calls == ["test/primary:free", "test/fb1:free"]

    async def test_midstream_failure_does_not_restart_answer(self, monkeypatch) -> None:
        """بثّ النموذج نصف إجابة ثم سقط: نُنهي الدور بما وصل، لا نلصق إجابتين."""
        client, completions = _client(
            {
                "test/primary:free": [_chunk("بداية الإجابة "), _conn_error()],
                "test/fb1:free": [_chunk("نصّ ثانوي يجب ألا يظهر")],
            },
            monkeypatch,
        )
        out = [c async for c in client.stream_chat(_MESSAGES)]
        assert [c.choices[0].delta.content for c in out] == ["بداية الإجابة "]
        assert completions.calls == ["test/primary:free"]

    async def test_whole_chain_dead_raises_instead_of_fake_answer(self, monkeypatch) -> None:
        client, _ = _client(
            {
                "test/primary:free": _status_error("test/primary:free"),
                "test/fb1:free": _conn_error(),
            },
            monkeypatch,
        )
        with pytest.raises(AllModelsFailedError) as exc:
            _ = [c async for c in client.stream_chat(_MESSAGES)]
        assert exc.value.models == ["test/primary:free", "test/fb1:free"]
        # الحالة التشغيلية تُسمّي نفسها: «no endpoints» يجب أن تُقرأ في السجلّ
        assert "No endpoints" in str(exc.value)

    async def test_auth_error_does_not_rotate(self, monkeypatch) -> None:
        """401 مشكلة مفتاح، لا مشكلة توجيه: الدوران فوق 6 نماذج يضاعف التعليق فقط."""
        client, completions = _client(
            {"test/primary:free": _status_error("test/primary:free", 401)}, monkeypatch
        )
        with pytest.raises(APIStatusError):
            _ = [c async for c in client.stream_chat(_MESSAGES)]
        assert completions.calls == ["test/primary:free"]


class TestGenerateRotation:
    async def test_generate_rotates_and_returns_response(self, monkeypatch) -> None:
        client, completions = _client(
            {
                "test/primary:free": _status_error("test/primary:free"),
                "test/fb1:free": "شرح مختصر",
            },
            monkeypatch,
        )
        resp = await client.generate(messages=_MESSAGES)
        assert resp.choices[0].message.content == "شرح مختصر"
        assert completions.calls == ["test/primary:free", "test/fb1:free"]

    async def test_explicit_model_bypasses_chain(self, monkeypatch) -> None:
        """مُستدعٍ يحدّد نموذجاً صراحةً يبقى على سلوكه القديم: استثناءٌ واحد بلا دوران."""
        client, completions = _client({"custom/model": _status_error("custom/model")}, monkeypatch)
        with pytest.raises(APIStatusError):
            await client.generate(model="custom/model", messages=_MESSAGES)
        assert completions.calls == ["custom/model"]


class TestSettingsWiring:
    def test_base_url_env_override_is_honoured(self, monkeypatch) -> None:
        """لا يُختبر المسار بلا مقبض base URL — وهذا المقبض هو ما عجز تشخيصُ ISS-200 بدونه."""
        monkeypatch.setenv("OPENROUTER_BASE_URL", "http://127.0.0.1:8100/api/v1")
        monkeypatch.setenv("OPENROUTER_API_KEY", "sk-or-test")
        from microservices.orchestrator_service.src.core.config import get_settings

        get_settings.cache_clear()
        try:
            client = AIClient()
            assert client.base_url == "http://127.0.0.1:8100/api/v1"
        finally:
            get_settings.cache_clear()

    def test_health_snapshot_reports_chain(self, monkeypatch) -> None:
        client = AIClient.__new__(AIClient)
        client.default_model = "test/primary:free"
        client.last_model = "test/fb1:free"
        client.base_url = DEFAULT_BASE_URL
        client.timeout = 45.0
        client.first_token_timeout = 30.0
        monkeypatch.setattr(
            AIClient, "model_chain", lambda *_: ["test/primary:free", "test/fb1:free"]
        )
        snap = client.health_snapshot()
        assert snap["primary"] == "test/primary:free"
        assert snap["last_serving_model"] == "test/fb1:free"
        assert len(snap["chain"]) == 2
