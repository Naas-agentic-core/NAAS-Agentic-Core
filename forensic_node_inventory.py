import re
import os

def run_inventory():
    main_py = "microservices/orchestrator_service/src/services/overmind/graph/main.py"
    search_py = "microservices/orchestrator_service/src/services/overmind/graph/search.py"

    with open(search_py, "r", encoding="utf-8") as f:
        content = f.read()

    print("=== SEARCH.PY NODES ===")
    nodes = re.findall(r"class (\w+Node.*):(.*?)class ", content, re.DOTALL)
    for name, body in nodes:
        print(f"[NODE] Name: {name}")
        reads = re.findall(r'state\.get\("([^"]+)"', body)
        print(f"[NODE] Reads from state: {set(reads)}")
        writes = re.findall(r'return \{"([^"]+)":', body)
        print(f"[NODE] Writes to state: {set(writes)}")
        print("---")

run_inventory()
