import re

def run_autopsy():
    main_py = "microservices/orchestrator_service/src/services/overmind/graph/main.py"

    with open(main_py, "r", encoding="utf-8") as f:
        content = f.read()

    state_def = re.search(r"class AgentState\(TypedDict\):(.*?)(?:class |\n\n\w)", content, re.DOTALL)
    if state_def:
        print("[STATE] ═══ COMPLETE STATE DEFINITION ═══")
        print(f"[STATE] File: {main_py}")
        print(f"[STATE] Type: TypedDict")
        print("[STATE]")
        print("[STATE] Fields:")
        lines = state_def.group(1).strip().split('\n')
        for line in lines:
            print(f"[STATE]   {line.strip()}")
        print("[STATE] ═══ END STATE DEFINITION ═══")

        has_messages = "messages" in state_def.group(1)
        has_add = "add" in state_def.group(1)
        print(f"[STATE] Field 'messages' exists: {'YES' if has_messages else 'NO'}")
        print(f"[STATE] Field 'messages' uses add_messages reducer: {'YES' if has_add else 'NO'}")

    else:
        print("AgentState not found.")

if __name__ == "__main__":
    run_autopsy()
