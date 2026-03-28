"""
Hyper-Core Registry & Decorators
================================
The central nervous system of the toolset.
"""

import time
from collections.abc import Callable

from .core_execution import _execute_tool_with_error_handling
from .core_metrics import _enrich_result_metadata, _record_invocation
from .core_models import ToolExecutionContext, ToolExecutionInfo
from .core_registration import _register_tool_metadata
from .definitions import __version__
from .globals import _ALIAS_INDEX, _CAPABILITIES, _REGISTRY_LOCK, _TOOL_REGISTRY
from .utils import _generate_trace_id, _lower

# ======================================================================================
# Canonicalization
# ======================================================================================


def canonicalize_tool_name(raw_name: str, description: str = "") -> tuple[str, list[str]]:
    """
    Canonicalize tool name.
    Simplified version.
    """
    canonical, notes = raw_name, []

    name = _lower(canonical)
    if name in _TOOL_REGISTRY and not _TOOL_REGISTRY[name].get("is_alias"):
        notes.append("canonical_exact")
        return name, notes
    if name in _ALIAS_INDEX:
        notes.append("direct_alias_hit")
        return _ALIAS_INDEX[name], notes

    return canonical, notes


def resolve_tool_name(name: str) -> str | None:
    canon, _ = canonicalize_tool_name(name)
    if canon in _TOOL_REGISTRY and not _TOOL_REGISTRY[canon].get("is_alias"):
        return canon
    if canon in _ALIAS_INDEX:
        return _ALIAS_INDEX[canon]
    return None


def has_tool(name: str) -> bool:
    return resolve_tool_name(name) is not None


def get_tool(name: str) -> dict[str, object] | None:
    canonical_name = resolve_tool_name(name)
    if not canonical_name:
        return None
    return _TOOL_REGISTRY.get(canonical_name)


def list_tools(include_aliases: bool = False) -> list[dict[str, object]]:
    tools = []
    for meta in _TOOL_REGISTRY.values():
        if not include_aliases and meta.get("is_alias"):
            continue
        tools.append(meta)
    return tools


# ======================================================================================
# Tool Decorator
# ======================================================================================


def tool(
    name: str,
    description: str,
    parameters: dict[str, object] | None = None,
    *,
    category: str = "general",
    aliases: list[str] | None = None,
    allow_disable: bool = True,
    capabilities: list[str] | None = None,
) -> None:
    """
    Decorator for registering tools in the tool registry.

    محدد لتسجيل الأدوات في سجل الأدوات.

    Args:
        name: Tool name
        description: Tool description
        parameters: JSON schema for tool parameters
        category: Tool category
        aliases: List of alternative names
        allow_disable: Whether tool can be disabled
        capabilities: List of tool capabilities
    """
    parameters = parameters or {"type": "object", "properties": {}}
    aliases = aliases or []
    capabilities = capabilities or []

    def decorator(func: Callable[..., object]) -> None:
        with _REGISTRY_LOCK:
            _register_tool_metadata(
                name, description, parameters, category, aliases, allow_disable, capabilities
            )

            def wrapper(**kwargs) -> None:
                trace_id = _generate_trace_id()
                start = time.perf_counter()
                meta_entry = _TOOL_REGISTRY[name]
                canonical_name = meta_entry["canonical"]

                exec_ctx = ToolExecutionContext(
                    name=name,
                    trace_id=trace_id,
                    meta_entry=meta_entry,
                    func=func,
                    kwargs=kwargs,
                )
                result = _execute_tool_with_error_handling(exec_ctx)

                elapsed_ms = (time.perf_counter() - start) * 1000.0
                _record_invocation(name, elapsed_ms, result.ok, result.error)

                exec_info = ToolExecutionInfo(
                    reg_name=name,
                    canonical_name=canonical_name,
                    elapsed_ms=elapsed_ms,
                    category=category,
                    capabilities=capabilities,
                    meta_entry=meta_entry,
                    trace_id=trace_id,
                )
                _enrich_result_metadata(result, exec_info)
                return result

            _TOOL_REGISTRY[name]["handler"] = wrapper
            for alias in aliases:
                _TOOL_REGISTRY[alias]["handler"] = wrapper
        return wrapper

    return decorator


def get_tools_schema(include_disabled: bool = False) -> list[dict[str, object]]:
    schema: list[dict[str, object]] = []
    for meta in _TOOL_REGISTRY.values():
        if meta.get("is_alias"):
            continue
        if meta.get("disabled") and not include_disabled:
            continue
        schema.append(
            {
                "name": meta["name"],
                "description": meta["description"],
                "parameters": meta["parameters"],
                "category": meta.get("category"),
                "aliases": meta.get("aliases", []),
                "disabled": meta.get("disabled", False),
                "capabilities": _CAPABILITIES.get(meta["name"], []),
                "version": __version__,
            }
        )
    return schema
