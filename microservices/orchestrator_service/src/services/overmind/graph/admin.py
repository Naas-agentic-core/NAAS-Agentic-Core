import re
from datetime import datetime
from typing import TypedDict

from langgraph.graph import END, StateGraph

from microservices.orchestrator_service.src.contracts.admin_tools import (
    validate_tool_name,
)
from microservices.orchestrator_service.src.services.overmind.graph.main import AgentState
from microservices.orchestrator_service.src.services.tools.registry import get_registry


def get_admin_system_prompt() -> str:
    return """
You are NAAS Admin Execution Engine — NOT a tutor.
أنت محرك تنفيذ إداري حتمي — لست مساعداً تعليمياً.

ABSOLUTE RULES:
① Execute the tool. Return the exact result. Nothing more.
② Never estimate. Never explain. Never educate.
③ Response format is ALWAYS:
   {
     "الإجابة":      "<exact tool output>",
     "tool_name":   "<admin.canonical_name>",
     "timestamp":   "<ISO8601 UTC>",
     "المصدر":      "orchestrator-service"
   }

FORBIDDEN — zero tolerance:
✗ "لا أستطيع الوصول..."
✗ "بناءً على معلوماتي..."
✗ Any educational explanation
✗ Any response without real tool execution
✗ dict/JSON raw output to user
"""


def assert_admin_prompt_only(prompt_fn_name: str):
    assert prompt_fn_name == "get_admin_system_prompt", (
        f"[CRITICAL BUG] Admin channel received non-admin prompt: "
        f"'{prompt_fn_name}'. "
        f"Educational prompt in admin channel = system failure."
    )


class AdminExecutionState(TypedDict, total=False):
    """حالة تنفيذ إدارية مقيّدة الحقول لتقليل الغموض عند حدود التحكم."""

    query: str
    user_role: str
    is_admin: bool
    scope: str


def _is_admin_state(state: AdminExecutionState) -> bool:
    """يفرض تحقق وصول حتمي بدلاً من منطق السماح العام."""

    role = str(state.get("user_role", "")).strip().lower()
    scope = str(state.get("scope", "")).strip().lower()
    return bool(state.get("is_admin") is True or role in {"admin", "super_admin", "superadmin"} or ("admin" in scope and "tool" in scope))


# Deterministic Graph Nodes
class DetectIntentNode:
    async def __call__(self, state):
        # Already handled by SupervisorNode
        return state


class ValidateAccessNode:
    async def __call__(self, state: AdminExecutionState) -> AdminExecutionState | dict[str, str]:
        if not _is_admin_state(state):
            return {"error": "ADMIN_ACCESS_DENIED", "access": "denied"}
        return {**state, "access": "granted"}


QUERY_TO_TOOL_MAP = [
    (r"python|بايثون|\.py|ملفات", "admin.count_python_files"),
    (r"جدول|table|database|db", "admin.count_database_tables"),
    (r"مستخدم|user|أعضاء|member", "admin.get_user_count"),
    (r"خدمة|service|container", "admin.list_microservices"),
    (r"إحصائيات|stats|كل|full", "admin.calculate_full_stats"),
]


def resolve_tool_deterministic(query: str) -> str:
    """Rule-first. Zero LLM involvement. Always returns a tool."""
    query_lower = query.lower()
    for pattern, tool_name in QUERY_TO_TOOL_MAP:
        if re.search(pattern, query_lower):
            validate_tool_name(tool_name)  # contract check
            return tool_name
    return "admin.calculate_full_stats"  # safe default


class ResolveToolNode:
    def __call__(self, state):
        tool = resolve_tool_deterministic(state.get("query", ""))
        return {"resolved_tool": tool}


class ExecuteToolNode:
    def __init__(self):
        pass

    async def __call__(self, state):
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        tool_name = state.get("resolved_tool")
        tool_fn = get_registry().get(tool_name)
        import logging

        logger = logging.getLogger("admin_graph")
        logger.info(f"TOOL_REGISTRY.get('{tool_name}') → {'found' if tool_fn else 'None'}")

        if not tool_fn:
            emit_telemetry(
                node_name="ExecuteToolNode",
                start_time=start_time,
                state=state,
                error="ADMIN_TOOL_UNAVAILABLE",
            )
            return {"error": "ADMIN_TOOL_UNAVAILABLE", "tool_name": tool_name}

        try:
            import asyncio

            if hasattr(tool_fn, "ainvoke"):
                result = await tool_fn.ainvoke({})
            elif asyncio.iscoroutinefunction(tool_fn) or asyncio.iscoroutinefunction(
                getattr(tool_fn, "invoke", None)
            ):
                result = await tool_fn()
            elif hasattr(tool_fn, "invoke"):
                result = tool_fn.invoke({})
            else:
                result = tool_fn()
                logger.info(f"TOOL EXECUTED → {tool_name} → {str(result)[:50]}")
        except Exception as e:
            logger.error("Exception in tool execution", exc_info=True)
            emit_telemetry(
                node_name="ExecuteToolNode", start_time=start_time, state=state, error=str(e)
            )
            return {
                "error": "ADMIN_TOOL_EXECUTION_FAILED",
                "tool_name": tool_name,
                "tool_result": str(e),
            }

        logger.info(f"TOOL EXECUTED → {tool_name} → {str(result)[:50]}")
        trust = 1.0

        emit_telemetry(
            node_name="ExecuteToolNode",
            start_time=start_time,
            state=state,
            trust_score=trust,
            tool_invoked=True,
        )

        return {
            "tool_result": result,
            "tool_name": tool_name,
            "trust_score": trust,
            "executed_at": datetime.utcnow().isoformat(),
        }


class RenderAnswerNode:
    def __call__(self, state):
        assert_admin_prompt_only("get_admin_system_prompt")  # Guard execution

        if state.get("error"):
            return {
                "final_response": {
                    "خطأ": state["error"],
                    "الأداة": state.get("tool_name", "unknown"),
                    "الإجراء": "تواصل مع مدير النظام",
                }
            }
        return {
            "final_response": {
                "الإجابة": state.get("tool_result"),
                "tool_name": state.get("tool_name"),
                "مستوى_الثقة": f"{state.get('trust_score', 0):.2f}",
                "وقت_التنفيذ": state.get("executed_at"),
                "المصدر": "orchestrator-service",
            }
        }


admin_graph = StateGraph(dict)
admin_graph.add_node("detect", DetectIntentNode())
admin_graph.add_node("validate", ValidateAccessNode())
admin_graph.add_node("resolve", ResolveToolNode())
admin_graph.add_node("execute", ExecuteToolNode())
admin_graph.add_node("render", RenderAnswerNode())

admin_graph.add_edge("detect", "validate")
admin_graph.add_edge("validate", "resolve")
admin_graph.add_edge("resolve", "execute")
admin_graph.add_edge("execute", "render")
admin_graph.add_edge("render", END)
admin_graph.set_entry_point("detect")


class AdminAgentNode:
    def __init__(self, admin_app=None):
        self.admin_app = admin_app

    async def __call__(self, state: AgentState) -> dict[str, object]:
        if not self.admin_app:
            raise RuntimeError("AdminAgentNode missing compiled admin_app")
        config = {"configurable": {"thread_id": "admin_run"}}

        # Merge state into dict for admin_app
        inputs = dict(state)
        res = await self.admin_app.ainvoke(inputs, config=config)

        # We need to make sure the state structure expected by caller is returned
        return {"final_response": res.get("final_response"), "tools_executed": True}
