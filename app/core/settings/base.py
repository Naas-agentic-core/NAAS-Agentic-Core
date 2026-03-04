"""
Unified Configuration System for CogniForge.

This module provides the canonical `AppSettings` and `get_settings()`
implementation, strictly following the Phase 2 refactoring plan.

Standards:
- Single Source of Truth: All services use this settings schema.
- Strict Types: No object, use Pydantic V2.
- Environment Awareness: Automatic detection and validation.
- Secure Defaults: Safe by design.
"""

import functools
import os
from typing import Literal

from pydantic import Field, ValidationInfo, computed_field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from .helpers import (
    _ensure_database_url,
    _get_or_create_dev_secret_key,
    _is_valid_email,
    _lenient_json_loads,
    _normalize_csv_or_list,
    _normalize_postgres_ssl,
    _upgrade_postgres_protocol,
)

# -----------------------------------------------------------------------------
# Base Settings (Shared across all services)
# -----------------------------------------------------------------------------


class BaseServiceSettings(BaseSettings):
    """
    Base configuration for all microservices.
    Enforces consistent environment, logging, and database patterns.
    """

    # Service Identity
    SERVICE_NAME: str = Field(..., description="Name of the service")
    SERVICE_VERSION: str = Field("0.1.0", description="Service version")

    # Environment
    ENVIRONMENT: Literal["development", "staging", "production", "testing"] = Field(
        "development", description="Operational environment"
    )
    DEBUG: bool = Field(False, description="Debug mode")

    # Logging
    LOG_LEVEL: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = Field(
        "INFO", description="Logging level"
    )

    # Database
    DATABASE_URL: str | None = Field(None, description="Database connection URL")

    # Security
    SECRET_KEY: str = Field(
        default_factory=_get_or_create_dev_secret_key,
        description="Master secret key",
    )

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        env_json_loads=_lenient_json_loads,
        extra="ignore",
    )

    @field_validator("DATABASE_URL", mode="before")
    @classmethod
    def validate_database_url(cls, v: str | None, info: ValidationInfo) -> str:
        """Heals and validates the database URL."""
        env = info.data.get("ENVIRONMENT", "development")
        url = _ensure_database_url(v, env)
        # Note: _upgrade_postgres_protocol also handles Supabase Pooler compatibility
        upgraded = _upgrade_postgres_protocol(url)
        return _normalize_postgres_ssl(upgraded)

    @model_validator(mode="after")
    def validate_security(self) -> "BaseServiceSettings":
        """Enforces security rules based on environment."""
        if self.ENVIRONMENT == "production":
            if "SECRET_KEY" not in self.__pydantic_fields_set__:
                raise ValueError("SECRET_KEY must be set in production")
            if self.DEBUG:
                raise ValueError("DEBUG must be False in production")
            if self.SECRET_KEY == "changeme" or len(self.SECRET_KEY) < 32:
                raise ValueError("Production SECRET_KEY is too weak")
        return self

    @computed_field
    @property
    def is_production(self) -> bool:
        """Returns True if we are in production mode."""
        return self.ENVIRONMENT == "production"


# -----------------------------------------------------------------------------
# Main App Settings (Legacy Monolith + Gateway)
# -----------------------------------------------------------------------------


