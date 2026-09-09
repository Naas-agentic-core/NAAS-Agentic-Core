"""
عميل ذكاء اصطناعي بسيط (معاد تنظيمه وفق SOLID).
-------------------------------------------------
ينفّذ بروتوكول LLMClient مع حقن تبعيات واضح وقابل للاختبار.
"""

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx

from app.core.ai_config import get_ai_config, get_openrouter_base_url, get_openrouter_site_url
from app.core.cognitive_cache import CognitiveResonanceEngine, get_cognitive_engine
from app.core.feature_flags import cognitive_cache_resilience_enabled
from app.core.gateway.connection import BASE_TIMEOUT, ConnectionManager
from app.core.gateway.exceptions import AIRateLimitError
from app.core.interfaces.llm import LLMClient
from app.core.types import JSONDict
from app.services.llm.safety_net import SafetyNetService

logger = logging.getLogger(__name__)

# D-177 — "answer every question" under free-tier rate limits.
# Soft deadline for the FIRST content chunk from a model. A model that streams
# only reasoning/keepalives (e.g. nvidia/nemotron-nano-9b measured at 62s,
# content=0) must not hold the turn hostage — abandon it and fail over fast.
# Set above the safety-pinned gemma models' legitimate first-token latency
# (~12-18s live) so a slow-but-working model is never wrongly abandoned, yet
# well below BASE_TIMEOUT (45s) so a truly dead model fails over quickly.
FIRST_TOKEN_TIMEOUT = 30.0
# Max wall-clock to wait before the bounded SECOND pass over models that returned
# 429 on the first pass. Kept short so interactive latency stays acceptable even
# when the provider advertises a longer Retry-After.
RATE_LIMIT_BACKOFF_MAX = 5.0
# A hosted runner can lose DNS briefly while OpenRouter is healthy. Retry only
# transport/5xx failures; 404, auth, and model-policy failures must still fail over.
TRANSIENT_PROVIDER_RETRIES = 2
TRANSIENT_PROVIDER_BACKOFF = 1.0


def _parse_retry_after(response: httpx.Response) -> float | None:
    """Best-effort ``retry_after`` (seconds) from a 429 response.

    OpenRouter advertises the hint either in the ``Retry-After`` header or in the
    JSON body under ``error.metadata.retry_after_seconds`` — try both, never raise.
    """
    header = response.headers.get("Retry-After")
    if header:
        try:
            return float(header)
        except ValueError:
            pass
    try:
        meta = response.json().get("error", {}).get("metadata", {})
        raw = meta.get("retry_after_seconds") or meta.get("retry_after_seconds_raw")
        if raw is not None:
            return float(raw)
    except (ValueError, json.JSONDecodeError, AttributeError):
        pass
    return None


@dataclass
class SimpleResponse:
    content: str


@dataclass
class _ModelOutcome:
    """Terminal sentinel yielded by ``_attempt_model`` after a model's chunks.

    ``emitted_content`` is True only if at least one real ``delta.content`` chunk
    reached the client; ``error`` classifies the failure (notably
    ``AIRateLimitError`` for 429) so the caller can schedule a second pass.
    """

    emitted_content: bool
    error: Exception | None
    chunks: list[JSONDict] | None = None


