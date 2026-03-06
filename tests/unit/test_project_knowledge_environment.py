"""اختبارات توصيفية لمعلومات البيئة في معرفة المشروع."""

from app.core.config import get_settings
from microservices.orchestrator_service.src.services.overmind.knowledge import ProjectKnowledge


def _reset_settings_cache() -> None:
    """يمسح ذاكرة التخزين المؤقت لإعدادات التطبيق لضمان قراءة بيئة جديدة."""
    get_settings.cache_clear()


def test_environment_info_defaults(monkeypatch) -> None:
    """يتحقق من أن المعلومات الافتراضية تعكس غياب إعدادات الذكاء والبيئات."""
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("GITPOD_WORKSPACE_ID", raising=False)
    monkeypatch.delenv("CODESPACES", raising=False)
    _reset_settings_cache()

    knowledge = ProjectKnowledge()
    env_info = knowledge.get_environment_info()

    assert env_info["environment"] == "testing"
    assert env_info["ai_configured"] is False
    assert env_info["supabase_configured"] is False
    assert env_info["runtime"]["codespaces"] is False
    assert env_info["runtime"]["gitpod"] is False
    assert env_info["runtime"]["local"] is True


def test_environment_info_runtime_flags(monkeypatch) -> None:
    """يتحقق من تفعيل أعلام البيئة عند ضبط المتغيرات الخاصة بها."""
    monkeypatch.setenv("ENVIRONMENT", "testing")
    monkeypatch.setenv("OPENROUTER_API_KEY", "dummy-key")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("GITPOD_WORKSPACE_ID", "workspace")
    monkeypatch.setenv("CODESPACES", "true")
    _reset_settings_cache()

    knowledge = ProjectKnowledge()
    env_info = knowledge.get_environment_info()

    assert env_info["ai_configured"] is True
    assert env_info["supabase_configured"] is True
    assert env_info["runtime"]["codespaces"] is True
    assert env_info["runtime"]["gitpod"] is True
    assert env_info["runtime"]["local"] is False
