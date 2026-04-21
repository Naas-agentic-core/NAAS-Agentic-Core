with open("microservices/orchestrator_service/src/services/overmind/graph/main.py", "r") as f:
    content = f.read()

# 1. Import GeneralKnowledgeNode
import_stmt = "from .admin import AdminAgentNode"
new_import_stmt = "from .admin import AdminAgentNode\n    from .general_knowledge import GeneralKnowledgeNode"
content = content.replace(import_stmt, new_import_stmt)

# 2. Update route_intent to include general_knowledge and rename search to educational
old_route = """def route_intent(state: AgentState) -> str:
    import logging

    logger = logging.getLogger("graph")
    intent = state.get("intent", "search")
    node = {
        "search": "query_rewriter",
        "admin": "admin_agent",
        "tool": "tool_executor",
        "chat": "chat_fallback",
    }.get(intent, "query_rewriter")
    logger.info(f"SUPERVISOR_NODE → routing to → {node}")
    return intent"""

new_route = """def route_intent(state: AgentState) -> str:
    import logging

    logger = logging.getLogger("graph")
    intent = state.get("intent", "educational")

    if intent == "search":
        intent = "educational"

    node = {
        "educational": "query_rewriter",
        "admin": "admin_agent",
        "tool": "tool_executor",
        "chat": "chat_fallback",
        "general_knowledge": "general_knowledge",
    }.get(intent, "query_rewriter")
    logger.info(f"SUPERVISOR_NODE → routing to → {node}")
    return intent"""
content = content.replace(old_route, new_route)

# 3. Add node and edges
old_graph_nodes = """    graph.add_node("chat_fallback", ChatFallbackNode())
    graph.add_node("synthesizer", synthesizer_node())
    graph.add_node("validator", ValidatorNode())

    graph.add_conditional_edges(
        "supervisor",
        route_intent,
        {
            "search": "query_rewriter",
            "admin": "admin_agent",
            "tool": "tool_executor",
            "chat": "chat_fallback",
        },
    )"""

new_graph_nodes = """    graph.add_node("chat_fallback", ChatFallbackNode())
    graph.add_node("general_knowledge", GeneralKnowledgeNode())
    graph.add_node("synthesizer", synthesizer_node())
    graph.add_node("validator", ValidatorNode())

    graph.add_conditional_edges(
        "supervisor",
        route_intent,
        {
            "educational": "query_rewriter",
            "admin": "admin_agent",
            "tool": "tool_executor",
            "chat": "chat_fallback",
            "general_knowledge": "general_knowledge",
        },
    )"""
content = content.replace(old_graph_nodes, new_graph_nodes)

old_graph_edges = """    graph.add_edge("tool_executor", "validator")  # tool_executor -> validator directly, bypassing synthesizer to not break admin outputs
    graph.add_edge("chat_fallback", "validator")
    graph.add_edge("synthesizer", "validator")"""

new_graph_edges = """    graph.add_edge("tool_executor", "validator")  # tool_executor -> validator directly, bypassing synthesizer to not break admin outputs
    graph.add_edge("chat_fallback", "validator")
    graph.add_edge("general_knowledge", END)
    graph.add_edge("synthesizer", "validator")"""

content = content.replace(old_graph_edges, new_graph_edges)

with open("microservices/orchestrator_service/src/services/overmind/graph/main.py", "w") as f:
    f.write(content)
