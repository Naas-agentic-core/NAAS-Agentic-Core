"""
Orchestrator Client.
Provides a typed interface to the Orchestrator Service.
Decouples the Monolith from the Overmind Orchestration Logic.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import AsyncGenerator
from pathlib import Path
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.core.http_client_factory import HTTPClientConfig, get_http_client
from app.core.settings.base import get_settings

logger = logging.getLogger("orchestrator-client")


class MissionResponse(BaseModel):
    id: int
    objective: str
    status: str
    outcome: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    result: dict[str, object] | None = None
    steps: list[dict[str, object]] = []


class OrchestratorClient:
    """
    Client for interacting with the Orchestrator Service.
    """

    def __init__(self, base_url: str | None = None) -> None:
        settings = get_settings()
        # Ensure we strictly use the configuration from settings to avoid routing to 'localhost'
        # within isolated Docker containers and ensure robust Microservices service discovery.
        env_url = getattr(settings, "ORCHESTRATOR_SERVICE_URL", None)
        resolved_url = base_url or env_url
        if not resolved_url:
            raise RuntimeError("ORCHESTRATOR_SERVICE_URL must be configured")

        self.base_url = resolved_url.rstrip("/")
        self.config = HTTPClientConfig(
            name="orchestrator-client",
            timeout=60.0,
            max_connections=50,
        )

    def _build_chat_url_candidates(self) -> list[str]:
        """يبني قائمة مرتبة لمسارات الدردشة المحتملة لضمان الاستمرارية عبر البيئات المختلفة."""
        base_candidates: list[str] = [self.base_url]

        fallback_urls_raw = os.getenv("ORCHESTRATOR_SERVICE_FALLBACK_URLS", "")
        fallback_bases = [url.strip().rstrip("/") for url in fallback_urls_raw.split(",") if url.strip()]
        base_candidates.extend(fallback_bases)

        parsed = urlparse(self.base_url)
        if parsed.hostname in {"localhost", "127.0.0.1"}:
            base_candidates.extend([
                "http://orchestrator-service:8006",
                "http://host.docker.internal:8006",
            ])
        else:
            base_candidates.extend([
                "http://localhost:8006",
                "http://127.0.0.1:8006",
            ])

        unique_bases: list[str] = []
        for candidate in base_candidates:
            if candidate and candidate not in unique_bases:
                unique_bases.append(candidate)

        return [f"{base}/agent/chat" for base in unique_bases]

    def _is_python_file_count_question(self, question: str) -> bool:
        """يتحقق مما إذا كان السؤال يطلب حساب عدد ملفات بايثون داخل المشروع."""
        normalized = question.strip().lower()
        indicators = [
            "كم عدد ملفات بايثون",
            "عدد ملفات بايثون",
            "python files",
            "how many python files",
        ]
        return any(indicator in normalized for indicator in indicators)

    def _count_python_files_in_project(self) -> int:
        """يحسب عدد ملفات Python داخل جذر المشروع مع استثناء الأدلة الضخمة وغير المرتبطة."""
        project_root = Path(__file__).resolve().parents[3]
        ignored_dirs = {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            ".mypy_cache",
        }

        count = 0
        for py_file in project_root.rglob("*.py"):
            if any(part in ignored_dirs for part in py_file.parts):
                continue
            count += 1
        return count

    async def _get_client(self) -> httpx.AsyncClient:
        return get_http_client(self.config)

    async def create_mission(
        self,
        objective: str,
        context: dict[str, object] | None = None,
        priority: int = 1,
        idempotency_key: str | None = None,
    ) -> MissionResponse:
        """
        Create and start a mission via the Orchestrator Service.
        """
        url = f"{self.base_url}/missions"
        payload = {
            "objective": objective,
            "context": context or {},
            "priority": priority,
        }
        headers = {}
        if idempotency_key:
            headers["X-Correlation-ID"] = idempotency_key

        client = await self._get_client()
        try:
            logger.info(f"Dispatching mission to Orchestrator: {objective[:50]}...")
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return MissionResponse(**data)
        except Exception as e:
            logger.error(f"Failed to create mission: {e}", exc_info=True)
            raise

    async def get_mission(self, mission_id: int) -> MissionResponse | None:
        """
        Get mission details.
        """
        url = f"{self.base_url}/missions/{mission_id}"
        client = await self._get_client()
        try:
            response = await client.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            data = response.json()
            return MissionResponse(**data)
        except Exception as e:
            logger.error(f"Failed to get mission {mission_id}: {e}")
            raise

    async def get_mission_events(self, mission_id: int) -> list[dict]:
        """
        Get mission events from the Orchestrator Service.
        """
        url = f"{self.base_url}/missions/{mission_id}/events"
        client = await self._get_client()
        try:
            response = await client.get(url)
            if response.status_code == 404:
                return []
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Failed to get mission events {mission_id}: {e}")
            return []

    async def chat_with_agent(
        self,
        question: str,
        user_id: int,
        conversation_id: int | None = None,
        history_messages: list[dict[str, str]] | None = None,
        context: dict[str, object] | None = None,
    ) -> AsyncGenerator[dict | str, None]:
        """
        Chat with the Orchestrator Agent (Microservice).
        Expects NDJSON stream from the service.
        Yields either structured event dictionaries or fallback strings.
        """
        payload = {
            "question": question,
            "user_id": user_id,
            "conversation_id": conversation_id,
            "history_messages": history_messages or [],
            "context": context or {},
        }

        candidate_urls = self._build_chat_url_candidates()
        client = await self._get_client()
        connection_errors: list[str] = []

        for candidate_url in candidate_urls:
            try:
                logger.info("Attempting orchestrator chat endpoint", extra={"url": candidate_url})
                response: httpx.Response | None = None

                async for attempt in AsyncRetrying(
                    stop=stop_after_attempt(2),
                    wait=wait_exponential(multiplier=1, min=1, max=4),
                    retry=retry_if_exception_type((httpx.ConnectError, httpx.TimeoutException)),
                    reraise=True,
                ):
                    with attempt:
                        request = client.build_request("POST", candidate_url, json=payload)
                        response = await client.send(request, stream=True)

                if response is None:
                    continue

                try:
                    response.raise_for_status()
                    async for line in response.aiter_lines():
                        if not line.strip():
                            continue
                        try:
                            yield json.loads(line)
                        except json.JSONDecodeError:
                            logger.warning(f"Received non-JSON line from agent: {line[:50]}...")
                            yield {"type": "assistant_delta", "payload": {"content": line}}
                    return
                finally:
                    await response.aclose()

            except Exception as e:
                connection_errors.append(f"{candidate_url} => {e}")
                logger.error("Orchestrator chat endpoint failed", exc_info=True)

        diagnostic = " | ".join(connection_errors) if connection_errors else "No endpoint attempted"
        logger.error("Failed to chat with agent across all endpoints", extra={"diagnostic": diagnostic})

        if self._is_python_file_count_question(question):
            files_count = self._count_python_files_in_project()
            yield (
                f"عدد ملفات بايثون في المشروع هو: {files_count} ملف. "
                "(تم تفعيل وضع الطوارئ المحلي بسبب تعذر الاتصال بخدمة orchestrator)"
            )
            return

        user_facing_error = (
            "تعذر الوصول إلى خدمة الوكيل حالياً. "
            "تحقق من تشغيل orchestrator-service أو اضبط ORCHESTRATOR_SERVICE_URL بشكل صحيح."
        )

        try:
            yield json.dumps(
                {
                    "type": "assistant_error",
                    "payload": {
                        "content": f"{user_facing_error} (diagnostic: {diagnostic})",
                    },
                }
            )
        except Exception as e:
            logger.error(f"Failed to chat with agent: {e}", exc_info=True)
            yield json.dumps(
                {
                    "type": "assistant_error",
                    "payload": {"content": "تعذر إنشاء استجابة خطأ من خدمة الوكيل."},
                }
            )


# Singleton
orchestrator_client = OrchestratorClient()
