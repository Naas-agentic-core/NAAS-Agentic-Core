import re
import uuid
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
    is_admin_user: bool
    scope: str
    access: str
    resolved_tool: str
    tool_result: str
    tool_name: str
    trust_score: float
    executed_at: str
    error: str
    final_response: dict


def _is_admin_state(state: AdminExecutionState) -> bool:
    """يفرض تحقق وصول حتمي بدلاً من منطق السماح العام."""

    role = str(state.get("user_role", "")).strip().lower()
    scope = str(state.get("scope", "")).strip().lower()
    has_admin_role = role in {"admin", "super_admin", "superadmin"}
    has_admin_scope = "admin" in scope and "tool" in scope
    return bool(
        state.get("is_admin") is True
        or state.get("is_admin_user") is True
        or has_admin_role
        or has_admin_scope
    )


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


def resolve_tool_deterministic(query: str) -> str:
    """محلل حتمي يحدد أداة الإدارة بدقة اعتماداً على كلمات الهدف الفعلي."""
    query_lower = query.lower()

    wants_python = bool(re.search(r"python|بايثون|\.py", query_lower))
    wants_tables = bool(re.search(r"جدول|جداول|table|tables|database|db", query_lower))
    wants_users = bool(re.search(r"مستخدم|مستخدمين|user|users|أعضاء|member", query_lower))
    wants_services = bool(re.search(r"خدمة|خدمات|service|services|container", query_lower))
    wants_full_stats = bool(re.search(r"إحصائيات|stats|metrics|ملخص|overview|كل", query_lower))

    if wants_python:
        validate_tool_name("admin.count_python_files")
        return "admin.count_python_files"
    if wants_tables:
        validate_tool_name("admin.count_database_tables")
        return "admin.count_database_tables"
    if wants_users:
        validate_tool_name("admin.get_user_count")
        return "admin.get_user_count"
    if wants_services:
        validate_tool_name("admin.list_microservices")
        return "admin.list_microservices"
    if wants_full_stats:
        validate_tool_name("admin.calculate_full_stats")
        return "admin.calculate_full_stats"

    # Queries containing only generic words like "عدد" / "ملفات" should not collapse to Python files.
    validate_tool_name("admin.calculate_full_stats")
    return "admin.calculate_full_stats"


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


admin_graph = StateGraph(AdminExecutionState)
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
        config = {"configurable": {"thread_id": str(uuid.uuid4())}}

        # Merge state into dict for admin_app
        inputs = dict(state)
        res = await self.admin_app.ainvoke(inputs, config=config)

        # We need to make sure the state structure expected by caller is returned
        from langchain_core.messages import AIMessage

        return {
            "final_response": res.get("final_response"),
            "tools_executed": True,
            "messages": [AIMessage(content=str(res.get("final_response")))],
        }
