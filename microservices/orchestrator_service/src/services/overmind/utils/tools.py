"""
Tool Registry Adapter.
Wraps the microservice's tool registry to provide the interface expected by Monolith agents.
"""

from collections.abc import Callable
from typing import Any

from microservices.orchestrator_service.src.core.logging import get_logger
from microservices.orchestrator_service.src.services.tools.registry import get_registry

logger = get_logger("tool-registry-adapter")


class ToolRegistry:
    """
    Adapter for Tool Registry.
    Provides .execute() method.
    """

    async def execute(self, tool_name: str, params: dict[str, object]) -> object:
        """Execute a tool by name."""
        registry = get_registry()
        func: Callable | None = registry.get(tool_name)

        if not func:
            logger.warning(f"Tool not found: {tool_name}")
            return None

        try:
            logger.info(f"Executing tool: {tool_name} with params: {params}")
            # Ensure params are passed correctly (kwargs unpacking)
            if params:
                return await func(**params)
            return await func()
        except Exception as e:
            logger.error(f"Tool execution failed: {tool_name}: {e}", exc_info=True)
            return None


# Singleton instance
tool_registry = ToolRegistry()
