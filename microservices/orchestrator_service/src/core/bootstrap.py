from microservices.orchestrator_service.src.core.database import get_checkpointer
from microservices.orchestrator_service.src.core.logging import get_logger
from microservices.orchestrator_service.src.services.tools.registry import (
    get_registry,
    register_tool,
)

logger = get_logger("bootstrap")


class AgentBootstrap:
    """
    Universal bootstrap contract.
    Every agent in NAAS must follow this.
    No exceptions. Ever.
    """

    # THE SACRED ORDER — violating this = the bug you just fixed
    import typing

    BOOT_ORDER: typing.ClassVar[list[str]] = [
        "1. register_tools()",  # tools exist
        "2. validate_registry()",  # tools verified
        "3. compile_graph()",  # graph built with tools
        "4. warmup_invoke()",  # graph proven working
        "5. accept_traffic()",  # only now open to requests
    ]

    @classmethod
    async def boot(cls, agent_name: str, tools: list, graph):
        # Step 1
        for tool in tools:
            register_tool(tool.name, tool)

        # Step 2
        registry = get_registry()
        for tool in tools:
            assert registry.get(tool.name), (
                f"[{agent_name}] Tool '{tool.name}' registered but not retrievable."
            )

        # Step 3
        compiled = graph.compile(checkpointer=get_checkpointer())

        # Step 4
        probe = await compiled.ainvoke(
            {"query": "warmup", "is_admin_user": True},
            config={"configurable": {"thread_id": f"{agent_name}_warmup"}},
        )
        assert probe is not None, f"[{agent_name}] Warmup returned None"

        logger.info(f"✅ {agent_name} booted successfully. Warmup result: {str(probe)[:100]}")
        return compiled
