from __future__ import annotations

import os
from urllib.parse import urlparse

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """إعدادات بوابة الواجهات مع ضوابط صارمة لاكتشاف الخدمات وحماية الإنتاج."""

    # Service URLs (Defaults for local development/Docker Compose)
    PLANNING_AGENT_URL: str = "http://planning-agent:8001"
    MEMORY_AGENT_URL: str = "http://memory-agent:8002"
    USER_SERVICE_URL: str = "http://user-service:8003"
    OBSERVABILITY_SERVICE_URL: str = "http://observability-service:8005"
    RESEARCH_AGENT_URL: str = "http://research-agent:8007"
    REASONING_AGENT_URL: str = "http://reasoning-agent:8008"
    ORCHESTRATOR_SERVICE_URL: str = "http://orchestrator-service:8006"
    CONVERSATION_SERVICE_URL: str = "http://conversation-service:8010"
    CORE_KERNEL_URL: str | None = None

    # Deployment profile
    ENVIRONMENT: str = "development"
    ALLOWED_HOSTS: list[str] = Field(default_factory=lambda: ["*"])
    BACKEND_CORS_ORIGINS: list[str] = Field(default_factory=lambda: ["*"])
    ALLOW_CONTAINER_LOCALHOST_ORCHESTRATOR: bool = False

    # Per-route cutover flags (Phase 0 defaults keep behavior unchanged)
    ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT: int = 0
    ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT: int = 0

    # Candidate target for WS cutover (kept disabled by default in PR#1)
    CONVERSATION_WS_URL: str = "ws://conversation-service:8010"

    # Gateway Configuration
    API_V1_STR: str = "/api/v1"
    PROJECT_NAME: str = "CogniForge API Gateway"
    SECRET_KEY: str = "super_secret_key_change_in_production"

    # Resiliency Settings
    CONNECT_TIMEOUT: float = 5.0
    READ_TIMEOUT: float = 60.0
    WRITE_TIMEOUT: float = 60.0
    POOL_LIMIT: int = 100

    # Circuit Breaker Settings
    CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = 5
    CIRCUIT_BREAKER_RECOVERY_TIMEOUT: float = 30.0

    # Retry Settings
    MAX_RETRIES: int = 3
    RETRY_BACKOFF_FACTOR: float = 0.5

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=True, extra="ignore"
    )

    @staticmethod
    def _is_container_runtime() -> bool:
        """يكشف بيئات الحاويات/العنقود لمنع localhost كوجهة بين الخدمات دون تصريح."""
        return (
            os.path.exists("/.dockerenv")
            or os.getenv("KUBERNETES_SERVICE_HOST") is not None
            or os.getenv("CONTAINER") == "true"
        )

    @model_validator(mode="after")
    def validate_security_and_discovery(self) -> Settings:
        """يفرض الأمان في الإنتاج ويمنع drift في ORCHESTRATOR_SERVICE_URL داخل الحاويات."""
        env = self.ENVIRONMENT.lower()
        if env in {"production", "staging"}:
            if (
                self.SECRET_KEY == "super_secret_key_change_in_production"
                or len(self.SECRET_KEY) < 32
            ):
                raise ValueError("SECRET_KEY غير آمن لبيئة production/staging")
            if self.ALLOWED_HOSTS == ["*"]:
                raise ValueError("ALLOWED_HOSTS لا يمكن أن تكون '*' في production/staging")
            if self.BACKEND_CORS_ORIGINS == ["*"]:
                raise ValueError("BACKEND_CORS_ORIGINS لا يمكن أن تكون '*' في production/staging")

        host = (urlparse(self.ORCHESTRATOR_SERVICE_URL).hostname or "").lower()
        if (
            host in {"localhost", "127.0.0.1"}
            and self._is_container_runtime()
            and not self.ALLOW_CONTAINER_LOCALHOST_ORCHESTRATOR
        ):
            raise ValueError(
                "ORCHESTRATOR_SERVICE_URL يشير إلى localhost داخل حاوية. "
                "استخدم DNS داخلياً مثل orchestrator-service أو فعّل المتغير "
                "ALLOW_CONTAINER_LOCALHOST_ORCHESTRATOR صراحة في التطوير المحلي فقط."
            )

        return self


settings = Settings()
