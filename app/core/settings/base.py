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
from urllib.parse import urlparse

# Override DATABASE_URL with APP_DATABASE_URL at import time so pydantic-settings
# picks up the Supabase URL instead of the Replit-managed local Postgres.
# Also rewrite port 6543 (PgBouncer transaction mode, no prepared statements)
# to port 5432 (Supabase session mode, full prepared statement support).
_app_db = os.environ.get("APP_DATABASE_URL")
if _app_db:
    if ":6543/" in _app_db:
        _app_db = _app_db.replace(":6543/", ":5432/")
    os.environ["DATABASE_URL"] = _app_db

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

    # Database — APP_DATABASE_URL takes priority over the Replit-managed DATABASE_URL
    APP_DATABASE_URL: str | None = Field(None, description="Override database connection URL")
    DATABASE_URL: str | None = Field(None, description="Database connection URL")

    @model_validator(mode="before")
    @classmethod
    def prefer_app_database_url(cls, values: dict) -> dict:
        """Use APP_DATABASE_URL when set, falling back to DATABASE_URL."""
        import os

        app_db = values.get("APP_DATABASE_URL") or os.environ.get("APP_DATABASE_URL")
        if app_db:
            values["DATABASE_URL"] = app_db
        return values

    # Security
    SECRET_KEY: str = Field(
        default_factory=_get_or_create_dev_secret_key,
        description="Master secret key",
    )

    # D-236 · ISS-152 — الوسطاء الذين يُصدَّق منهم `X-Forwarded-For` (CIDR مفصولة
    # بفواصل). فارغةً تعني الافتراض في `app/security/client_identity.py`: الحلقة
    # المحلّية وحدها. ⛔ قائمة سماح لا قائمة منع — الترويسة يزوّرها العميل بحرّية،
    # فالثقة بها بلا شرطٍ تُحوِّل حدّ المعدّل إلى زينة.
    TRUSTED_PROXY_IPS: str = Field(
        "",
        description="Comma-separated CIDRs whose X-Forwarded-For header is trusted",
    )

    @field_validator("TRUSTED_PROXY_IPS")
    @classmethod
    def validate_trusted_proxy_ips(cls, v: str) -> str:
        """قائمةُ سماحٍ خاطئة تُضيَّق **بصمت** — فتُرفَض عند الإقلاع لا عند الطلب.

        بلا هذا كان مُدخَلٌ مكتوبٌ خطأً يُتجاهَل بتحذيرٍ وقت الطلب، فينكمش نطاق
        الثقة دون أن يلاحظ المُشغِّل — وإعدادٌ أمنيٌّ يفشل صامتاً أسوأ من غيابه.
        رصدته مراجعة CodeRabbit.
        """
        import ipaddress

        for entry in (part.strip() for part in (v or "").split(",")):
            if not entry:
                continue
            try:
                ipaddress.ip_network(entry, strict=False)
            except ValueError as exc:
                raise ValueError(f"TRUSTED_PROXY_IPS: invalid CIDR {entry!r}") from exc
        return v

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
            if not self.DATABASE_URL or "sqlite" in (self.DATABASE_URL or ""):
                raise ValueError("DATABASE_URL must be set to a real database in production")
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
    # D-WS-002: القيم الافتراضية تشمل port 5000 (frontend في Codespaces/Gitpod/Ona)
    # وport 3000 (local dev). يمكن تجاوزها عبر BACKEND_CORS_ORIGINS env var.
    # النوع str | list[str] يسمح لـ pydantic-settings بتمرير CSV string إلى
    # field_validator بدلاً من محاولة parse JSON مباشرة.
    BACKEND_CORS_ORIGINS: str | list[str] = Field(
        default=[
            "http://localhost:3000",
            "http://localhost:5000",
            "http://127.0.0.1:3000",
            "http://127.0.0.1:5000",
        ]
    )
    # D-WS-002: ALLOWED_HOSTS يشمل Gitpod/Ona/Codespaces wildcard hosts.
    # TrustedHostMiddleware يرفض أي host غير موجود هنا بـ 400.
    # النوع str | list[str] يسمح بـ CSV في env var.
    ALLOWED_HOSTS: str | list[str] = Field(
        default=[
            "localhost",
            "127.0.0.1",
            "testserver",
            "test",
            # Gitpod / Ona (legacy *.gitpod.io + new *.gitpod.dev cluster domains)
            # D-WS-GITPOD-001: Gitpod Flex uses <PORT>--<ENV_ID>.<cluster>.gitpod.dev
            # e.g. 8000--019e6245-....eu-central-1-01.gitpod.dev
            "*.gitpod.io",
            "*.ws-eu.gitpod.io",
            "*.ws-us.gitpod.io",
            "*.gitpod.dev",
            "*.eu-central-1-01.gitpod.dev",
            "*.eu-central-1-02.gitpod.dev",
            "*.us-east-1-01.gitpod.dev",
            # GitHub Codespaces
            "*.app.github.dev",
            "*.preview.app.github.dev",
            # Replit
            "*.replit.dev",
            "*.replit.app",
            "*.janeway.replit.dev",
        ]
    )

    # Infra
    REDIS_URL: str | None = None
    # D-201 — ناقل الأحداث. الغياب ليس عطباً: بلا عنوان يعمل السائق في الذاكرة، فيبقى
    # مسار الأحداث كاملاً حيّاً بدل أن يكون قدرةً معلّقة على بنية تحتية غائبة (§6.6).
    KAFKA_BOOTSTRAP_SERVERS: str | None = Field(
        None, description="Kafka/Redpanda bootstrap servers; empty means the in-memory driver"
    )
    KAFKA_CLIENT_ID: str = Field("cogniforge-monolith", description="Kafka client id")
    TEMPORAL_ADDRESS: str | None = Field(
        None, description="Temporal frontend address; empty means workflows run inline"
    )
    TEMPORAL_NAMESPACE: str = Field("default", description="Temporal namespace")
    TEMPORAL_TASK_QUEUE: str = Field("cogniforge", description="Temporal task queue")
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
    ALLOW_CONTAINER_LOCALHOST_ORCHESTRATOR: bool = Field(
        False,
        description="يسمح باستخدام localhost للخدمة المنسقة داخل الحاوية فقط عند ضبطه صراحة.",
    )

    # AI (Missing fields restored)
    OPENAI_API_KEY: str | None = Field(None, description="OpenAI API Key")
    OPENROUTER_API_KEY: str | None = Field(None, description="OpenRouter API Key")
    AI_SERVICE_URL: str | None = Field(None, description="AI Service URL")

    # D-268 (ISS-191): `TAVILY_API_KEY` عبر ستّة أبواب ووصل العملية — ثم قرأه
    # كودُ `app/` بـ`os.environ` في موضعين، خرقاً مباشراً لقاعدة CLAUDE.md §6
    # («⛔ لا `os.environ` في كود التطبيق»). القاعدة كانت نثراً بلا فارض، وهو
    # بالضبط صنف العطب الذي عالجه D-188. الحقلُ هنا يجعل القراءة القانونية ممكنة،
    # وبوّابة `check_secret_capture_parity` تجعل غيرها مستحيلة.
    TAVILY_API_KEY: str | None = Field(None, description="Tavily web-search API key")
    # يُقرأ كإشارةِ توفّرٍ في `app/`، ومستهلكه الحيّ الوحيد `research_agent`.
    # ⚠️ ولا مسارَ التقاطٍ له اليوم (مذكورٌ في `docker-compose.legacy.yml` وحده)
    # — فجوةٌ **مُعلَنة** في `config/secret_catalog.json` لا مكتومة.
    FIRECRAWL_API_KEY: str | None = Field(None, description="Firecrawl web-search API key")

    # ── D-269: طبقة الهوية المعرفية المحيطة (Honcho) ─────────────────────────
    # ⚠️ في هذه المرحلة: **التقاطٌ ومسبارُ توفّرٍ حيّ فقط**. ⛔ لا تُرسَل بيانات
    # طالبٍ إلى أيّ طرفٍ ثالث — مسار الكتابة `SEAM` مُعلَنة بصفر كود، وشرط ترقيتها
    # منطوق في `.memory/ambient_identity_truth.md`. غيابُ المفتاح ليس عطلاً.
    HONCHO_API_KEY: str | None = Field(None, description="Honcho ambient-identity API key")
    HONCHO_BASE_URL: str = Field(
        "https://api.honcho.dev",
        description="Honcho API host. Not a secret — configuration, kept overridable for self-hosting.",
    )
    HONCHO_API_VERSION: str = Field(
        "v3",
        description="Honcho API version prefix. Measured live 2026-08-19: v3 answers, v2/v1 return 404.",
    )
    HONCHO_WORKSPACE_ID: str = Field(
        "ETAALIM",
        description="Honcho workspace the platform owns. Not a secret.",
    )
    HONCHO_PROBE_TIMEOUT_SECONDS: float = Field(
        5.0,
        description="Explicit probe timeout — an open wait on a third party turns slowness into a hang (D-189).",
    )

    # Codespaces / Dev Environment (Missing fields restored)
    CODESPACES: bool = Field(False, description="Is running in Codespaces")
    CODESPACE_NAME: str | None = Field(None, description="Codespace Name")
    GITHUB_CODESPACES_PORT_FORWARDING_DOMAIN: str | None = Field(None)
    # D-WS-002: port 5000 هو المنفذ الافتراضي للـ frontend في Codespaces/Gitpod/Ona
    FRONTEND_URL: str = Field(default="http://localhost:5000", description="Frontend URL")
    ENABLE_STATIC_FILES: bool = Field(
        True, description="Enable backend static file serving (disable for Next.js-only UI)."
    )
    SEMANTIC_TUTOR_ENABLED: bool = Field(
        True, description="D-142 Phase 2: تمكين مدير الحوار السقراطي الموحد (DialogueManagerSkill)"
    )
    COGNITIVE_TURN_ENABLED: bool = Field(
        True,
        description=(
            "D-158/D-159: طبقة القرار الموحَّدة _cognitive_turn فوق tutor_state. "
            "افتراض ON منذ D-159 (بعد نجاح E2E الحي — قاعدة D-158-f). الرجوع: env=0."
        ),
    )
    # Skills Platform — opt-in activation of dormant capabilities (default OFF → zero
    # behavior change unless explicitly enabled). Each gated skill returns None when off.
    ENABLE_RETRIEVAL_RERANK_SKILL: bool = Field(
        False,
        description="Enable RetrievalRerankSkill (LlamaIndex retrieval + CrossEncoder rerank).",
    )
    ENABLE_MCP_TOOL_SKILL: bool = Field(
        False, description="Enable MCPToolSkill (8-tool MCP bridge: list + call)."
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
            "RESEARCH_AGENT_URL": ("8007", "research-agent", "8007"),
            "PLANNING_AGENT_URL": ("8001", "planning-agent", "8000"),
            "REASONING_AGENT_URL": ("8008", "reasoning-agent", "8008"),
            "ORCHESTRATOR_SERVICE_URL": ("8006", "orchestrator-service", "8006"),
        }

        if field_name not in service_map:
            return "http://localhost:8000"

        local_port, host, docker_port = service_map[field_name]

        if is_codespaces:
            return f"http://localhost:{local_port}"

        return f"http://{host}:{docker_port}"

    @staticmethod
    def _is_container_runtime() -> bool:
        """يتحقق من التشغيل داخل حاوية Docker/Kubernetes لاكتشاف أخطاء اكتشاف الخدمات مبكرًا."""
        return (
            os.path.exists("/.dockerenv")
            or os.getenv("KUBERNETES_SERVICE_HOST") is not None
            or os.getenv("CONTAINER") == "true"
        )

    @model_validator(mode="after")
    def apply_codespaces_local_overrides(self) -> "AppSettings":
        """يضبط عناوين localhost في Codespaces عندما لا يحدد المطوّر روابط صريحة."""
        if not self.CODESPACES:
            return self

        env_to_attr = {
            "USER_SERVICE_URL": "USER_SERVICE_URL",
            "RESEARCH_AGENT_URL": "RESEARCH_AGENT_URL",
            "PLANNING_AGENT_URL": "PLANNING_AGENT_URL",
            "REASONING_AGENT_URL": "REASONING_AGENT_URL",
            "ORCHESTRATOR_SERVICE_URL": "ORCHESTRATOR_SERVICE_URL",
        }
        local_ports = {
            "USER_SERVICE_URL": "8003",
            "RESEARCH_AGENT_URL": "8007",
            "PLANNING_AGENT_URL": "8001",
            "REASONING_AGENT_URL": "8008",
            "ORCHESTRATOR_SERVICE_URL": "8006",
        }

        for env_name, attr_name in env_to_attr.items():
            if os.getenv(env_name):
                continue
            setattr(self, attr_name, f"http://localhost:{local_ports[attr_name]}")

        return self

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

    @model_validator(mode="after")
    def validate_orchestrator_service_discovery(self) -> "AppSettings":
        """يفرض عدم استخدام localhost بين الخدمات داخل الحاويات إلا بتصريح صريح."""
        orchestrator_url = self.ORCHESTRATOR_SERVICE_URL or ""
        hostname = (urlparse(orchestrator_url).hostname or "").lower()
        is_localhost = hostname in {"localhost", "127.0.0.1"}
        if not is_localhost:
            return self

        running_in_container = self._is_container_runtime()
        explicit_allowance = self.ALLOW_CONTAINER_LOCALHOST_ORCHESTRATOR
        if self.CODESPACES:
            return self

        if running_in_container and not explicit_allowance:
            raise ValueError(
                "ORCHESTRATOR_SERVICE_URL points to localhost داخل بيئة حاوية. "
                "استخدم DNS داخلياً مثل http://orchestrator-service:8006 أو فعّل "
                "ALLOW_CONTAINER_LOCALHOST_ORCHESTRATOR صراحةً في بيئة التطوير فقط."
            )

        return self


@functools.lru_cache
def get_settings() -> AppSettings:
    """Singleton accessor for AppSettings."""
    return AppSettings()
