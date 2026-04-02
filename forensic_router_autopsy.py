import re

def run():
    main_py = "microservices/orchestrator_service/src/services/overmind/graph/main.py"
    with open(main_py, "r", encoding="utf-8") as f:
        content = f.read()

    print("[ROUTER] ══════════════════════════════════════════════")
    print(f"[ROUTER] FILE: {main_py}")
    print(f"[ROUTER] FUNCTION: route_intent")

    route_func = re.search(r"def route_intent\(.*?\):(.*?)def ", content, re.DOTALL)
    if route_func:
        print(route_func.group(0))

    print("[ROUTER] ══════════════════════════════════════════════")

    cond_edges = re.search(r"graph\.add_conditional_edges\((.*?)\)", content, re.DOTALL)
    if cond_edges:
        print("[GRAPH] ═══ COMPLETE EDGE MAP ═══")
        print(cond_edges.group(1))

run()
