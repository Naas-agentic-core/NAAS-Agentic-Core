"""AI Client for Orchestrator Service.
Provides a simple interface to OpenAI-compatible LLMs.

ISS-200 (D-288 — 2026-09-09): this client used to send every request to
``ActiveModels.PRIMARY`` and nothing else. Two failures compounded there:

1. **No fallback chain.** The monolith gateway
   (``app/core/gateway/simple_client.py``) rotates over ``[PRIMARY, FALLBACK_1..5]``
   and skips a model that 404s / 429s / returns ``content=None``. This client —
   the one the live chat graph actually calls
   (``services/overmind/graph/general_knowledge.py``, ``.../graph/search.py``) —
   did not. When OpenRouter stopped serving the pinned free model
   (``"endpoints": []``), *every* student turn died here while CI stayed green,
   because ``live-e2e.yml`` overrides PRIMARY through ``OPENROUTER_PRIMARY_MODEL``.
2. **The base URL was hardcoded**, so the chain could not be repointed at a
   gateway/proxy (or a test double) without editing source.

The client now rotates the same canonical chain the parity gate guards, reads the
base URL from the ``OPENROUTER_BASE_URL`` Settings field, and raises
:class:`AllModelsFailedError`
when the whole chain is exhausted — so a caller can report an outage instead of
answering a student with a canned line. **No model id is spelled out here**: the
single source of truth stays in ``ai_config``/``shared.ai_models.model_chain``
(gates: ``check_model_client_literals``, ``check_model_chain_parity``).
"""

import logging
import os
import time
from collections.abc import AsyncGenerator
from typing import Any

from openai import APIConnectionError, APIError, APITimeoutError, AsyncOpenAI, OpenAI
from openai.types.chat import ChatCompletionChunk

from microservices.orchestrator_service.src.core.ai_config import ActiveModels, get_ai_config
from microservices.orchestrator_service.src.core.config import get_settings

logger = logging.getLogger("ai-client")

#: Default OpenRouter surface. The *override knob* is a Settings field (D-270 L5: one
# home per programmatic identifier), so this module never re-declares the env name.
DEFAULT_BASE_URL = "https://openrouter.ai/api/v1"

#: Bound a model that connects but never produces content (monolith D-177 analogue:
#: an empty/slow model must not hold the turn for the whole socket timeout).
FIRST_TOKEN_TIMEOUT_ENV = "ORCHESTRATOR_LLM_FIRST_TOKEN_TIMEOUT"
DEFAULT_FIRST_TOKEN_TIMEOUT = 30.0

#: Statuses worth rotating away from immediately — a dead/rate-limited/unavailable
#: model is a routing problem, not a reason to fail the turn.
# 401/403 (مفتاح خاطئ أو صلاحية) لا تدور: كل نموذج سيفشل بنفس السبب ⇒ ارفع فوراً.
_RETRY_AS_FALLBACK_STATUS = frozenset({402, 404, 406, 408, 409, 413, 425, 429, 500, 502, 503, 504})


class AllModelsFailedError(RuntimeError):
    """كل نماذج السلسلة فشلت.

    يُرفع بدلاً من إرجاع نصٍّ جاهز: «تعذّر التوليد» حالةُ تشغيلٍ يجب أن يراها
    المُشغِّل (وإطار خطأ للعميل)، لا إجابة تُنسَب للمحتوى.
    """

    def __init__(self, attempts: list[tuple[str, str]]) -> None:
        self.attempts = list(attempts)
        detail = (
            ", ".join(f"{model}→{error}" for model, error in self.attempts)
            or "no models configured"
        )
        super().__init__(f"all models in chain failed: {detail}")
        self.models = [model for model, _ in self.attempts]


#: رسالة الحالة التشغيلية — تُعرَّف هنا لأن مصدرها فشل السلسلة نفسها، وتستهلكها عقد
#: الرسم بدل أن تخترع كلُّ عقدة نصّاً مختلفاً يُقرأ كأنه «إجابة» (ISS-200 / D-288).
PROVIDER_UNAVAILABLE_MESSAGE = (
    "⚠️ تعذّر الوصول إلى مزوّد الذكاء الاصطناعي حالياً: كل نماذج السلسلة فشلت في هذه "
    "الدورة. السؤال سليم والعطل في الخدمة — أعد المحاولة بعد لحظات."
)


