"""
Planning Agent Client.
Provides a typed interface to the Planning Agent Microservice.
Decouples the Monolith from the Planning Logic.
"""

from __future__ import annotations

from typing import Any, Final

import httpx

from microservices.orchestrator_service.src.core.config import get_settings
from microservices.orchestrator_service.src.core.http_client_factory import (
    HTTPClientConfig,
    get_http_client,
)
from microservices.orchestrator_service.src.core.logging import get_logger

logger = get_logger("planning-client")

DEFAULT_PLANNING_AGENT_URL: Final[str] = "http://planning-agent:8000"


class PlanningClient:
    """
    Client for interacting with the Planning Agent microservice.
    """

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        resolved_url = base_url or settings.PLANNING_AGENT_URL or DEFAULT_PLANNING_AGENT_URL
        self.base_url = resolved_url.rstrip("/")
        self.config = HTTPClientConfig(
            name="planning-agent-client",
            timeout=60.0,
            max_connections=50,
        )

    async def _get_client(self) -> httpx.AsyncClient:
        return get_http_client(self.config)

    async def create_plan(
        self, objective: str, context: dict[str, object] | list[str]
    ) -> dict[str, object]:
        """
        Request a strategic plan from the Planning Agent.
        """
        url = f"{self.base_url}/plans"

        # Ensure context is JSON serializable
        # If context is a list of strings, pass it as is (API supports both but prefers dict for future)
        # If context is CollaborationContext.shared_memory (dict), pass it.

        payload = {"objective": objective, "context": context}

        client = await self._get_client()
        try:
            logger.info(f"Requesting plan for objective: {objective[:50]}...")
            response = await client.post(url, json=payload)
            response.raise_for_status()

            # PlanResponse structure: {plan_id, goal, strategy_name, reasoning, steps: [...]}
            return response.json()

        except Exception as e:
            logger.error(f"Planning failed: {e}", exc_info=True)
            # Fallback or re-raise
            raise


# Singleton
planning_client = PlanningClient()
