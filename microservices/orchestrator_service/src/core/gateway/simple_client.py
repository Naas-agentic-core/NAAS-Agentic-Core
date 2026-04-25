"""
عميل ذكاء اصطناعي بسيط (معاد تنظيمه وفق SOLID).
-------------------------------------------------
ينفّذ بروتوكول LLMClient مع حقن تبعيات واضح وقابل للاختبار.
"""

import hashlib
import json
import logging
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import httpx

from microservices.orchestrator_service.src.core.ai_config import get_ai_config
from microservices.orchestrator_service.src.core.cognitive_cache import (
    CognitiveResonanceEngine,
    get_cognitive_engine,
)
from microservices.orchestrator_service.src.core.gateway.connection import (
    BASE_TIMEOUT,
    ConnectionManager,
)
from microservices.orchestrator_service.src.core.interfaces.llm import LLMClient
from microservices.orchestrator_service.src.core.types import JSONDict
from microservices.orchestrator_service.src.services.llm.safety_net import SafetyNetService

logger = logging.getLogger(__name__)


@dataclass
class SimpleResponse:
    content: str


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

        self.base_url = "https://openrouter.ai/api/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://cogniforge.local",
            "X-Title": "CogniForge Simple Gateway",
        }

    async def __aiter__(self) -> "OpenRouterClient":
        """دعم التكرار غير المتزامن على العميل نفسه للتوافق الخلفي."""
        return self

    def _get_context_hash(self, messages: list[JSONDict]) -> str:
        """توليد بصمة ثابتة لسياق المحادثة."""
        if not messages:
            return "empty"
        # We hash everything
        context_msgs = messages
        context_str = json.dumps(context_msgs, sort_keys=True)
        return hashlib.sha256(context_str.encode()).hexdigest()

    async def stream_chat(self, messages: list[JSONDict]) -> AsyncGenerator[JSONDict, None]:
        """
        يبث إكمال الدردشة مع تجربة النماذج حسب الأولوية.
        """
        if not messages:
            yield self._create_error_chunk("No messages provided.")
            return

        last_message = messages[-1]
        prompt = str(last_message.get("content", ""))
        context_hash = self._get_context_hash(messages)

        # 1. Check Cognitive Cache (injected)
        # Note: Logic preserved from original (disabled by default in code, but structure remains)
        # if last_message.get("role") == "user":
        #     cached = self.cognitive_engine.recall(prompt, context_hash)
        #     ...

        # 2. Prepare Model List
        models_to_try = [self.primary_model, *self.fallback_models]

        # 3. Try each model
        client = ConnectionManager.get_client()
        full_response_chunks: list[JSONDict] = []
        success = False

        for model_id in models_to_try:
            try:
                logger.info(f"Attempting model: {model_id}")
                async for chunk in self._stream_model(client, model_id, messages):
                    full_response_chunks.append(chunk)
                    yield chunk

                success = True
                # Memorize success
                if last_message.get("role") == "user":
                    self.cognitive_engine.memorize(prompt, context_hash, full_response_chunks)
                return

            except (httpx.ConnectError, httpx.ReadTimeout, httpx.HTTPStatusError, ValueError) as e:
                logger.warning(f"Model {model_id} failed: {e}. Trying next...")
            except Exception as e:
                logger.error(f"Unexpected error with {model_id}: {e}", exc_info=True)

        # 4. Safety Net (All models failed)
        if not success:
            logger.critical("All models exhausted. Engaging Safety Net.")
            async for chunk in self.safety_net.stream_safety_response():
                yield chunk

    async def _stream_model(
        self, client: httpx.AsyncClient, model_id: str, messages: list[JSONDict]
    ) -> AsyncGenerator[JSONDict, None]:
        """
        مولّد داخلي للبث من نموذج محدد.
        """
        try:
            async with client.stream(
                "POST",
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json={"model": model_id, "messages": messages, "stream": True, "temperature": 0.7},
                timeout=httpx.Timeout(BASE_TIMEOUT, connect=10.0),
            ) as response:
                if response.status_code != 200:
                    await response.aread()
                    raise httpx.HTTPStatusError(
                        f"Status {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                async for line in response.aiter_lines():
                    if line.startswith("data: "):
                        data_str = line[6:]
                        if data_str.strip() == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data_str)
                            yield chunk
                        except json.JSONDecodeError:
                            continue

        except httpx.StreamError as e:
            raise httpx.ConnectError(f"Stream error: {e}") from e

    def _create_error_chunk(self, message: str) -> JSONDict:
        return {"error": {"message": message}}  # type: ignore

    async def send_message(
        self, system_prompt: str, user_message: str, temperature: float = 0.7
    ) -> str:
        """
        مساعد بسيط للإرسال غير المتدفق.
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
                content = delta.get("content", "")
                if content:
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
