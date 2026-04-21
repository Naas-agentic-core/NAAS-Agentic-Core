with open("microservices/orchestrator_service/src/services/overmind/graph/main.py", "r") as f:
    content = f.read()

content = content.replace("intent = \"search\"\n        emit_telemetry(node_name=\"SupervisorNode\", start_time=start_time, state=state)\n        return {\"intent\": intent, \"query\": query}", "intent = \"educational\"\n        emit_telemetry(node_name=\"SupervisorNode\", start_time=start_time, state=state)\n        return {\"intent\": intent, \"query\": query}")

with open("microservices/orchestrator_service/src/services/overmind/graph/main.py", "w") as f:
    f.write(content)
