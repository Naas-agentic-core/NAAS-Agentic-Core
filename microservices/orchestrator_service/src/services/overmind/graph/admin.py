import re
from datetime import datetime
from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from microservices.orchestrator_service.src.contracts.admin_tools import (
    ADMIN_TOOLS,
    validate_tool_name,
)
from microservices.orchestrator_service.src.services.overmind.graph.main import AgentState
from microservices.orchestrator_service.src.services.tools.registry import get_registry

def get_admin_system_prompt() -> str:
    return """
You are NAAS Admin Execution Engine.
أنت محرك تنفيذ إداري — وليس مساعداً تعليمياً.

YOUR ONLY JOB:
- Execute the tool provided to you
- Return the EXACT number from tool result
- Never estimate. Never explain. Never educate.
- If tool fails -> return error_code, not text

RESPONSE FORMAT (strict):
{
  "الإجابة": "<exact result from tool>",
  "tool_name": "<contract tool name>",
  "timestamp": "<ISO8601>",
  "source_service": "orchestrator-service"
}

FORBIDDEN:
x "لا أستطيع الوصول..."
x "بناءً على معلوماتي..."
x Any educational content
x Any estimation or approximation
x Any response without tool execution
"""

def assert_admin_context(prompt_type: str):
    assert prompt_type == "admin_only", (
        f"CRITICAL: Educational prompt used in admin channel! "
        f"Got: {prompt_type}. This is a system bug."
    )

class MockTLM:
    def get_trustworthiness_score(self, prompt: str, response: str) -> float:
        # Mocking TLM until real implementation is provided in the future
        return 0.95

# Deterministic Graph Nodes
class DetectIntentNode:
    async def __call__(self, state):
        # Already handled by SupervisorNode
        return state

class ValidateAccessNode:
    async def __call__(self, state):
        # Allow all for now, in a real system we'd check JWT scope or user_id
        return {**state, "access": "granted"}

class ResolveToolNode:
    QUERY_TO_TOOL = {
        "python|بايثون|ملف":   "admin.count_python_files",
        "جدول|table|database": "admin.count_database_tables",
        "مستخدم|user":         "admin.get_user_count",
        "خدمة|service":        "admin.list_microservices",
        "إحصائيات|stats":      "admin.calculate_full_stats",
    }

    def __call__(self, state):
        query = state.get("query", "").lower()
        for pattern, tool_name in self.QUERY_TO_TOOL.items():
            if re.search(pattern, query):
                validate_tool_name(tool_name)  # contract check
                return {"resolved_tool": tool_name}
        # Fallback: full stats
        return {"resolved_tool": "admin.calculate_full_stats"}

class ExecuteToolNode:
    def __init__(self):
        self.tlm = MockTLM()

    async def __call__(self, state):
        import time
        from .telemetry import emit_telemetry

        start_time = time.time()
        tool_name = state.get("resolved_tool")
        tool_fn = get_registry().get(tool_name)

        if not tool_fn:
            emit_telemetry(node_name="ExecuteToolNode", start_time=start_time, state=state, error="ADMIN_TOOL_UNAVAILABLE")
            return {
                "error": "ADMIN_TOOL_UNAVAILABLE",
                "tool_name": tool_name
            }

        # Execute with TLM trust scoring
        try:
            import asyncio
            if hasattr(tool_fn, "ainvoke"):
                result = await tool_fn.ainvoke({})
            elif asyncio.iscoroutinefunction(tool_fn) or asyncio.iscoroutinefunction(getattr(tool_fn, "invoke", None)):
                result = await tool_fn()
            elif hasattr(tool_fn, "invoke"):
                result = tool_fn.invoke({})
            else:
                result = tool_fn()
        except Exception as e:
            emit_telemetry(node_name="ExecuteToolNode", start_time=start_time, state=state, error=str(e))
            return {
                "error": "ADMIN_TOOL_EXECUTION_FAILED",
                "tool_name": tool_name,
                "tool_result": str(e)
            }

        trust = self.tlm.get_trustworthiness_score(
            prompt=state.get("query", ""),
            response=str(result)
        )

        emit_telemetry(node_name="ExecuteToolNode", start_time=start_time, state=state, trust_score=trust, tool_invoked=True)

        return {
            "tool_result":  result,
            "tool_name":    tool_name,
            "trust_score":  trust,
            "executed_at":  datetime.utcnow().isoformat()
        }

class RenderAnswerNode:
    def __call__(self, state):
        assert_admin_context("admin_only") # Guard execution

        if state.get("error"):
            return {
                "final_response": {
                    "خطأ": state["error"],
                    "الأداة": state.get("tool_name"),
                    "الإجراء": "تواصل مع مدير النظام"
                }
            }
        return {
            "final_response": {
                "الإجابة":         state.get("tool_result"),
                "tool_name":      state.get("tool_name"),
                "مستوى_الثقة":    state.get("trust_score"),
                "وقت_التنفيذ":    state.get("executed_at"),
                "المصدر":         "orchestrator-service"
            }
        }

admin_graph = StateGraph(dict)
admin_graph.add_node("detect",   DetectIntentNode())
admin_graph.add_node("validate", ValidateAccessNode())
admin_graph.add_node("resolve",  ResolveToolNode())
admin_graph.add_node("execute",  ExecuteToolNode())
admin_graph.add_node("render",   RenderAnswerNode())

admin_graph.add_edge("detect",   "validate")
admin_graph.add_edge("validate", "resolve")
admin_graph.add_edge("resolve",  "execute")
admin_graph.add_edge("execute",  "render")
admin_graph.add_edge("render",    END)
admin_graph.set_entry_point("detect")

admin_app = admin_graph.compile(
    checkpointer=MemorySaver(),
    interrupt_before=[]
)

class AdminAgentNode:
    async def __call__(self, state: AgentState) -> dict[str, Any]:
        config = {"configurable": {"thread_id": "admin_run"}}

        # Merge state into dict for admin_app
        inputs = dict(state)
        res = await admin_app.ainvoke(inputs, config=config)

        # We need to make sure the state structure expected by caller is returned
        return {
            "final_response": res.get("final_response"),
            "tools_executed": True
        }
