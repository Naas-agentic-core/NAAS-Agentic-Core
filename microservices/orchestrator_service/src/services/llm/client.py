"""
AI Client for Orchestrator Service.
Provides a simple interface to OpenAI-compatible LLMs.

## سلسلة النماذج الاحتياطية (ISS-LLM-CHAIN — 2026-09-08)

كان هذا العميل يستدعي **نموذجاً واحداً** (`default_model`) ويرفع الاستثناء عند
فشله — بلا أي تقدّم إلى بقية السلسلة. لمّا أزال OpenRouter نقاط النهاية
(endpoints) لـ `openai/gpt-oss-20b:free` صار كل استدعاء يعيد
``404 No endpoints found``، فتفشل ``SynthesizerNode`` ويرى الطالب سياقاً خاماً
أو لا شيء («النظام لا يجيب») — وهو العطل المُعاد إنتاجه حياً في هذه الجولة.

الإصلاح: العميل يمشي الآن على السلسلة الكاملة `[PRIMARY, FALLBACK_1..5]`
المُعلَنة في `core/ai_config.py` (نفس السلسلة التي تحرسها بوابة تطابق السلاسل
`check_model_chain_parity`)، ويتقدّم تلقائياً عند:

* أي استثناء من المزوّد (404 / 429 / 5xx / انقطاع)، **و**
* تيّار يعيد صفر محتوى (`content_chunks == 0` — نموذج reasoning-only)،
  وهو الحارس نفسه المعمول به في مونوليث `app/core/gateway/simple_client.py`.

``model=`` الصريح يبقى فوق السلسلة (طلبٌ محدَّد بنموذج بعينه يُحترم كما هو).
"""

import logging
import os
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk

from microservices.orchestrator_service.src.core.ai_config import (
    ActiveModels,
    get_ai_config,
)
from microservices.orchestrator_service.src.core.config import get_settings

logger = logging.getLogger("ai-client")


def resolve_model_chain(primary_model: str) -> list[str]:
    """تبني سلسلة النماذج المرتَّبة: الأساسي ثم البدائل الخمسة (بلا تكرار).

    Args:
        primary_model: النموذج الأساسي (يُحترم دائماً كأول عنصر).

    Returns:
        قائمة مرتَّبة من معرّفات النماذج تُجرَّب بالترتيب حتى أول محتوى صالح.
    """
    chain: list[str] = [primary_model]
    try:
        candidates = list(get_ai_config().get_fallback_models())
    except Exception as exc:  # pragma: no cover — fail-open على مستوى القراءة
        logger.warning("model_chain_resolution_failed: %s", exc)
        candidates = []
    for model_id in candidates:
        if isinstance(model_id, str) and model_id and model_id not in chain:
            chain.append(model_id)
    return chain


