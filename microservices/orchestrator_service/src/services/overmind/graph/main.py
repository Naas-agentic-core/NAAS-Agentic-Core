import asyncio
from operator import add
from typing import Annotated, Any, TypedDict

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from .admin import ADMIN_TOOLS, AdminAgentNode


def _load_search_nodes() -> tuple[type, type, type, type, type]:
    """يحمّل عقد البحث عند توفر التبعيات ويعيد بدائل آمنة عند غيابها."""
    try:
        from .search import (
            InternalRetrieverNode,
            QueryAnalyzerNode,
            RerankerNode,
            SynthesizerNode,
            WebSearchFallbackNode,
        )

        return (
            QueryAnalyzerNode,
            InternalRetrieverNode,
            RerankerNode,
            WebSearchFallbackNode,
            SynthesizerNode,
        )
    except Exception:
        class _PassthroughNode:
            def __call__(self, state: dict) -> dict:
                return state

        return (
            _PassthroughNode,
            _PassthroughNode,
            _PassthroughNode,
            _PassthroughNode,
            _PassthroughNode,
        )




class AgentState(TypedDict):
    messages: Annotated[list[Any], add]
    query: str
    intent: str
    filters: Any
    retrieved_docs: list[Any]
    reranked_docs: list[Any]
    used_web: bool
    final_response: Any
    tools_executed: bool


class SupervisorNode:
    def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        query = state.get("query", "").lower()
        if any(w in query for w in ["كم", "إحصائيات", "ملف", "ملفات"]):
            intent = "admin"
        else:
            intent = "search"
        emit_telemetry(node_name="SupervisorNode", start_time=start_time, state=state)
        return {"intent": intent}


class ToolExecutorNode:
    async def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        messages = state.get("messages", [])
        if not messages:
            emit_telemetry(node_name="ToolExecutorNode", start_time=start_time, state=state)
            return {"tools_executed": False}

        last_msg = messages[-1]
        results = []
        if hasattr(last_msg, "tool_calls") and last_msg.tool_calls:
            for tc in last_msg.tool_calls:
                for t in ADMIN_TOOLS:
                    if t.name == tc["name"]:
                        try:
                            if asyncio.iscoroutinefunction(t.invoke):
                                res = await t.ainvoke(tc["args"])
                            else:
                                res = t.invoke(tc["args"])
                            results.append(str(res))
                        except Exception as e:
                            results.append(f"Error: {e!s}")
                            emit_telemetry(
                                node_name="ToolExecutorNode",
                                start_time=start_time,
                                state=state,
                                error=e,
                            )

        emit_telemetry(
            node_name="ToolExecutorNode", start_time=start_time, state=state, tool_invoked=True
        )
        return {"final_response": "\n".join(results), "tools_executed": True}


class ValidatorNode:
    def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        emit_telemetry(node_name="ValidatorNode", start_time=start_time, state=state)
        return {}


def route_intent(state: AgentState) -> str:
    return state.get("intent", "search")


def check_results(state: AgentState) -> str:
    docs = state.get("reranked_docs", [])
    return "found" if len(docs) > 0 else "not_found"


def check_quality(state: AgentState) -> str:
    return "pass"


def create_unified_graph():
    graph = StateGraph(AgentState)

    (
        query_analyzer_node,
        internal_retriever_node,
        reranker_node,
        web_search_fallback_node,
        synthesizer_node,
    ) = _load_search_nodes()

    graph.add_node("supervisor", SupervisorNode())
    graph.add_node("query_analyzer", query_analyzer_node())
    graph.add_node("retriever", internal_retriever_node())
    graph.add_node("reranker", reranker_node())
    graph.add_node("web_fallback", web_search_fallback_node())
    graph.add_node("admin_agent", AdminAgentNode())
    graph.add_node("tool_executor", ToolExecutorNode())
    graph.add_node("synthesizer", synthesizer_node())
    graph.add_node("validator", ValidatorNode())

    graph.add_conditional_edges(
        "supervisor",
        route_intent,
        {"search": "query_analyzer", "admin": "admin_agent", "tool": "tool_executor"},
    )

    graph.add_edge("query_analyzer", "retriever")
    graph.add_edge("retriever", "reranker")
    graph.add_conditional_edges(
        "reranker", check_results, {"found": "synthesizer", "not_found": "web_fallback"}
    )

    graph.add_edge("web_fallback", "synthesizer")
    graph.add_edge("admin_agent", "tool_executor")
    graph.add_edge(
        "tool_executor", "validator"
    )  # tool_executor -> validator directly, bypassing synthesizer to not break admin outputs
    graph.add_edge("synthesizer", "validator")

    graph.add_conditional_edges("validator", check_quality, {"pass": END, "fail": "supervisor"})

    graph.set_entry_point("supervisor")
    memory = MemorySaver()
    return graph.compile(checkpointer=memory)
