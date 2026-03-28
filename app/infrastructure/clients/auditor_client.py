import logging
import os

import httpx

from app.core.protocols import AgentReflector, CollaborationContext

logger = logging.getLogger(__name__)


class AuditorClient(AgentReflector):
    """
    HTTP Client for the Auditor Microservice.
    Implements AgentReflector protocol but delegates to remote service.
    """

    def __init__(self, base_url: str = "http://localhost:8002"):
        # Allow override via env var
        self.base_url = os.environ.get("AUDITOR_SERVICE_URL", base_url)
        self.timeout = float(os.environ.get("AUDITOR_TIMEOUT", "60.0"))

    async def review_work(
        self, result: dict[str, object], original_objective: str, context: CollaborationContext
    ) -> dict[str, object]:
        """
        Remote call to Auditor Service for work review.
        """
        url = f"{self.base_url}/review"

        # Prepare Payload (Pydantic Schema)
        payload = {
            "result": result,
            "original_objective": original_objective,
            "context": context.shared_memory,  # Extract dict from context object
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                # The service returns strict schema: approved, feedback, score, final_response
                # The protocol expects a dict. Pydantic handles validation on service side.
                return response.json()

        except httpx.HTTPError as e:
            logger.error(f"Auditor Service unreachable: {e}")
            # Fallback for resilience (Circuit Breaker logic could go here)
            return {
                "approved": False,
                "feedback": f"Service Error: {e!s}",
                "score": 0.0,
                "final_response": "**System Error:** Auditor Service is offline.",
            }
        except Exception as e:
            logger.error(f"Auditor Client Error: {e}")
            return {
                "approved": False,
                "feedback": f"Client Error: {e!s}",
                "score": 0.0,
                "final_response": "**System Error:** Client failure.",
            }

    async def consult(self, situation: str, analysis: dict[str, object]) -> dict[str, object]:
        """
        Remote call to Auditor Service for consultation.
        """
        url = f"{self.base_url}/consult"

        payload = {"situation": situation, "analysis": analysis}

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, json=payload)
                response.raise_for_status()
                return response.json()

        except Exception as e:
            logger.error(f"Auditor Service Consultation Failed: {e}")
            return {
                "recommendation": "Service unavailable. Proceed with caution.",
                "confidence": 0.0,
            }

    def detect_loop(self, history_hashes: list[str], current_plan: dict[str, object]) -> None:
        """
        Loop detection is a lightweight logic that can remain client-side
        or move to server. For now, we keep it local or implement a naive version.

        Original implementation was local. We can either:
        1. Move logic to server (new endpoint)
        2. Keep local (if it doesn't require heavy dependencies)

        Let's keep a simple local implementation to avoid network overhead for hash checks.
        """
        # Re-implement basic check locally to satisfy protocol
        import hashlib
        import json

        try:
            encoded = json.dumps(current_plan, sort_keys=True, default=str).encode("utf-8")
            current_hash = hashlib.sha256(encoded).hexdigest()

            if history_hashes.count(current_hash) >= 2:
                raise RuntimeError("Infinite loop detected by Client.")
        except Exception as e:
            logger.warning(f"Loop detection failed: {e}")

    def compute_plan_hash(self, plan: dict[str, object]) -> str:
        """
        Compute hash locally.
        """
        import hashlib
        import json

        try:
            encoded = json.dumps(plan, sort_keys=True, default=str).encode("utf-8")
            return hashlib.sha256(encoded).hexdigest()
        except Exception:
            return "unknown"
