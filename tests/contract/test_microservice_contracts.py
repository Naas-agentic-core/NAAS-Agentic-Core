"""اختبارات عقود OpenAPI للخدمات المصغرة."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

import pytest
from fastapi import FastAPI

from app.core.openapi_contracts import compare_contract_to_runtime, detect_runtime_drift
from app.main import create_app as create_core_app

CONTRACTS_DIR = Path(__file__).resolve().parents[2] / "docs" / "contracts" / "openapi"


def _contract_path(filename: str) -> Path:
    return CONTRACTS_DIR / filename


def _get_planning_app() -> FastAPI:
    from microservices.planning_agent.main import create_app

    return create_app()


def _get_memory_app() -> FastAPI:
    from microservices.memory_agent.main import create_app

    return create_app()


def _get_user_app() -> FastAPI:
    from microservices.user_service.main import create_app

    return create_app()


def _get_observability_app() -> FastAPI:
    from microservices.observability_service.main import app

    return app


def _build_cases() -> list[tuple[str, Callable[[], FastAPI] | FastAPI, str]]:
    return [
        ("core", lambda: create_core_app(enable_static_files=False), "core-api-v1.yaml"),
        ("planning", _get_planning_app, "planning_agent-openapi.json"),
        ("memory", _get_memory_app, "memory_agent-openapi.json"),
        ("user", _get_user_app, "user_service-openapi.json"),
        ("observability", _get_observability_app, "observability_service-openapi.json"),
    ]


# Paths migrated from Monolith Core
MIGRATED_PATHS = {
    "/admin/ai-config",
    "/admin/audit",
    "/admin/users",
    "/admin/users/{user_id}/roles",
    "/admin/users/{user_id}/status",
    "/api/missions",
    "/api/missions/{mission_id}",
    "/api/observability/aiops",
    "/api/observability/alerts",
    "/api/observability/analytics/{path}",
    "/api/observability/gitops",
    "/api/observability/health",
    "/api/observability/metrics",
    "/api/observability/performance",
    "/api/v1/agents/langgraph/run",
    "/api/v1/agents/plan",
    "/api/v1/agents/plan/{plan_id}",
    "/api/v1/overmind/missions",
    "/api/v1/overmind/missions/{mission_id}",
    "/auth/login",
    "/auth/logout",
    "/auth/password/forgot",
    "/auth/password/reset",
    "/auth/reauth",
    "/auth/refresh",
    "/auth/register",
    "/qa/question",
    "/admin/api/chat/ws",
    "/api/chat/ws",
    "/users/me",
    "/users/me/change-password",
}


@pytest.mark.parametrize("service_name, app_source, contract_file", _build_cases())
def test_contract_alignment_for_services(
    service_name: str,
    app_source: Callable[[], FastAPI] | FastAPI,
    contract_file: str,
) -> None:
    """يتحقق من تطابق مخطط التشغيل مع عقد OpenAPI لكل خدمة."""

    app = _resolve_app(app_source)
    contract_path = _contract_path(contract_file)
    contract_operations = _load_contract_operations(contract_path)

    # Filter expected contract for Monolith
    if service_name == "core":
        contract_operations = {
            path: methods
            for path, methods in contract_operations.items()
            if path not in MIGRATED_PATHS
        }

    contract_comparison = compare_contract_to_runtime(
        contract_operations=contract_operations,
        runtime_schema=app.openapi(),
    )
    assert contract_comparison.is_clean(), (
        f"عقد الخدمة {service_name} يحتوي على مسارات أو عمليات مفقودة: "
        f"paths={sorted(contract_comparison.missing_paths)}, "
        f"operations={ {path: sorted(methods) for path, methods in contract_comparison.missing_operations.items()} }"
    )


@pytest.mark.parametrize("service_name, app_source, contract_file", _build_cases())
def test_no_undocumented_paths_or_operations(
    service_name: str,
    app_source: Callable[[], FastAPI] | FastAPI,
    contract_file: str,
) -> None:
    """يتحقق من عدم وجود مسارات أو عمليات غير موثقة في التشغيل."""

    app = _resolve_app(app_source)
    contract_path = _contract_path(contract_file)
    contract_operations = _load_contract_operations(contract_path)

    # Note: We don't filter MIGRATED_PATHS here because this test checks for *extra* paths in runtime.
    # If the contract still has them but the runtime doesn't, that's handled by test_contract_alignment_for_services.
    # If the runtime has paths not in contract, that's what this tests.

    drift_report = detect_runtime_drift(
        contract_operations=contract_operations,
        runtime_schema=app.openapi(),
    )
    assert drift_report.is_clean(), (
        f"الخدمة {service_name} تعرض مسارات أو عمليات غير موثقة: "
        f"paths={sorted(drift_report.unexpected_paths)}, "
        f"operations={ {path: sorted(methods) for path, methods in drift_report.unexpected_operations.items()} }"
    )


def _load_contract_operations(contract_path: Path) -> dict[str, set[str]]:
    """يحمل عمليات العقد مع ضمان وجودها قبل الفحص."""

    from app.core.openapi_contracts import load_contract_operations

    operations = load_contract_operations(contract_path)
    assert operations, f"عقد OpenAPI فارغ أو غير قابل للتحميل: {contract_path}"
    return operations


def _resolve_app(app_source: Callable[[], FastAPI] | FastAPI) -> FastAPI:
    """يعيد تطبيق FastAPI حتى لو كان الكائن قابلاً للاستدعاء."""
    if isinstance(app_source, FastAPI):
        return app_source
    return app_source()
