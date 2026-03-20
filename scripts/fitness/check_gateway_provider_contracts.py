"""يتحقق من التزام بوابة API بعقود chat/content (HTTP + WS) ومنع الانحراف قبل الدمج."""

from __future__ import annotations

import ast
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTRACT_PATH = REPO_ROOT / "docs/contracts/consumer/gateway_chat_content_contracts.json"
GATEWAY_MAIN = REPO_ROOT / "microservices/api_gateway/main.py"
GATEWAY_CONFIG = REPO_ROOT / "microservices/api_gateway/config.py"


def _load_contract() -> dict[str, object]:
    data = json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))
    if "http" not in data or "websocket" not in data:
        raise ValueError("Contract must define both http and websocket sections")
    return data


def _collect_route_paths() -> tuple[set[str], set[str]]:
    tree = ast.parse(GATEWAY_MAIN.read_text(encoding="utf-8"))
    http_routes: set[str] = set()
    ws_routes: set[str] = set()

    for node in ast.walk(tree):
        if not isinstance(node, ast.AsyncFunctionDef):
            continue
        for decorator in node.decorator_list:
            if not isinstance(decorator, ast.Call) or not isinstance(decorator.func, ast.Attribute):
                continue
            if not decorator.args:
                continue
            first_arg = decorator.args[0]
            if not isinstance(first_arg, ast.Constant) or not isinstance(first_arg.value, str):
                continue
            route = first_arg.value
            if decorator.func.attr == "api_route":
                http_routes.add(route)
            if decorator.func.attr == "websocket":
                ws_routes.add(route)

    return http_routes, ws_routes


def _collect_config_names() -> set[str]:
    tree = ast.parse(GATEWAY_CONFIG.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            names.add(node.target.id)
    return names


def main() -> int:
    if not CONTRACT_PATH.exists():
        print("❌ Missing provider contract file for gateway chat/content.")
        return 1

    contract = _load_contract()
    http_routes, ws_routes = _collect_route_paths()
    config_names = _collect_config_names()

    missing_http = [item["route"] for item in contract["http"] if item["route"] not in http_routes]
    missing_ws = [item["route"] for item in contract["websocket"] if item["route"] not in ws_routes]

    missing_toggles: list[str] = []
    for item in contract["http"]:
        toggle = item.get("legacy_toggle")
        if isinstance(toggle, str) and toggle not in config_names:
            missing_toggles.append(toggle)
    for item in contract["websocket"]:
        legacy_toggle = item.get("legacy_toggle")
        ttl_toggle = item.get("ttl_toggle")
        if isinstance(legacy_toggle, str) and legacy_toggle not in config_names:
            missing_toggles.append(legacy_toggle)
        if isinstance(ttl_toggle, str) and ttl_toggle not in config_names:
            missing_toggles.append(ttl_toggle)

    if missing_http or missing_ws or missing_toggles:
        print("❌ Gateway provider verification failed.")
        if missing_http:
            print(f"   Missing HTTP routes: {sorted(missing_http)}")
        if missing_ws:
            print(f"   Missing WS routes: {sorted(missing_ws)}")
        if missing_toggles:
            print(f"   Missing toggles in config: {sorted(set(missing_toggles))}")
        return 1

    print("✅ Gateway provider verification passed for chat/content HTTP+WS contracts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
