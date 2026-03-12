"""
Orchestrator Client.
Provides a typed interface to the Orchestrator Service.
Decouples the Monolith from the Overmind Orchestration Logic.
"""

from __future__ import annotations

import json
import logging
import uuid
from collections.abc import AsyncGenerator

import httpx
from pydantic import BaseModel
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_exponential

from app.contracts.chat_events import ChatEventEnvelope, ChatEventPayload, ChatEventType
from app.core.http_client_factory import HTTPClientConfig, get_http_client
from app.core.settings.base import get_settings
from app.infrastructure.clients.routing_policy import ChatRoutingPolicy
from app.services.capabilities.exercise_retrieval import (
    ExerciseRetrievalRequest,
    detect_exercise_retrieval,
)
from app.services.capabilities.exercise_retrieval import (
    make_result as make_exercise_result,
)
from app.services.capabilities.file_intelligence import (
    FileIntelligenceRequest,
    build_file_count_command,
    default_project_root,
    detect_file_intelligence,
)
from app.services.capabilities.file_intelligence import (
    make_result as make_file_result,
)

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
        """يبني مرشّحات التوجيه عبر سياسة مركزية تمنع split-brain إلا في وضع breakglass."""
        policy = ChatRoutingPolicy.from_environment(self.base_url)
        return policy.candidate_urls()

    def _file_intelligence_decision(self, question: str) -> tuple[bool, str | None]:
        """يستدعي قدرة ذكاء الملفات الرسمية لإنتاج قرار موحد."""
        decision = detect_file_intelligence(FileIntelligenceRequest(question=question))
        return decision.recognized, decision.extension

    def _exercise_retrieval_decision(self, question: str) -> bool:
        """يستدعي قدرة استرجاع التمارين الرسمية لتوحيد eligibility."""
        decision = detect_exercise_retrieval(ExerciseRetrievalRequest(question=question))
        return decision.recognized






    async def _execute_shell_tool(
        self,
        command: str,
        cwd: str,
        timeout: int = 30,
    ) -> dict[str, object]:
        """ينفذ أداة shell عبر طبقة الأدوات لضمان حساب حقيقي قائم على التنفيذ الفعلي."""
        from app.services.agent_tools.shell_tool import execute_shell

        return await execute_shell(command=command, cwd=cwd, timeout=timeout)

    async def _count_files_in_project(self, extension: str | None = None) -> int | None:
        """يحسب عدد الملفات فعلياً عبر shell ويعيد None عند فشل التنفيذ أو التحليل."""
        project_root = default_project_root()
        command = build_file_count_command(extension=extension)
        shell_result = await self._execute_shell_tool(command=command, cwd=project_root, timeout=45)

        if not shell_result.get("success"):
            logger.warning("Local shell file-count command failed", extra={"result": shell_result})
            return None

        stdout_value = str(shell_result.get("stdout", "")).strip()
        if not stdout_value:
            return None

        first_line = stdout_value.splitlines()[0].strip()
        if not first_line.isdigit():
            logger.warning(
                "Shell output is not a numeric file count", extra={"stdout": stdout_value}
            )
            return None

        return int(first_line)

    async def _build_local_file_count_response(self, question: str) -> str | None:
        """ينشئ رداً محلياً بعد تنفيذ عدّ احترافي حقيقي عبر القدرة الرسمية لذكاء الملفات."""
        recognized, extension = self._file_intelligence_decision(question)
        if not recognized:
            return None

        files_count = await self._count_files_in_project(extension=extension)
        result = make_file_result(extension=extension, count=files_count)
        return result.message


    async def _build_local_retrieval_response(self, question: str) -> str | None:
        """ينفذ استرجاعاً محلياً للمعرفة التعليمية عند تعطل service control plane."""
        if not self._exercise_retrieval_decision(question):
            return None

        try:
            from app.services.chat.tools.retrieval.service import search_educational_content

            result = await search_educational_content(query=question)
            normalized = make_exercise_result(result)
            return normalized.message
        except Exception:
            logger.warning("local_retrieval_fallback_failed", exc_info=True)
            return None

    @staticmethod
    def _sanitize_text_for_user(content: str) -> str:
        """يعقّم نصًا موجّهًا للمستخدم النهائي من أي تلميحات طوبولوجيا داخلية."""
        lowered = content.lower()
        blocked_tokens = (
            "orchestrator-service",
            "localhost",
            "127.0.0.1",
            "host.docker.internal",
            "orchestrator_service_url",
            "diagnostic",
        )
        if any(token in lowered for token in blocked_tokens):
            return "تعذر إتمام طلبك حالياً بسبب ضغط أو عطل مؤقت في خدمة المحادثة. حاول مرة أخرى بعد لحظات."
        return content

    def _normalize_stream_event(self, raw_event: object) -> dict[str, object]:
        """يوحد شكل أحداث التدفق ويضمن عدم تسريب تفاصيل داخلية في مسارات الأخطاء."""
        if isinstance(raw_event, dict):
            raw_type = str(raw_event.get("type", ChatEventType.ASSISTANT_DELTA.value))
            payload = raw_event.get("payload")
            if not isinstance(payload, dict):
                payload = {"content": str(raw_event)}
        else:
            raw_type = ChatEventType.ASSISTANT_DELTA.value
            payload = {"content": str(raw_event)}

        safe_payload = {
            "content": self._sanitize_text_for_user(str(payload.get("content", "")))
            if payload.get("content") is not None
            else None,
            "details": self._sanitize_text_for_user(str(payload.get("details", "")))
            if payload.get("details") is not None
            else None,
            "status_code": payload.get("status_code") if isinstance(payload.get("status_code"), int) else None,
            "request_id": str(payload.get("request_id")) if payload.get("request_id") is not None else None,
            "retry_hint": str(payload.get("retry_hint")) if payload.get("retry_hint") is not None else None,
        }

        event_type_map = {
            "assistant_delta": ChatEventType.ASSISTANT_DELTA,
            "assistant_final": ChatEventType.ASSISTANT_FINAL,
            "assistant_error": ChatEventType.ASSISTANT_ERROR,
            "status": ChatEventType.STATUS,
        }
        envelope = ChatEventEnvelope(
            type=event_type_map.get(raw_type, ChatEventType.ASSISTANT_DELTA),
            payload=ChatEventPayload(**safe_payload),
        )
        return envelope.model_dump(exclude_none=True)

    @staticmethod
    def _sanitize_error_for_user(*, request_id: str) -> dict[str, object]:
        """ينتج رسالة خطأ آمنة للمستخدم بدون أي تفاصيل طوبولوجيا أو تشخيص داخلي."""
        return {
            "type": "assistant_error",
            "payload": {
                "content": "تعذر إتمام طلبك حالياً بسبب ضغط أو عطل مؤقت في خدمة المحادثة. حاول مرة أخرى بعد لحظات.",
                "request_id": request_id,
                "retry_hint": "يمكنك إعادة المحاولة بعد دقيقة.",
            },
        }

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

        routing_policy = ChatRoutingPolicy.from_environment(self.base_url)
        candidate_urls = routing_policy.candidate_urls()
        client = await self._get_client()
        request_id = str(uuid.uuid4())
        connection_errors: list[str] = []
        contract_version = routing_policy.contract_version
        fallback_enabled = routing_policy.fallback_enabled

        logger.info(
            "chat_contract_route_start",
            extra={
                "request_id": request_id,
                "contract_version": contract_version,
                "candidate_count": len(candidate_urls),
                "fallback_enabled": fallback_enabled,
            },
        )

        for candidate_url in candidate_urls:
            try:
                logger.info(
                    "chat_routing_attempt",
                    extra={"candidate_url": candidate_url, "request_id": request_id},
                )
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
                            parsed_line = json.loads(line)
                            yield self._normalize_stream_event(parsed_line)
                        except json.JSONDecodeError:
                            logger.warning(f"Received non-JSON line from agent: {line[:50]}...")
                            yield self._normalize_stream_event(line)
                    return
                finally:
                    await response.aclose()

            except Exception as e:
                connection_errors.append(f"{candidate_url} => {e}")
                logger.error(
                    "chat_routing_failed",
                    exc_info=True,
                    extra={"request_id": request_id, "candidate_url": candidate_url},
                )

        diagnostic = " | ".join(connection_errors) if connection_errors else "No endpoint attempted"
        logger.error(
            "Failed to chat with agent across all endpoints", extra={"diagnostic": diagnostic}
        )

        if fallback_enabled:
            local_file_count_response = await self._build_local_file_count_response(question)
            if local_file_count_response:
                yield local_file_count_response
                return

            local_retrieval_response = await self._build_local_retrieval_response(question)
            if local_retrieval_response:
                yield local_retrieval_response
                return

        try:
            yield json.dumps(
                self._sanitize_error_for_user(request_id=request_id), ensure_ascii=False
            )
        except Exception as e:
            logger.error(f"Failed to chat with agent: {e}", exc_info=True)
            yield json.dumps(
                self._sanitize_error_for_user(request_id=request_id), ensure_ascii=False
            )


# Singleton
orchestrator_client = OrchestratorClient()
