"""اختبارات صارمة لمنع drift في اكتشاف الخدمات عبر البيئات المختلفة."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.settings.base import AppSettings
from microservices.api_gateway.config import Settings as GatewaySettings


@pytest.mark.parametrize(
    ("field_name", "expected_host"),
    [
        ("USER_SERVICE_URL", "http://user-service:8000"),
        ("PLANNING_AGENT_URL", "http://planning-agent:8000"),
        ("RESEARCH_AGENT_URL", "http://research-agent:8007"),
        ("REASONING_AGENT_URL", "http://reasoning-agent:8008"),
        ("ORCHESTRATOR_SERVICE_URL", "http://orchestrator-service:8006"),
    ],
)
def test_service_defaults_match_compose_dns(field_name: str, expected_host: str) -> None:
    """يتأكد أن القيم الافتراضية في بيئة الحاويات تستخدم DNS داخلياً وليس localhost."""
    settings = AppSettings(SECRET_KEY="x" * 40, CODESPACES=False)
    assert getattr(settings, field_name) == expected_host


def test_codespaces_localhost_is_explicit_dev_path() -> None:
    """يسمح بـ localhost فقط في مسار Codespaces المحلي الصريح."""
    settings = AppSettings(SECRET_KEY="x" * 40, CODESPACES=True)
    assert settings.ORCHESTRATOR_SERVICE_URL == "http://localhost:8006"


def test_gateway_rejects_localhost_in_container_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    """يرفض البوابة عند تشغيلها في حاوية مع ORCHESTRATOR_SERVICE_URL=localhost دون تصريح."""
    monkeypatch.setattr("microservices.api_gateway.config.os.path.exists", lambda _: True)
    with pytest.raises(ValidationError):
        GatewaySettings(ORCHESTRATOR_SERVICE_URL="http://localhost:8006")


def test_gateway_allows_localhost_in_container_only_when_explicit(monkeypatch: pytest.MonkeyPatch) -> None:
    """يسمح بالـ localhost داخل الحاوية فقط عند تفعيل المتغير الصريح."""
    monkeypatch.setattr("microservices.api_gateway.config.os.path.exists", lambda _: True)
    settings = GatewaySettings(
        ORCHESTRATOR_SERVICE_URL="http://localhost:8006",
        ALLOW_CONTAINER_LOCALHOST_ORCHESTRATOR=True,
    )
    assert settings.ORCHESTRATOR_SERVICE_URL == "http://localhost:8006"
