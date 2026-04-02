from __future__ import annotations

from pathlib import Path

from microservices.orchestrator_service.src.api.routes import _safe_conversation_id


def test_safe_conversation_id_parses_string_and_int() -> None:
    assert _safe_conversation_id("42") == 42
    assert _safe_conversation_id(42) == 42
    assert _safe_conversation_id(None) is None
    assert _safe_conversation_id("abc") is None
    assert _safe_conversation_id("") is None



def test_frontend_no_longer_forces_string_conversation_id() -> None:
    source = Path("frontend/app/hooks/useAgentSocket.js").read_text(encoding="utf-8")
    assert "payload.conversation_id = String(conversationId)" not in source
    assert "Number.parseInt(String(conversationId), 10)" in source



def test_gateway_has_explicit_admin_conversation_routes_before_admin_catch_all() -> None:
    source = Path("microservices/api_gateway/main.py").read_text(encoding="utf-8")
    explicit_route = source.find('"/admin/api/conversations"')
    catch_all_route = source.find('"/admin/{path:path}"')
    assert explicit_route != -1
    assert catch_all_route != -1
    assert explicit_route < catch_all_route


def test_frontend_fetches_limited_conversations_and_dedupes() -> None:
    source = Path("frontend/app/components/CogniForgeApp.jsx").read_text(encoding="utf-8")
    assert "?limit=50" in source
    assert "const uniqueMap = new Map();" in source
    assert "setConversations(Array.from(uniqueMap.values()));" in source


def test_orchestrator_conversation_list_endpoints_are_limited() -> None:
    source = Path("microservices/orchestrator_service/src/api/routes.py").read_text(
        encoding="utf-8"
    )
    assert "limit: int = Query(default=50, ge=1, le=200)" in source
    assert "LIMIT :limit" in source
