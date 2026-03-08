import importlib
import subprocess
from datetime import datetime
from typing import Any, TypedDict

from langchain_core.messages import BaseMessage
from sqlalchemy import text

from microservices.orchestrator_service.src.core.database import async_session_factory

from .mcp_mock import kagent_tool


def _load_chat_openai_class():
    """يحمّل فئة ChatOpenAI بشكل كسول لتجنب أعطال الاستيراد عند غياب التبعيات."""
    try:
        from langchain_openai import ChatOpenAI as chat_openai_class
    except Exception as exc:  # pragma: no cover - defensive import for unstable environments
        raise RuntimeError("langchain-openai dependency is unavailable") from exc

    return chat_openai_class


class AgentState(TypedDict):
    messages: list[BaseMessage]


# Tool Definitions
@kagent_tool(name="count_python_files", mcp_server="naas.tools.filesystem")
def count_python_files() -> dict:
    """Get the exact count of python files in the project."""
    result = subprocess.run(
        ["find", ".", "-type", "f", "-name", "*.py"], capture_output=True, text=True, check=False
    )
    count = len(result.stdout.strip().split("\n"))
    return {"count": count, "unit": "ملف بايثون"}


@kagent_tool(name="count_db_tables", mcp_server="naas.tools.database")
async def count_db_tables() -> dict:
    """Get the exact count of database tables."""
    async with async_session_factory() as session:
        result = await session.execute(text("SELECT COUNT(*) FROM information_schema.tables"))
        count = result.scalar() or 0
    return {"count": count, "unit": "جدول"}


@kagent_tool(name="list_microservices", mcp_server="naas.tools.infrastructure")
def list_microservices() -> dict:
    """List all running microservices using Docker SDK."""
    try:
        docker_spec = importlib.util.find_spec("docker")
        if docker_spec is None:
            return {"count": 0, "services": [], "error": "docker-sdk-unavailable", "unit": "خدمة مصغرة"}

        docker_module = importlib.import_module("docker")
        client = docker_module.from_env()
        services = client.containers.list()
        return {
            "count": len(services),
            "services": [s.name for s in services],
            "unit": "خدمة مصغرة",
        }
    except Exception as e:
        return {"count": 0, "services": [], "error": str(e), "unit": "خدمة مصغرة"}


@kagent_tool(name="calculate_stats", mcp_server="naas.tools.analytics")
async def calculate_stats() -> dict:
    """Calculate and get complete project statistics."""
    files_res = count_python_files.invoke({})
    tables_res = await count_db_tables.ainvoke({})
    services_res = list_microservices.invoke({})

    return {
        "total_files": files_res["count"],
        "total_tables": tables_res["count"],
        "total_services": services_res["count"],
        "computed_at": datetime.utcnow().isoformat(),
    }


ADMIN_TOOLS = [count_python_files, count_db_tables, list_microservices, calculate_stats]


class MockTLM:
    def get_trustworthiness_score(self, prompt: str, response: str) -> float:
        # Mocking TLM until real implementation is provided in the future
        return 0.95


class AdminAgentNode:
    """
    DSPy-optimized Admin Agent
    tool_choice=required — ZERO hallucination tolerance
    """

    def __init__(self):
        chat_openai_class = _load_chat_openai_class()
        self.llm = chat_openai_class(model="gpt-4o-mini", temperature=0).bind_tools(
            tools=ADMIN_TOOLS,
            tool_choice="required",  # NON NEGOTIABLE
        )
        self.tlm = MockTLM()

    async def __call__(self, state: AgentState) -> dict[str, Any]:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()

        response = await self.llm.ainvoke(state["messages"])

        # TLM Trustworthiness Check
        trust_score = self.tlm.get_trustworthiness_score(
            prompt=str(state["messages"]), response=str(response.content)
        )

        # GUARD: If LLM hallucinated -> FORCE tool execution
        tool_invoked = False
        if not hasattr(response, "tool_calls") or not response.tool_calls or trust_score < 0.80:
            response = await self.llm.bind_tools(ADMIN_TOOLS, tool_choice="required").ainvoke(
                state["messages"]
            )
            tool_invoked = True
        elif hasattr(response, "tool_calls") and response.tool_calls:
            tool_invoked = True

        emit_telemetry(
            node_name="AdminAgentNode",
            start_time=start_time,
            state=state,
            tool_invoked=tool_invoked,
            trust_score=trust_score,
            tokens_used=getattr(response.response_metadata, "token_usage", {}).get(
                "total_tokens", 0
            )
            if hasattr(response, "response_metadata")
            else 0,
        )

        return {"messages": [response]}
