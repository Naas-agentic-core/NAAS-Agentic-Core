with open("microservices/orchestrator_service/src/services/overmind/graph/general_knowledge.py", "r") as f:
    content = f.read()

content = content.replace("from .state import AgentState", "from .main import AgentState")

with open("microservices/orchestrator_service/src/services/overmind/graph/general_knowledge.py", "w") as f:
    f.write(content)
