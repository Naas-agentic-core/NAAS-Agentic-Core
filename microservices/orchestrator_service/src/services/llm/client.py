"""
AI Client for Orchestrator Service.
Provides a simple interface to OpenAI-compatible LLMs.
"""

import logging
from collections.abc import AsyncGenerator

from openai import AsyncOpenAI
from openai.types.chat import ChatCompletionChunk

from microservices.orchestrator_service.src.core.config import get_settings

logger = logging.getLogger("ai-client")


class AIClient:
    """
    Simple AI Client for Orchestrator Service.
    Wraps AsyncOpenAI to provide generate and stream_chat methods.
    """

    def __init__(self) -> None:
        from openai import AsyncOpenAI, OpenAI

        settings = get_settings()
        if settings.OPENROUTER_API_KEY:
            api_key = settings.OPENROUTER_API_KEY
            base_url = "https://openrouter.ai/api/v1"
        else:
            api_key = settings.OPENAI_API_KEY
            base_url = None

        if not api_key:
            logger.warning("No API Key found for AI Client. AI features will fail.")

        self.client = AsyncOpenAI(
            api_key=api_key or "dummy-key",
            base_url=base_url,
        )

        self.sync_client = OpenAI(
            api_key=api_key or "dummy-key",
            base_url=base_url,
        )
        self.default_model = (
            "nvidia/nemotron-3-super-120b-a12b:free"  # Default model, can be overridden
        )

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
        """
        target_model = model or self.default_model
        if not messages:
            messages = [{"role": "user", "content": kwargs.get("prompt", "")}]

        try:
            return await self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                **kwargs,
            )
        except Exception as e:
            logger.error(f"AI Generation failed: {e}")
            raise

    async def stream_chat(
        self,
        messages: list[dict[str, str]],
        model: str | None = None,
        **kwargs: object,
    ) -> AsyncGenerator[ChatCompletionChunk, None]:
        """
        Stream chat completion.
        Yields chunks compatible with OpenAI structure.
        """
        target_model = model or self.default_model
        try:
            stream = await self.client.chat.completions.create(
                model=target_model,
                messages=messages,
                stream=True,
                **kwargs,
            )
            async for chunk in stream:
                yield chunk
        except Exception as e:
            logger.error(f"AI Stream failed: {e}")
            raise

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


# Singleton instance
ai_client = AIClient()


def get_ai_client() -> AIClient:
    return ai_client