class AIClient:
    """
    Simple AI Client for Orchestrator Service.
    Wraps AsyncOpenAI to provide generate and stream_chat methods, rotating the
    canonical model chain on failure (ISS-200).
    """

    def __init__(self) -> None:
        settings = get_settings()
        # The knob is a Settings field (D-270 L5 — one home per programmatic identifier);
        # this module only reads it. Empty override keeps the historical behaviour exactly.
        override = (settings.OPENROUTER_BASE_URL or "").strip()
        if settings.OPENROUTER_API_KEY:
            api_key = settings.OPENROUTER_API_KEY
            base_url = override or DEFAULT_BASE_URL
        else:
            api_key = settings.OPENAI_API_KEY
            base_url = override or None

        if not api_key:
            logger.warning("No API Key found for AI Client. AI features will fail.")

        # DEADLOCK FIX: bound leaf-node streaming/generate I/O. Without an
        # explicit timeout a stalled OpenRouter stream blocks the node
        # indefinitely; a bounded client raises so the node's fallback engages.
        # ISS-200: `max_retries=0` — the retry mechanism *is* the model chain.
        # Hammering one rate-limited model three times while a student waits adds
        # latency, not availability.
        self.timeout = float(os.getenv("ORCHESTRATOR_LLM_TIMEOUT", "45"))
        self.first_token_timeout = float(
            os.getenv(FIRST_TOKEN_TIMEOUT_ENV, DEFAULT_FIRST_TOKEN_TIMEOUT)
        )
        self.base_url = base_url
        self.client = AsyncOpenAI(
            api_key=api_key or "dummy-key",
            base_url=base_url,
            timeout=self.timeout,
            max_retries=0,
        )

        self.sync_client = OpenAI(
            api_key=api_key or "dummy-key",
            base_url=base_url,
            timeout=self.timeout,
            max_retries=0,
        )
        # لا حرفية هنا بعد اليوم: المصدر هو `ActiveModels.PRIMARY` — الملفّ الذي تحرسه
        # `check_model_chain_parity` بالفعل. فالقرار الواحد له موطنٌ واحد (D-186).
        # `ORCHESTRATOR_LLM_MODEL` يبقى تجاوزاً صريحاً للمُشغِّل.
        self.default_model = os.getenv("ORCHESTRATOR_LLM_MODEL", ActiveModels.PRIMARY)
        # آخر نموذج أعطى محتوى حقيقياً — للتشخيص و`/health` والـ telemetry.
        self.last_model: str | None = None

    # ------------------------------------------------------------------ chain
    def model_chain(self) -> list[str]:
        """السلسلة المرتَّبة: PRIMARY ثم الاحتياطيات، بلا تكرار (مصدر واحد للحقيقة).

        تُقرأ من `ai_config` في كل call (لا تُجمَّد عند الاستيراد) ليتبع العميلُ
        تجاوزَ المُشغِّل ``OPENROUTER_PRIMARY_MODEL`` و``OPENROUTER_EXTRA_MODELS``
        كما يفعل المونوليث بالضبط.
        """
        chain: list[str] = []
        candidates = [self.default_model, *get_ai_config().get_fallback_models()]
        for candidate in candidates:
            cleaned = (candidate or "").strip()
            if cleaned and cleaned not in chain:
                chain.append(cleaned)
        return chain

    @staticmethod
    def _should_rotate(exc: Exception) -> bool:
        """هل يستحق هذا الخطأ تجربة النموذج التالي؟ (نعم لمعظم الأخطاء)."""
        if isinstance(exc, (APIConnectionError, APITimeoutError, TimeoutError, ConnectionError)):
            return True
        if isinstance(exc, APIError):
            status = getattr(exc, "status_code", None)
            if isinstance(status, int):
                return status in _RETRY_AS_FALLBACK_STATUS
            return True
        # ValueError من حارس «لا محتوى» + أخطاء الشبكة غير المصنَّفة.
        return True

    def _describe(self, exc: Exception) -> str:
        status = getattr(exc, "status_code", None)
        name = type(exc).__name__
        msg = str(exc).replace("\n", " ")[:180]
        return f"{name}({status}) {msg}" if status else f"{name} {msg}"

    # --------------------------------------------------------------- generate
    async def generate(
        self,
        model: str | None = None,
        messages: list[dict[str, str]] | None = None,
        **kwargs: object,
    ) -> object:
        """
        Generate a complete response.
        If 'response_format' is JSON, returns the parsed object if possible, or the raw response.
        Use for non-streaming tasks.

        ISS-200: مع ``model=None`` تدور السلسلة كاملة؛ ومع ``model=<id>`` يبقى السلوك
        القديم (نموذج واحد، استثناء واحد) لتفادي كسر أي مستدعٍ محدِّد النموذج.
        """
        if not messages:
            messages = [{"role": "user", "content": kwargs.get("prompt", "")}]

        targets = [model] if model else self.model_chain()
        attempts: list[tuple[str, str]] = []
        for target_model in targets:
            try:
                resp = await self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    **kwargs,
                )
                self.last_model = target_model
                if len(targets) > 1:
                    logger.info("AI generate served by model=%s", target_model)
                return resp
            except Exception as e:
                attempts.append((target_model, self._describe(e)))
                if model or not self._should_rotate(e):
                    logger.error("AI Generation failed: %s", e)
                    raise
                logger.warning("AI generate: model=%s failed (%s) — rotating", *attempts[-1])
        raise AllModelsFailedError(attempts)

    # ------------------------------------------------------------- streaming
    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: object,
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Stream chat completion.
        Yields ChatCompletionChunk objects (OpenAI SDK type) — first chunk wins:
        a model is abandoned **only while nothing has been emitted**, so a student
        never sees two answers stitched together.
        Use extract_stream_content() to get text from each chunk safely.

        ISS-200: rotation over the canonical chain + ``content``-only guard (D-067:
        a reasoning-only model yields ``content=None`` and must not count as an
        answer) + :class:`AllModelsFailedError` when the whole chain is dead.
        """
        targets = [model] if model else self.model_chain()
        attempts: list[tuple[str, str]] = []
        for target_model in targets:
            emitted = 0
            started = time.monotonic()
            try:
                stream = await self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    stream=True,
                    **kwargs,
                )
                async for chunk in stream:
                    if self._chunk_has_content(chunk):
                        if emitted == 0:
                            self.last_model = target_model
                        emitted += 1
                        yield chunk
                    elif emitted == 0 and (time.monotonic() - started) > self.first_token_timeout:
                        raise TimeoutError(
                            f"first_token_timeout model={target_model} "
                            f"after={self.first_token_timeout:.0f}s"
                        )
                if emitted == 0:
                    # نموذج بلا أي content (reasoning-only أو فراغ) = فشل، لا إجابة.
                    raise ValueError(f"empty_completion model={target_model} (content_chunks=0)")
                if len(targets) > 1:
                    logger.info("AI stream served by model=%s chunks=%d", target_model, emitted)
                return
            except Exception as e:
                if emitted > 0:
                    # وصل محتوى للطالب فعلاً: لا نعيد التوليد فوقه، ننهي الدور.
                    logger.warning(
                        "AI stream interrupted after %d chunks (model=%s): %s",
                        emitted,
                        target_model,
                        self._describe(e),
                    )
                    return
                attempts.append((target_model, self._describe(e)))
                if model or not self._should_rotate(e):
                    logger.error("AI Stream failed: %s", e)
                    raise
                logger.warning("AI stream: model=%s failed (%s) — rotating", *attempts[-1])
        raise AllModelsFailedError(attempts)

    @staticmethod
    def _chunk_has_content(chunk: object) -> bool:
        """هل يحمل الـ chunk محتوى حقيقياً (لا reasoning فقط)؟"""
        return isinstance(AIClient.extract_stream_content(chunk), str)

    @staticmethod
    def extract_stream_content(chunk: object) -> str | None:
        """
        يستخرج محتوى النص من chunk بأمان سواء كان ChatCompletionChunk أو dict.

        ISS-STREAM-002: الإصلاح الجراحي — stream_chat يُعيد ChatCompletionChunk objects
        (OpenAI SDK) وليس dicts. الكود القديم كان يستخدم chunk.get('choices') مما يُسبب
        AttributeError يُبتلع بـ except → لا يُصدر أي محتوى → timeout كارثي.
        """
        # ChatCompletionChunk (OpenAI SDK object)
        if hasattr(chunk, "choices"):
            choices = chunk.choices
            if choices and len(choices) > 0:
                delta = choices[0].delta
                if delta is not None:
                    content = getattr(delta, "content", None)
                    if isinstance(content, str) and content:
                        return content
            return None

        # dict fallback (legacy/mock)
        if isinstance(chunk, dict):
            choices = chunk.get("choices")
            if choices and len(choices) > 0:
                delta = choices[0]
                if isinstance(delta, dict):
                    content = delta.get("delta", {}).get("content")
                else:
                    content = getattr(getattr(delta, "delta", None), "content", None)
                if isinstance(content, str) and content:
                    return content
        return None

    async def generate_text(self, prompt: str, **kwargs: object) -> str:
        """Helper for simple text generation."""
        response = await self.generate(prompt=prompt, **kwargs)
        return response.choices[0].message.content or ""

    def generate_sync(
        self,
        model: str | None = None,
        messages: list[dict[str, str]] | None = None,
        **kwargs: object,
    ) -> object:
        """
        Generate a complete response synchronously.
        """
        target_model = model or self.default_model
        if not messages:
            messages = [{"role": "user", "content": kwargs.get("prompt", "")}]

        try:
            return self.sync_client.chat.completions.create(
                model=target_model,
                messages=messages,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"AI Sync Generation failed: {e}")
            raise

    def health_snapshot(self) -> dict[str, Any]:
        """لقطة تشغيل لمسار التوليد — تُستهلَك في `/health` والمسبارات الحيّة."""
        chain = self.model_chain()
        return {
            "primary": chain[0] if chain else None,
            "chain": chain,
            "last_serving_model": self.last_model,
            "base_url": self.base_url or "openai-default",
            "timeout_s": self.timeout,
            "first_token_timeout_s": self.first_token_timeout,
        }


# Singleton instance
ai_client = AIClient()


def get_ai_client() -> AIClient:
    return ai_client