class OpenRouterClient(LLMClient):
    """
    عميل قوي ومبسّط يقوم بالمهام التالية:
    1) المصادقة مع OpenRouter.
    2) التبديل الاحتياطي للنماذج (أساسي -> بدائل).
    3) التخزين المؤقت عبر محرك معرفي محقون.
    4) شبكة أمان عبر خدمة SafetyNetService.
    """

    def __init__(
        self,
        api_key: str,
        primary_model: str,
        fallback_models: list[str],
        cognitive_engine: CognitiveResonanceEngine,
        safety_net: SafetyNetService,
    ):
        self.api_key = api_key
        self.primary_model = primary_model
        self.fallback_models = fallback_models
        self.cognitive_engine = cognitive_engine
        self.safety_net = safety_net

        # ISS-200/D-288: base URL قابل للتجاوز (بوابة/وكيل/ازدواج اختبار) — نفس عقدة
        # OPENROUTER_PRIMARY_MODEL: لا يُختبر المسار بلا هذا المقبض. والاسمُ موطنُه
        # `Settings` لا هذا الملفّ: لكلِّ نصٍّ يقرؤه البرنامج موطنٌ واحد (D-270 L5).
        self.base_url = get_openrouter_base_url()
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": get_openrouter_site_url(),
            "X-Title": "CogniForge Simple Gateway",
        }

    async def __aiter__(self) -> "OpenRouterClient":
        """دعم التكرار غير المتزامن على العميل نفسه للتوافق الخلفي."""
        return self

    def _get_context_hash(self, messages: list[JSONDict]) -> str:
        """توليد بصمة ثابتة لسياق المحادثة."""
        if not messages:
            return "empty"
        # We hash everything *except* the last message (which is the new prompt)
        context_msgs = messages[:-1] if len(messages) > 1 else []
        context_str = json.dumps(context_msgs, sort_keys=True)
        return hashlib.sha256(context_str.encode()).hexdigest()

    async def stream_chat(
        self,
        messages: list[JSONDict],
        max_tokens: int | None = None,
    ) -> AsyncGenerator[JSONDict, None]:
        """
        يبث إكمال الدردشة مع تجربة النماذج حسب الأولوية.

        Args:
            messages: قائمة رسائل المحادثة.
            max_tokens: الحد الأقصى للرموز المُولَّدة — يُقلِّص وقت الاستجابة
                        للطلبات ذات السياق الكبير (مثل شرح التمارين).
        """
        if not messages:
            yield self._create_error_chunk("No messages provided.")
            return

        last_message = messages[-1]
        prompt = str(last_message.get("content", ""))
        context_hash = self._get_context_hash(messages)

        # 2. Prepare Model List
        models_to_try = [self.primary_model, *self.fallback_models]

        # 3. Try each model.
        # D-177: a single linear pass drops to the safety net ("لا يجيب") whenever
        # every free model is *transiently* 429 at the same instant — which the
        # live probe (2026-07-22) showed is common. We instead run a bounded
        # SECOND pass over just the rate-limited models after a short backoff, so
        # a momentary global rate-limit self-heals before we ever give up.
        client = ConnectionManager.get_client()

        rate_limited: list[str] = []  # models that returned 429 on pass 1
        max_retry_after = 0.0

        def _memorize(outcome: _ModelOutcome) -> None:
            # D-180: get_cognitive_engine() returns a REAL Arabic-aware singleton
            # (not None). The None-guard is kept as defensive code (a test may inject
            # None, and CLAUDE.md forbids removing it). Every successful user turn is
            # memorized so the resilience recall (step 4 below) has content to serve.
            if last_message.get("role") == "user" and self.cognitive_engine is not None:
                self.cognitive_engine.memorize(prompt, context_hash, outcome.chunks or [])

        for model_id in models_to_try:
            outcome: _ModelOutcome | None = None
            async for item in self._attempt_model(client, model_id, messages, max_tokens):
                if isinstance(item, _ModelOutcome):
                    outcome = item
                    break
                yield item
            if outcome and outcome.emitted_content:
                _memorize(outcome)
                return
            if outcome and isinstance(outcome.error, AIRateLimitError):
                rate_limited.append(model_id)
                if outcome.error.retry_after:
                    max_retry_after = max(max_retry_after, outcome.error.retry_after)

        # 3b. Bounded second pass — retry ONLY the rate-limited models.
        if rate_limited:
            backoff = min(max_retry_after or 1.0, RATE_LIMIT_BACKOFF_MAX)
            logger.warning(
                "all_models_pass1_failed rate_limited=%d backoff=%.1fs — second pass",
                len(rate_limited),
                backoff,
            )
            await asyncio.sleep(backoff)
            for model_id in rate_limited:
                outcome = None
                async for item in self._attempt_model(client, model_id, messages, max_tokens):
                    if isinstance(item, _ModelOutcome):
                        outcome = item
                        break
                    yield item
                if outcome and outcome.emitted_content:
                    _memorize(outcome)
                    return

        # 4. Cognitive-cache resilience recall (D-180 / ISS-133) — BEFORE the safety net.
        # Every model is exhausted (typically a transient global 429). A high-resonance
        # prior answer to the SAME question in the SAME context is strictly better than
        # the "لا يجيب" safety-net stub — this is what makes the system "answer every
        # question". Pedagogy is preserved: recall() enforces an exact context_hash
        # match, and this path fires ONLY after the full model chain has failed, never
        # short-circuiting a live model. Reversible via COGNITIVE_CACHE_RESILIENCE_ENABLED=0.
        if (
            cognitive_cache_resilience_enabled()
            and self.cognitive_engine is not None
            and last_message.get("role") == "user"
        ):
            recalled = self.cognitive_engine.recall(prompt, context_hash)
            if recalled:
                logger.warning(
                    "cognitive_cache_resilience_hit — replaying prior answer (%d chunks)",
                    len(recalled),
                )
                for chunk in recalled:
                    yield chunk
                return

        # 5. Safety Net (all models failed AND no cache resonance).
        logger.critical("All models exhausted. Engaging Safety Net.")
        async for chunk in self.safety_net.stream_safety_response():
            yield chunk

    @staticmethod
    def _is_transient_provider_error(error: Exception) -> bool:
        """Return whether retrying the same provider is safe and useful."""
        if isinstance(error, (httpx.ConnectError, httpx.ReadTimeout)):
            return True
        if isinstance(error, httpx.HTTPStatusError):
            return error.response.status_code in {502, 503, 504}
        return False

    async def _stream_model_with_retries(
        self,
        client: httpx.AsyncClient,
        model_id: str,
        messages: list[JSONDict],
        max_tokens: int | None,
    ) -> AsyncGenerator[JSONDict, None]:
        """Retry transient transport/provider outages, never permanent model errors."""
        for attempt in range(TRANSIENT_PROVIDER_RETRIES + 1):
            try:
                async for chunk in self._stream_model(client, model_id, messages, max_tokens):
                    yield chunk
                return
            except Exception as error:
                if (
                    not self._is_transient_provider_error(error)
                    or attempt >= TRANSIENT_PROVIDER_RETRIES
                ):
                    raise
                delay = TRANSIENT_PROVIDER_BACKOFF * (attempt + 1)
                logger.warning(
                    "transient_provider_error model=%s attempt=%d/%d retry_in=%.1fs error=%s",
                    model_id,
                    attempt + 1,
                    TRANSIENT_PROVIDER_RETRIES,
                    delay,
                    error,
                )
                await asyncio.sleep(delay)

    async def _attempt_model(
        self,
        client: httpx.AsyncClient,
        model_id: str,
        messages: list[JSONDict],
        max_tokens: int | None,
    ) -> "AsyncGenerator[JSONDict | _ModelOutcome, None]":
        """Stream one model, yielding its chunks then a terminal ``_ModelOutcome``.

        Isolating a single model attempt keeps ``stream_chat`` readable and lets
        both the first and second pass share identical failover semantics. The
        outcome carries whether any real content was emitted and, on failure, the
        exception (so the caller can classify 429 vs hard-fail).
        """
        emitted = False
        collected: list[JSONDict] = []
        try:
            logger.info("Attempting model: %s", model_id)
            async for chunk in self._stream_model_with_retries(
                client, model_id, messages, max_tokens=max_tokens
            ):
                collected.append(chunk)
                choices = chunk.get("choices", [])  # type: ignore[union-attr]
                if choices and (choices[0].get("delta", {}) or {}).get("content"):
                    emitted = True
                yield chunk
            yield _ModelOutcome(emitted_content=emitted, error=None, chunks=collected)
        except AIRateLimitError as e:
            logger.warning("model_rate_limited model=%s retry_after=%s", model_id, e.retry_after)
            yield _ModelOutcome(emitted_content=emitted, error=e, chunks=collected)
        except (
            httpx.ConnectError,
            httpx.ReadTimeout,
            httpx.HTTPStatusError,
            ValueError,
            TimeoutError,
        ) as e:
            logger.warning("Model %s failed: %s. Trying next...", model_id, e)
            yield _ModelOutcome(emitted_content=emitted, error=e, chunks=collected)
        except Exception as e:  # never let one model kill the turn
            logger.error("Unexpected error with %s: %s", model_id, e, exc_info=True)
            yield _ModelOutcome(emitted_content=emitted, error=e, chunks=collected)

    async def _stream_model(
        self,
        client: httpx.AsyncClient,
        model_id: str,
        messages: list[JSONDict],
        max_tokens: int | None = None,
    ) -> AsyncGenerator[JSONDict, None]:
        """
        مولّد داخلي للبث من نموذج محدد.

        ISS-STREAM-004: يُضيف asyncio.sleep(0) بعد كل chunk لإعطاء
        event loop فرصة معالجة أحداث أخرى — يمنع machine-gun effect
        حيث تصل 100+ chunk في أقل من 10ms مما يُجمِّد الواجهة.

        D-177: 429 يُصنَّف كـ AIRateLimitError (مع retry_after) ليُشغِّل المرور
        الثاني؛ ونحرس زمن أول محتوى (FIRST_TOKEN_TIMEOUT) حتى لا يُجمِّد نموذجٌ
        بطيء/فارغ الدور (nvidia/nemotron-nano-9b قِيس 62s بمحتوى=0).
        """
        payload: dict[str, object] = {
            "model": model_id,
            "messages": messages,
            "stream": True,
            "temperature": 0.7,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        started = time.monotonic()
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=httpx.Timeout(BASE_TIMEOUT, connect=10.0),
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    if response.status_code == 429:
                        raise AIRateLimitError(
                            f"rate_limited model={model_id}",
                            retry_after=_parse_retry_after(response),
                        )
                    raise httpx.HTTPStatusError(
                        f"Status {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                # ISS-079 (D-067 — 2026-05-17): Reasoning-leak guard
                # كارثة سابقة: ISS-069 redirect reasoning → content كان يبث
                # التفكير الإنجليزي للطالب ("We need to respond as a brilliant
                # Algerian Baccalaureate math professor...") كنص عربي مزعوم.
                # الحل: لا نُمرِّر reasoning كـ content أبداً — نُعيده فارغاً
                # ليفعّل fallback chain يستدعي نموذج آخر يُنتج content فعلي.
                content_chunks = 0
                reasoning_chunks = 0
                async for line in response.aiter_lines():
                    # D-177: abandon a model that has not produced ANY real content
                    # within FIRST_TOKEN_TIMEOUT so a slow/empty model fails over
                    # fast instead of holding the turn for the full BASE_TIMEOUT.
                    if content_chunks == 0 and (time.monotonic() - started) > FIRST_TOKEN_TIMEOUT:
                        raise TimeoutError(
                            f"first_token_timeout model={model_id} after={FIRST_TOKEN_TIMEOUT:.0f}s"
                        )
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            choices = chunk.get("choices", [])
                            if choices:
                                delta = choices[0].get("delta", {})
                                has_content = bool(delta.get("content"))
                                has_reasoning = bool(delta.get("reasoning"))
                                if has_content:
                                    content_chunks += 1
                                if has_reasoning and not has_content:
                                    reasoning_chunks += 1
                                # تنظيف: لا تمرر reasoning كـ content
                                if has_reasoning and not has_content:
                                    delta["content"] = None
                                    choices[0]["delta"] = delta
                                    chunk["choices"] = choices
                            yield chunk
                            await asyncio.sleep(0)
                        except json.JSONDecodeError:
                            continue
                # تشخيص: إذا الكل reasoning فقط، سجِّل للمراقبة
                if reasoning_chunks > 0 and content_chunks == 0:
                    logger.warning(
                        "reasoning_only_response model=%s reasoning_chunks=%d — likely model "
                        "incompatibility with this prompt (fallback will trigger)",
                        model_id,
                        reasoning_chunks,
                    )

                # ISS-107 (D-WS-LANG-GUARD): نموذج لم يُنتج أي content حقيقي
                # (reasoning-only مثل glm-4.5-air، أو فراغ تام) يُعَدّ فشلاً —
                # نرفع استثناءً ليتقدّم stream_chat للنموذج التالي بدل إرجاع
                # إجابة فارغة («لا يجيب»). آمن: كل ما بُثّ كان content=None
                # (المستهلك يتخطّاه)، فلا غارباج وصل للطالب.
                if content_chunks == 0:
                    raise ValueError(
                        f"empty_completion model={model_id} "
                        f"(content_chunks=0 reasoning_chunks={reasoning_chunks})"
                    )

        except httpx.StreamError as e:
            raise httpx.ConnectError(f"Stream error: {e}") from e

    def _create_error_chunk(self, message: str) -> JSONDict:
        return {"error": {"message": message}}  # type: ignore

    async def send_message(
        self, system_prompt: str, user_message: str, temperature: float = 0.7
    ) -> str:
        """
        مساعد بسيط للإرسال غير المتدفق.

        ISS-079 (D-067): لم نعد نُمرِّر reasoning كـ content — هذا كان يسرِّب
        التفكير الإنجليزي للطلاب. الآن نُجمِّع content فقط، ونعود فارغاً إذا
        النموذج فشل (fallback chain يستدعي نموذج آخر).
        """
        messages: list[JSONDict] = [
            {"role": "system", "content": system_prompt},  # type: ignore
            {"role": "user", "content": user_message},  # type: ignore
        ]

        full_content = []
        async for chunk in self.stream_chat(messages):
            choices = chunk.get("choices", [])  # type: ignore
            if choices:
                delta = choices[0].get("delta", {})
                content = delta.get("content")
                if content and isinstance(content, str):
                    full_content.append(content)

        return "".join(full_content)

    # Legacy Compatibility
    async def generate_text(
        self, prompt: str, model: str | None = None, system_prompt: str | None = None, **kwargs
    ) -> SimpleResponse:
        """توليد نص بسيط مع الحفاظ على التوافق الخلفي."""
        sys_p = system_prompt or "You are a helpful assistant."
        content = await self.send_message(sys_p, prompt)
        return SimpleResponse(content=content)

    async def forge_new_code(self, **kwargs) -> SimpleResponse:
        """توليد شيفرة مع الحفاظ على التوافق الخلفي."""
        prompt = kwargs.get("prompt", "")
        return await self.generate_text(prompt, **kwargs)

    # Legacy Safety Net Helper for NeuralRoutingMesh
    async def _stream_safety_net(self) -> AsyncGenerator[JSONDict, None]:
        async for chunk in self.safety_net.stream_safety_response():
            yield chunk


class SimpleAIClient(OpenRouterClient):
    """
    غلاف متوافق مع الخلفية يحقن التبعيات العالمية تلقائيًا.
    """

    def __init__(self, api_key: str | None = None):
        config = get_ai_config()
        key = api_key or config.openrouter_api_key or "dummy_key"

        super().__init__(
            api_key=key,
            primary_model=config.primary_model,
            fallback_models=config.get_fallback_models(),
            cognitive_engine=get_cognitive_engine(),
            safety_net=SafetyNetService(),
        )
