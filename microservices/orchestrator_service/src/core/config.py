import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, ValidationInfo, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Unified Configuration for Orchestrator Service.
    Safe defaults, environment-aware, and decoupled from Monolith.
    """

    # Service Identity
    SERVICE_NAME: str = "orchestrator-service"
    SERVICE_VERSION: str = "1.0.0"
    PROJECT_NAME: str = "Orchestrator Service"

    # Environment
    ENVIRONMENT: Literal["development", "staging", "production", "testing"] = Field(
        "development", description="Operational environment"
    )
    DEBUG: bool = Field(False, description="Debug mode")
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Logging level"
    )
    CODESPACES: bool = Field(False, description="Is running in GitHub Codespaces")

    # Security
    SECRET_KEY: str = Field(default="dev_secret_key", validation_alias="SECRET_KEY")
    API_V1_STR: str = "/api/v1"
    ADMIN_TOOL_API_KEY: str | None = Field(
        default=None,
        description="Shared key for internal admin-tool endpoints",
    )

    # CORS
    BACKEND_CORS_ORIGINS: list[str] = Field(default=["*"], description="CORS Allowed Origins")

    # Database
    POSTGRES_USER: str = "postgres"
    POSTGRES_PASSWORD: str = "password"
    POSTGRES_HOST: str = "localhost"
    POSTGRES_DB: str = "orchestrator_db"
    POSTGRES_PORT: int = 5432
    DATABASE_URL: str = Field(default="", validation_alias="ORCHESTRATOR_DATABASE_URL")

    # Redis
    REDIS_URL: str = "redis://localhost:6379"

    # Outbox Relay (disabled by default for safe incremental rollout)
    OUTBOX_RELAY_ENABLED: bool = False
    OUTBOX_RELAY_INTERVAL_SECONDS: int = 15
    OUTBOX_RELAY_BATCH_SIZE: int = 50
    OUTBOX_RELAY_MAX_FAILED_ATTEMPTS: int = 3
    OUTBOX_RELAY_PROCESSING_TIMEOUT_SECONDS: int = 300

    # AI Config
    OPENAI_API_KEY: str | None = Field(None, description="OpenAI API Key")
    OPENROUTER_API_KEY: str | None = Field(None, description="OpenRouter API Key")

    # Microservices URLs (Dynamic Resolution)
    PLANNING_AGENT_URL: str | None = Field(default=None, validate_default=True)
    MEMORY_AGENT_URL: str | None = Field(default=None, validate_default=True)
    RESEARCH_AGENT_URL: str | None = Field(default=None, validate_default=True)
    REASONING_AGENT_URL: str | None = Field(default=None, validate_default=True)
    USER_SERVICE_URL: str | None = Field(default=None, validate_default=True)

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @field_validator("CODESPACES", mode="before")
    @classmethod
    def detect_codespaces(cls, v: object) -> bool:
        if v is not None:
            return bool(v)
        return os.getenv("CODESPACES") == "true"

    @field_validator(
        "USER_SERVICE_URL",
        "RESEARCH_AGENT_URL",
        "PLANNING_AGENT_URL",
        "REASONING_AGENT_URL",
        "MEMORY_AGENT_URL",
        mode="before",
    )
    @classmethod
    def resolve_service_urls(cls, v: str | None, info: ValidationInfo) -> str:
        """
        Resolves service URLs based on environment (Docker vs Local/Codespaces).
        """
        if v:
            return v

        field_name = info.field_name
        is_codespaces = info.data.get("CODESPACES")
        if is_codespaces is None:
            is_codespaces = os.getenv("CODESPACES") == "true"

        service_map = {
            "USER_SERVICE_URL": ("8003", "user-service", "8000"),
            "RESEARCH_AGENT_URL": ("8007", "research-agent", "8007"),
            "PLANNING_AGENT_URL": ("8001", "planning-agent", "8000"),
            "REASONING_AGENT_URL": ("8008", "reasoning-agent", "8008"),
            "MEMORY_AGENT_URL": ("8002", "memory-agent", "8000"),
        }

        if field_name not in service_map:
            return "http://localhost:8000"

        local_port, host, docker_port = service_map[field_name]
        if is_codespaces:
            return f"http://localhost:{local_port}"
        return f"http://{host}:{docker_port}"

    def model_post_init(self, __context: object) -> None:
        if not self.DATABASE_URL:
            self.DATABASE_URL = (
                f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD}"
                f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}"
            )

    @model_validator(mode="after")
    def validate_production_security(self) -> "Settings":
        """Enforces security rules in production and staging."""
        if self.ENVIRONMENT in ("production", "staging"):
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production")
            if self.SECRET_KEY == "dev_secret_key" or len(self.SECRET_KEY) < 32:
                raise ValueError("SECRET_KEY must be strong in production")
            if self.BACKEND_CORS_ORIGINS == ["*"]:
                raise ValueError("SECURITY RISK: BACKEND_CORS_ORIGINS cannot be '*' in production.")
            if not self.ADMIN_TOOL_API_KEY or len(self.ADMIN_TOOL_API_KEY) < 24:
                raise ValueError(
                    "ADMIN_TOOL_API_KEY must be configured and strong in production/staging"
                )

        if self.OUTBOX_RELAY_INTERVAL_SECONDS < 1:
            raise ValueError("OUTBOX_RELAY_INTERVAL_SECONDS must be >= 1")

        if self.OUTBOX_RELAY_BATCH_SIZE < 1 or self.OUTBOX_RELAY_BATCH_SIZE > 500:
            raise ValueError("OUTBOX_RELAY_BATCH_SIZE must be between 1 and 500")

        if self.OUTBOX_RELAY_MAX_FAILED_ATTEMPTS < 1 or self.OUTBOX_RELAY_MAX_FAILED_ATTEMPTS > 20:
            raise ValueError("OUTBOX_RELAY_MAX_FAILED_ATTEMPTS must be between 1 and 20")

        if self.OUTBOX_RELAY_PROCESSING_TIMEOUT_SECONDS < 5:
            raise ValueError("OUTBOX_RELAY_PROCESSING_TIMEOUT_SECONDS must be >= 5")

        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
