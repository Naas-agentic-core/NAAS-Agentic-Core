"""اختبارات حوكمة الملكية لمنع ازدواجية المسارات وانزياح الـ control-plane."""

from __future__ import annotations

import json
from pathlib import Path

REGISTRY_PATH = Path("config/route_ownership_registry.json")


def _load_registry() -> dict[str, object]:
    return json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))


def test_critical_domains_have_single_owner_target_pair() -> None:
    """يضمن أن chat/content/mission domains لها زوج ملكية/هدف وحيد في ملف السجل."""
    payload = _load_registry()
    routes: list[dict[str, object]] = payload["routes"]

    critical_groups: dict[str, list[dict[str, object]]] = {
        "chat": [
            route
            for route in routes
            if str(route["route_id"]).startswith("chat_")
            or str(route["public_path"]).startswith("/api/chat")
            or str(route["public_path"]).startswith("/admin/api/chat")
        ],
        "missions": [route for route in routes if "missions" in str(route["public_path"])],
        "content": [route for route in routes if "content" in str(route["public_path"])],
    }

    for domain, domain_routes in critical_groups.items():
        assert domain_routes, f"Expected routes for domain={domain}"
        owner_target_pairs = {
            (str(route["owner"]), str(route["target_service"])) for route in domain_routes
        }
        assert len(owner_target_pairs) == 1, (
            f"Domain {domain} has conflicting ownership pairs: {owner_target_pairs}"
        )


def test_no_default_legacy_target_for_critical_domains() -> None:
    """يمنع إعادة تفعيل legacy target افتراضيًا لمسارات chat/mission/content الحرجة."""
    payload = _load_registry()
    routes: list[dict[str, object]] = payload["routes"]

    critical_routes = [
        route
        for route in routes
        if any(
            token in str(route["public_path"])
            for token in ("/api/chat", "/admin/api/chat", "/missions", "/content")
        )
    ]
    assert critical_routes, "Expected critical routes to be present"

    for route in critical_routes:
        assert route.get("default_profile") is True
        assert bool(route.get("legacy_target", False)) is False
