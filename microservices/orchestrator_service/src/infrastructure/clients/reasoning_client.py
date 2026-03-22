"""
Reasoning Agent Client.
Provides a typed interface to the Reasoning Agent Microservice.
Decouples the Monolith from Deep Reasoning Logic.
"""

from __future__ import annotations

from typing import Final

import httpx

from microservices.orchestrator_service.src.core.config import get_settings
from microservices.orchestrator_service.src.core.http_client_factory import (
    HTTPClientConfig,
    get_http_client,
)
from microservices.orchestrator_service.src.core.logging import get_logger

logger = get_logger("reasoning-client")

DEFAULT_REASONING_AGENT_URL: Final[str] = "http://reasoning-agent:8000"


class ReasoningClient:
    """
    Client for interacting with the Reasoning Agent microservice.
    Uses 'SuperReasoningWorkflow' via the /execute endpoint.
    """

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        resolved_url = base_url or settings.REASONING_AGENT_URL or DEFAULT_REASONING_AGENT_URL
        self.base_url = resolved_url.rstrip("/")
        self.config = HTTPClientConfig(
            name="reasoning-agent-client",
            timeout=120.0,  # Deep reasoning is slow
            max_connections=50,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        return get_http_client(self.config)

    async def reason_deeply(self, query: str) -> dict[str, object]:
        """
        Request deep reasoning analysis.
        """
        url = f"{self.base_url}/execute"

        payload = {"caller_id": "app-backend", "action": "reason", "payload": {"query": query}}

        client = await self._get_client()
        try:
            logger.info(f"Requesting reasoning for: {query[:50]}...")
            response = await client.post(url, json=payload)
            response.raise_for_status()

            data = response.json()
            # AgentResponse: {status, data: {answer, logic_trace}, error}

            if data.get("status") != "success":
                error_msg = data.get("error", "Unknown error")
                logger.error(f"Reasoning agent returned error: {error_msg}")
                return {"error": error_msg}

            return data.get("data", {})

        except Exception as e:
            logger.error(f"Reasoning request failed: {e}", exc_info=True)
            return {"error": str(e)}


# Singleton
reasoning_client = ReasoningClient()
