import re

with open("microservices/orchestrator_service/src/services/overmind/graph/main.py", "r") as f:
    content = f.read()

new_check = '''def check_results(state: AgentState) -> str:
    docs = state.get("reranked_docs", [])
    if len(docs) > 0:
        return "found"
    intent = state.get("intent", "")
    if intent == "educational":
        return "web_fallback"
    return "general_knowledge"'''

old_pattern = r"def check_results\(state: AgentState\) -> str:\n\s*docs = state\.get\([^\n]+\n\s*return[^\n]+"
content = re.sub(old_pattern, new_check, content)

old_edges_pattern = r"graph\.add_conditional_edges\(\n*\s*\"reranker\",\s*check_results,\s*\{\"found\":\s*\"synthesizer\",\s*\"not_found\":\s*\"web_fallback\"\}\n*\s*\)"

new_edges = '''graph.add_conditional_edges(
        "reranker", check_results,
        {
            "found":             "synthesizer",
            "web_fallback":      "web_fallback",
            "general_knowledge": "general_knowledge",
        }
    )'''

content = re.sub(old_edges_pattern, new_edges, content)

with open("microservices/orchestrator_service/src/services/overmind/graph/main.py", "w") as f:
    f.write(content)
