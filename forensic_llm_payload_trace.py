import re

def run():
    search_py = "microservices/orchestrator_service/src/services/overmind/graph/search.py"
    with open(search_py, "r", encoding="utf-8") as f:
        content = f.read()

    print("[LLM_CALL] ═══ LLM INVOCATION TRACE ═══")

    # We look for self.analyzer
    analyzer_call = re.search(r"self\.analyzer\((.*?)\)", content)
    if analyzer_call:
        print(f"[LLM_CALL] Location: {search_py}")
        print(f"[LLM_CALL] Node: QueryAnalyzerNode")
        print(f"[LLM_CALL] ")
        print(f"[LLM_CALL] WHAT IS SENT TO THE LLM: {analyzer_call.group(1)}")

        if "raw_query" in analyzer_call.group(1):
            if "context_query" in analyzer_call.group(1):
                print(f"[LLM_CALL]   Argument source: context_query")
                print(f"[LLM_CALL]   Contains history: YES (context_query)")
            else:
                print(f"[LLM_CALL]   Argument source: query")
                print(f"[LLM_CALL]   Contains history: NO")
                print(f"🚨🚨🚨 [LLM_CALL] STATELESS INVOCATION")

    else:
        print("No self.analyzer call found.")

    print("[LLM_CALL] ═══ END ═══")

run()
