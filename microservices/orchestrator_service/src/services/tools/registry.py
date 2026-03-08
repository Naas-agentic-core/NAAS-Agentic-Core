"""
Tool Registry.
"""

from collections.abc import Callable

from microservices.orchestrator_service.src.core.logging import get_logger

logger = get_logger("tool-registry")

# Global registry of tool functions
_TOOL_REGISTRY: dict[str, Callable] = {}


def get_registry() -> dict[str, Callable]:
    """Returns the tool registry."""
    return _TOOL_REGISTRY


def register_tool(name: str, func: Callable) -> None:
    """Registers a tool."""
    _TOOL_REGISTRY[name] = func
    logger.info(f"Registered tool: {name}")


class CriticalStartupError(Exception):
    pass


def startup_registry_check(registry: dict[str, Callable]) -> None:
    """
    Service REFUSES to start if admin tools missing.
    No silent failures. Ever.
    """
    from microservices.orchestrator_service.src.contracts.admin_tools import ADMIN_TOOL_CONTRACT

    REQUIRED_ADMIN_TOOLS = list(ADMIN_TOOL_CONTRACT.keys())
    registered = list(registry.keys())
    missing = [t for t in REQUIRED_ADMIN_TOOLS if t not in registered]

    if missing:
        raise CriticalStartupError(
            f"REGISTRY STARVATION DETECTED.\n"
            f"Missing admin tools: {missing}\n"
            f"Service cannot start. Fix registry first."
        )

    logger.info(
        "✅ Admin tool registry healthy",
        extra={
            "registered_tools": registered,
            "required_tools": REQUIRED_ADMIN_TOOLS,
            "status": "ALL_PRESENT"
        }
    )


def register_all_tools() -> None:
    """
    Register all available tools into the global registry.
    This function should be called during application startup (lifespan).
    """
    try:
        # Import here to avoid circular dependencies
        from microservices.orchestrator_service.src.services.tools.content import (
            register_content_tools,
        )
        from microservices.orchestrator_service.src.services.tools.retrieval.service import (
            search_educational_content,
        )
        from microservices.orchestrator_service.src.contracts.admin_tools import ADMIN_TOOLS

        registry = get_registry()

        # 1. Register Content Tools (Search, Curriculum, etc.)
        register_content_tools(registry)

        # 2. Register Retrieval Tools (Legacy/Educational)
        registry["search_educational_content"] = search_educational_content

        # 3. Register Admin Metrics Tools (NEW)
        for tool in ADMIN_TOOLS:
            registry[tool.name] = tool

        # Validate after registration
        startup_registry_check(registry)

        logger.info(
            f"All tools registered successfully. Total tools: {len(registry)}. "
            f"Tools: {list(registry.keys())}"
        )

    except CriticalStartupError:
        raise
    except Exception as e:
        logger.error(f"Failed to register tools: {e}", exc_info=True)
        # We don't raise here to allow startup to continue, but agents will be lobotomized.
