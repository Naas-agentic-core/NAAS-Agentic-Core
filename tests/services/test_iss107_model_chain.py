"""ISS-107 — اختبار سلسلة النماذج: التقدّم عند content_chunks==0.

يثبت أن نموذجاً ينتج content فارغاً (reasoning-only مثل glm-4.5-air) يُعَدّ
فشلاً فيتقدّم ``stream_chat`` للنموذج التالي بدل إرجاع إجابة فارغة («لا يجيب»).
كما يثبت تنظيف السلسلة من النماذج المُثبَت كارثيّتها حياً (2026-06-02).
"""

import pytest

from app.core.ai_config import get_ai_config
from app.core.gateway.simple_client import OpenRouterClient


class _StubSafetyNet:
    async def stream_safety_response(self):
        yield {"choices": [{"delta": {"content": "[safety]"}}]}


def _make_client():
    return OpenRouterClient(
        api_key="test",
        primary_model="model-empty",
        fallback_models=["model-good"],
        cognitive_engine=None,
        safety_net=_StubSafetyNet(),
    )


class TestEmptyAdvances:
    @pytest.mark.asyncio
    async def test_empty_model_advances_to_next(self, monkeypatch):
        """model-empty يرفع ValueError (content==0) → ينتقل لـ model-good."""
        client = _make_client()

        async def fake_stream_model(c, model_id, messages, max_tokens=None):
            if model_id == "model-empty":
                # يحاكي ما يفعله _stream_model الحقيقي عند content_chunks==0
                raise ValueError(f"empty_completion model={model_id} (content_chunks=0)")
                yield  # pragma: no cover
            yield {"choices": [{"delta": {"content": "إجابة عربية سليمة"}}]}

        monkeypatch.setattr(client, "_stream_model", fake_stream_model)
        out = "".join(
            [
                ch["choices"][0]["delta"].get("content", "")
                async for ch in client.stream_chat([{"role": "user", "content": "q"}])
            ]
        )
        assert "إجابة عربية سليمة" in out
        assert "[safety]" not in out  # لم نلجأ لشبكة الأمان

    @pytest.mark.asyncio
    async def test_all_empty_falls_to_safety_net(self, monkeypatch):
        client = _make_client()

        async def all_empty(c, model_id, messages, max_tokens=None):
            raise ValueError("empty_completion content_chunks=0")
            yield  # pragma: no cover

        monkeypatch.setattr(client, "_stream_model", all_empty)
        out = "".join(
            [
                ch.get("choices", [{}])[0].get("delta", {}).get("content", "") or ""
                async for ch in client.stream_chat([{"role": "user", "content": "q"}])
            ]
        )
        assert "[safety]" in out  # كل النماذج فشلت → شبكة الأمان


class TestChainHygiene:
    def test_broken_models_removed(self):
        """النماذج المُثبَت كارثيّتها حياً (2026-06-02) ليست في السلسلة."""
        cfg = get_ai_config()
        chain = [cfg.primary_model, *cfg.get_fallback_models()]
        joined = " ".join(chain)
        assert "trinity-large-thinking" not in joined  # 404
        assert "glm-4.5-air" not in joined  # content فارغ
        assert "nemotron-3-super-120b" not in joined  # إنجليزي في content

    def test_primary_is_verified_arabic(self):
        # ISS-130 (D-167 — 2026-07-14): gpt-oss-120b:free أُزيل من OpenRouter (404)
        # ⇒ إعادة ترقية gpt-oss-20b (تعافى من 429 — مُتحقَّق حياً عربي+LaTeX).
        cfg = get_ai_config()
        assert cfg.primary_model == "openai/gpt-oss-20b:free"