class AIClient:
    """
    Simple AI Client for Orchestrator Service.
    Wraps AsyncOpenAI to provide generate and stream_chat methods.
    """

    def __init__(self) -> None:
        from openai import OpenAI

        settings = get_settings()
        if settings.OPENROUTER_API_KEY:
            api_key = settings.OPENROUTER_API_KEY
            base_url = "https://openrouter.ai/api/v1"
        else:
            api_key = settings.OPENAI_API_KEY
            base_url = None

        if not api_key:
            logger.warning("No API Key found for AI Client. AI features will fail.")

        # DEADLOCK FIX: bound leaf-node streaming/generate I/O. Without an
        # explicit timeout a stalled OpenRouter stream blocks the node
        # indefinitely; a bounded client raises so the node's fallback engages.
        self.client = AsyncOpenAI(
            api_key=api_key or "dummy-key",
            base_url=base_url,
            timeout=45.0,
        )

        self.sync_client = OpenAI(
            api_key=api_key or "dummy-key",
            base_url=base_url,
            timeout=45.0,
        )
        # ISS-157: كان هنا `nvidia/nemotron-3-nano-30b-a3b:free` مُصلَّباً — وهو النموذج
        # الذي يمنعه D-067 صراحةً أن يكون PRIMARY (ISS-079: كارثة «pepepe aaaa»، محتوى
        # إنجليزي/فارغ مع موجّهات النظام الطويلة). التعليق القديم كان يستشهد بـISS-069
        # (2026-05-15)، و**D-067 نقضه بعد يومين** (2026-05-17) ولم يُحدَّث هذا الملفّ.
        #
        # لا حرفية هنا بعد اليوم: المصدر هو `ActiveModels.PRIMARY` — الملفّ الذي تحرسه
        # `check_model_chain_parity` بالفعل. فالقرار الواحد له موطنٌ واحد (D-186).
        # `ORCHESTRATOR_LLM_MODEL` يبقى تجاوزاً صريحاً للمُشغِّل.
        self.default_model = os.getenv("ORCHESTRATOR_LLM_MODEL", ActiveModels.PRIMARY)
        # السلسلة الكاملة (الأساسي + البدائل) — يتقدّم عليها العميل عند الفشل.
        self.model_chain = resolve_model_chain(self.default_model)

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

        ISS-LLM-CHAIN: يمشي على السلسلة كاملة ويتقدّم عند أي استثناء.
        """
        targets = [model] if model else list(self.model_chain)
        if not messages:
            messages = [{"role": "user", "content": kwargs.get("prompt", "")}]

        last_error: Exception | None = None
        for target_model in targets:
            try:
                return await self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    **kwargs,
                )
            except Exception as e:
                last_error = e
                logger.error(
                    "AI Generation failed (model=%s): %s — advancing to next model",
                    target_model,
                    e,
                )
        raise last_error or RuntimeError("AI Generation failed: empty model chain")

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: object,
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Stream chat completion.
        Yields ChatCompletionChunk objects (OpenAI SDK type).
        Use extract_stream_content() to get text from each chunk safely.

        ISS-LLM-CHAIN: يمشي على السلسلة كاملة. يتقدّم إلى النموذج التالي عند
        أي استثناء من المزوّد (404 «No endpoints found» / 429 / 5xx) وعند تيّار
        يُنهي دون أي محتوى (حارس content_chunks==0 المعمول به في المونوليث).
        ``model=`` الصريح يُلغي السلسلة ويجرّب ذلك النموذج وحده.
        """
        targets = [model] if model else list(self.model_chain)
        last_error: Exception | None = None

        for target_model in targets:
            try:
                stream = await self.client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    stream=True,
                    **kwargs,
                )
            except Exception as e:
                last_error = e
                logger.error(
                    "AI Stream failed (model=%s): %s — advancing to next model",
                    target_model,
                    e,
                )
                continue

            emitted_content = False
            try:
                async for chunk in stream:
                    if not emitted_content and self.extract_stream_content(chunk):
                        emitted_content = True
                    yield chunk
            except Exception as e:
                # عطبٌ في منتصف التيار: لا يمكن التراجع عمّا بُثَّ — نتقدّم
                # للنموذج التالي فقط إن لم نكن قد بثثنا أي محتوى للطالب.
                last_error = e
                if emitted_content:
                    logger.error(
                        "AI Stream aborted mid-content (model=%s): %s", target_model, e
                    )
                    return
                logger.error(
                    "AI Stream failed before any content (model=%s): %s — advancing",
                    target_model,
                    e,
                )
                continue

            if emitted_content:
                return
            # تيّارٌ بلا محتوى (reasoning-only / نموذج ميت أعاد 200 فارغاً).
            last_error = RuntimeError(f"empty_completion model={target_model}")
            logger.error(
                "AI Stream produced no content (model=%s) — advancing to next model",
                target_model,
            )

        if last_error:
            logger.error(f"AI Stream failed across the whole model chain: {last_error}")
            raise last_error

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
        targets = [model] if model else list(self.model_chain)
        if not messages:
            messages = [{"role": "user", "content": kwargs.get("prompt", "")}]

        last_error: Exception | None = None
        for target_model in targets:
            try:
                return self.sync_client.chat.completions.create(
                    model=target_model,
                    messages=messages,
                    **kwargs,
                )
            except Exception as e:
                last_error = e
                logger.error(
                    "AI Sync Generation failed (model=%s): %s — advancing to next model",
                    target_model,
                    e,
                )
        raise last_error or RuntimeError("AI Sync Generation failed: empty model chain")


# Singleton instance
ai_client = AIClient()


def get_ai_client() -> AIClient:
    return ai_client
