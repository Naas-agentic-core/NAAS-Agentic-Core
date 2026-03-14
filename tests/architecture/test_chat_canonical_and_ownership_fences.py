"""حواجز معمارية لمنع توسع split-brain في مسارات chat وملكية نماذج mission."""

from __future__ import annotations

from pathlib import Path


def test_chat_routers_keep_compatibility_facade_and_canonical_authority() -> None:
    """يثبت أن مسارات chat في التطبيق تبقى واجهات توافقية وتفويضها للمنسق الرسمي."""

    admin_router = Path("app/api/routers/admin.py").read_text(encoding="utf-8")
    customer_router = Path("app/api/routers/customer_chat.py").read_text(encoding="utf-8")

    assert 'COMPATIBILITY_FACADE_MODE = True' in admin_router
    assert 'COMPATIBILITY_FACADE_MODE = True' in customer_router
    assert 'CANONICAL_EXECUTION_AUTHORITY = "app.services.chat.orchestrator.ChatOrchestrator"' in admin_router
    assert (
        'CANONICAL_EXECUTION_AUTHORITY = "app.services.chat.orchestrator.ChatOrchestrator"'
        in customer_router
    )


def test_gateway_remains_canonical_runtime_entry_for_chat_paths() -> None:
    """يثبت أن البوابة تملك نقاط الدخول العامة لمسارات chat (HTTP/WS) بشكل صريح."""

    gateway_main = Path("microservices/api_gateway/main.py").read_text(encoding="utf-8")

    assert '@app.websocket("/api/chat/ws")' in gateway_main
    assert '@app.websocket("/admin/api/chat/ws")' in gateway_main
    assert '@app.api_route(' in gateway_main
    assert '"/api/chat/{path:path}"' in gateway_main


def test_orchestrator_state_uses_microservice_mission_models_only() -> None:
    """يمنع توسيع ازدواجية الملكية عبر تثبيت مصدر النماذج داخل خدمة orchestrator."""

    state_module = Path(
        "microservices/orchestrator_service/src/services/overmind/state.py"
    ).read_text(encoding="utf-8")

    assert "from microservices.orchestrator_service.src.models.mission import (" in state_module
    assert "from app.core.domain.mission import" not in state_module


def test_orchestrator_routes_do_not_import_monolith_api_surfaces() -> None:
    """يمنع توسيع split-brain عبر استيراد واجهات monolith داخل مسارات orchestrator."""

    routes_module = Path("microservices/orchestrator_service/src/api/routes.py").read_text(
        encoding="utf-8"
    )

    assert "from app.api" not in routes_module
    assert "from app.services.chat" not in routes_module
