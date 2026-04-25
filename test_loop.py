from microservices.orchestrator_service.src.services.overmind.graph.main import (
    ValidatorNode,
    check_quality,
)

node = ValidatorNode()

# Initial failure
state1 = {"final_response": "لم أفهم", "retry_count": 0}
updates = node(state1)
state1.update(updates)
print("After first failure:", state1, check_quality(state1))

# Second failure
updates = node(state1)
state1.update(updates)
print("After second failure:", state1, check_quality(state1))