class AppSettings(BaseServiceSettings):
    """
    Configuration for the main application (Monolith/Gateway).
    Inherits from BaseServiceSettings for consistency.
    """

    SERVICE_NAME: str = "CogniForge-Core"
    PROJECT_NAME: str = Field("CogniForge", description="Project Name")
    VERSION: str = Field("4.0.0-legendary", description="System Version")
    DESCRIPTION: str = Field("AI-Powered Platform", description="System Description")

    # API
    API_V1_STR: str = "/api/v1"
    API_STRICT_MODE: bool = Field(True, description="Strict API Security")

    # CORS & Hosts
    BACKEND_CORS_ORIGINS: list[str] = Field(default=["*"])
    ALLOWED_HOSTS: list[str] = Field(default=["*"])

    # Infra
    REDIS_URL: str | None = None
    DB_POOL_SIZE: int = Field(40, description="DB Pool Size")
    DB_MAX_OVERFLOW: int = Field(60, description="DB Max Overflow")

    # Admin
    ADMIN_EMAIL: str = "admin@cogniforge.com"
    ADMIN_PASSWORD: str = "change_me_please_123!"
    ADMIN_NAME: str = "Supreme Administrator"

    # Service URLs
    USER_SERVICE_URL: str | None = Field(None, description="User service base URL")
    RESEARCH_AGENT_URL: str | None = Field(None, description="Research Agent URL")
    PLANNING_AGENT_URL: str | None = Field(None, description="Planning Agent URL")
    REASONING_AGENT_URL: str | None = Field(None, description="Reasoning Agent URL")
    ORCHESTRATOR_SERVICE_URL: str | None = Field(None, description="Orchestrator Service URL")

    # AI (Missing fields restored)
    OPENAI_API_KEY: str | None = Field(None, description="OpenAI API Key")
    OPENROUTER_API_KEY: str | None = Field(None, description="OpenRouter API Key")
    AI_SERVICE_URL: str | None = Field(None, description="AI Service URL")

    # Codespaces / Dev Environment (Missing fields restored)
    CODESPACES: bool = Field(False, description="Is running in Codespaces")
    CODESPACE_NAME: str | None = Field(None, description="Codespace Name")
    GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN: str | None = Field(None)
    FRONTEND_URL: str = Field(default="http://localhost:3000", description="Frontend URL")
    ENABLE_STATIC_FILES: bool = Field(
        True, description="Enable backend static file serving (disable for Next.js-only UI)."
    )

    # Security (Tokens)
    ACCESS_TOKEN_EXPIRE_MINUTES: int = Field(60 * 24 * 8, description="Access Token Expiry")
    REAUTH_TOKEN_EXPIRE_MINUTES: int = Field(10, description="Re-auth Token Expiry")

    @field_validator("BACKEND_CORS_ORIGINS", "ALLOWED_HOSTS", mode="before")
    @classmethod
    def assemble_list(cls, v: str | list[str] | None) -> list[str]:
        return _normalize_csv_or_list(v)

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
        "ORCHESTRATOR_SERVICE_URL",
        mode="before",
    )
    @classmethod
    def default_service_urls(cls, v: str | None, info: ValidationInfo) -> str:
        """
        Ensure default service URLs based on the environment (Codespaces vs Docker).
        """
        if v:
            return v

        field_name = info.field_name
        is_codespaces = info.data.get("CODESPACES")
        if is_codespaces is None:
            is_codespaces = os.getenv("CODESPACES") == "true"

        return cls._resolve_service_url(field_name, bool(is_codespaces))

    @staticmethod
    def _resolve_service_url(field_name: str, is_codespaces: bool) -> str:
        """
        Resolves the default URL for a service based on the environment.
        """
        # Map field names to (localhost_port, docker_host, docker_port)
        service_map = {
            "USER_SERVICE_URL": ("8003", "user-service", "8000"),
            "RESEARCH_AGENT_URL": ("8006", "research-agent", "8000"),
            "PLANNING_AGENT_URL": ("8001", "planning-agent", "8000"),
            "REASONING_AGENT_URL": ("8007", "reasoning-agent", "8000"),
            "ORCHESTRATOR_SERVICE_URL": ("8006", "orchestrator-service", "8006"),
        }

        if field_name not in service_map:
            return "http://localhost:8000"

        local_port, host, docker_port = service_map[field_name]

        if is_codespaces:
            return f"http://localhost:{local_port}"

        return f"http://{host}:{docker_port}"

    @model_validator(mode="after")
    def validate_production_security(self) -> "AppSettings":
        """ضوابط صارمة لأمان بيئات الإنتاج."""
        if self.ENVIRONMENT in ("production", "staging"):
            if self.ALLOWED_HOSTS == ["*"]:
                raise ValueError(
                    "SECURITY RISK: ALLOWED_HOSTS cannot be '*' in production/staging."
                )
            if self.BACKEND_CORS_ORIGINS == ["*"]:
                raise ValueError(
                    "SECURITY RISK: BACKEND_CORS_ORIGINS cannot be '*' in production/staging."
                )
        return self

    @model_validator(mode="after")
    def validate_admin_credentials(self) -> "AppSettings":
        """يفرض ضبط بيانات اعتماد المسؤول بشكل آمن في بيئة الإنتاج."""
        if (
            self.ENVIRONMENT == "production"
            and not self.CODESPACES
            and not os.getenv("PYTEST_CURRENT_TEST")
        ):
            admin_password = self.ADMIN_PASSWORD.strip()
            admin_email = self.ADMIN_EMAIL.strip().lower()

            if not admin_password:
                raise ValueError("ADMIN_PASSWORD must be set in production")
            if admin_password == "change_me_please_123!":
                raise ValueError("ADMIN_PASSWORD must be changed from default in production")
            if len(admin_password) < 12:
                raise ValueError("ADMIN_PASSWORD must be at least 12 characters in production")
            if not admin_email or admin_email == "admin@cogniforge.com":
                raise ValueError("ADMIN_EMAIL must be customized in production")
            if not _is_valid_email(admin_email):
                raise ValueError("ADMIN_EMAIL must be a valid email address in production")
        return self


@functools.lru_cache
def get_settings() -> AppSettings:
    """Singleton accessor for AppSettings."""
    return AppSettings()
