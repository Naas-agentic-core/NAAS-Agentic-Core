import os
import threading
from datetime import datetime

from app.services.api_config_secrets.application.config_secrets_manager import (
    ConfigSecretsManager,
    ConfigSetting,
    SecretRequest,
)
from app.services.api_config_secrets.domain.models import (
    ConfigEntry,
    Environment,
    EnvironmentConfig,
    RotationPolicy,
    Secret,
    SecretAccessLog,
    SecretType,
)
from app.services.api_config_secrets.domain.ports import VaultBackend
from app.services.api_config_secrets.infrastructure.memory_adapters import (
    InMemoryAuditLogger,
    InMemoryConfigRepository,
    InMemorySecretMetadataRepository,
)
from app.services.api_config_secrets.infrastructure.vault_adapters import (
    AWSSecretsManagerBackend,
    HashiCorpVaultBackend,
    LocalVaultBackend,
    SecretEncryption,
)

__all__ = [
    "AWSSecretsManagerBackend",
    "ConfigEntry",
    "ConfigSecretsService",
    "ConfigSetting",
    "Environment",
    "EnvironmentConfig",
    "HashiCorpVaultBackend",
    "LocalVaultBackend",
    "RotationPolicy",
    "Secret",
    "SecretAccessLog",
    "SecretEncryption",
    "SecretRequest",
    "SecretType",
    "VaultBackend",
    "get_config_secrets_service",
]


class ConfigSecretsService:
    """واجهة مبسطة تبقي إدارة الإعدادات والأسرار واضحة للمبتدئين."""

    def __init__(self, vault_backend: VaultBackend | None = None):
        self._vault = vault_backend or LocalVaultBackend()
        self._config_repo = InMemoryConfigRepository()
        self._secret_repo = InMemorySecretMetadataRepository()
        self._audit_logger = InMemoryAuditLogger()
        self._manager = ConfigSecretsManager(
            vault_backend=self._vault,
            config_repo=self._config_repo,
            secret_metadata_repo=self._secret_repo,
            audit_logger=self._audit_logger,
        )

    @property
    def vault(self) -> VaultBackend:
        return self._manager.vault

    @property
    def lock(self) -> threading.Lock:
        return self._config_repo._lock  # type: ignore

    def set_config(self, setting: ConfigSetting) -> None:
        """تطبيق إعداد تكوين من كائن موحد يسهل قراءته ومراجعته."""

        self._manager.set_config(setting)

    def get_config(
        self, environment: Environment, key: str, default: object | None = None
    ) -> object | None:
        """الحصول على قيمة إعداد مع دعم قيمة افتراضية واضحة."""
        return self._manager.get_config(environment, key, default)

    def create_secret(self, request: SecretRequest) -> str:
        """إنشاء سر جديد بالاعتماد على طلب موحّد قابل للتدقيق."""

        return self._manager.create_secret(request)

    def get_secret(self, secret_id: str, accessed_by: str = "system") -> str | None:
        """قراءة السر من الخزينة عبر الواجهة الميسّرة."""
        return self._manager.get_secret(secret_id, accessed_by)

    def rotate_secret(self, secret_id: str, new_value: str, accessed_by: str = "system") -> bool:
        """تدوير السر إلى قيمة جديدة مع الحفاظ على التوافق الخلفي."""
        return self._manager.rotate_secret(secret_id, new_value, accessed_by)

    def check_rotation_needed(self) -> list[str]:
        """تجميع قائمة بالأسرار التي تحتاج تدويراً حالياً."""
        return self._manager.check_rotation_needed()

    def _calculate_next_rotation(self, from_date: datetime, policy: RotationPolicy) -> datetime:
        """تمرير مباشر لحساب موعد التدوير لتسهيل الاختبارات المتخصصة."""

        return self._manager._calculate_next_rotation(from_date, policy)

    def _log_access(
        self,
        secret_id: str,
        accessed_by: str,
        action: str,
        success: bool,
        reason: str | None = None,
    ) -> None:
        """تسجيل الوصول للأسرار من طبقة الواجهة للاستخدامات الاختبارية."""

        self._manager._log_access(secret_id, accessed_by, action, success, reason)

    def get_environment_config(self, environment: Environment) -> EnvironmentConfig:
        """استرجاع التكوين الكامل لبيئة معينة مع الإحالات إلى الأسرار."""
        return self._manager.get_environment_config(environment)

    def get_audit_report(
        self, secret_id: str | None = None, accessed_by: str | None = None, limit: int = 1000
    ) -> list[dict[str, object]]:
        """الحصول على تقرير تدقيق الوصول عبر الواجهة المجمّعة."""
        return self._manager.get_audit_report(secret_id, accessed_by, limit)


_config_secrets_instance: ConfigSecretsService | None = None
_config_lock = threading.Lock()


def get_config_secrets_service() -> ConfigSecretsService:
    """استرجاع نسخة الخدمة الأحادية المسؤولة عن الإعدادات والأسرار."""
    global _config_secrets_instance
    if _config_secrets_instance is None:
        with _config_lock:
            if _config_secrets_instance is None:
                vault_type = os.environ.get("VAULT_BACKEND", "local")
                if vault_type == "hashicorp":
                    vault_url = os.environ.get("VAULT_URL", "http://localhost:8200")
                    vault_token = os.environ.get("VAULT_TOKEN", "")
                    backend = HashiCorpVaultBackend(vault_url, vault_token)
                elif vault_type == "aws":
                    region = os.environ.get("AWS_REGION", "us-east-1")
                    backend = AWSSecretsManagerBackend(region)
                else:
                    backend = LocalVaultBackend()
                _config_secrets_instance = ConfigSecretsService(vault_backend=backend)
    return _config_secrets_instance
