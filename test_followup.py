import asyncio
import uuid
import logging

# We need to disable or bypass the checkpointer for a clean, simple memory-only test.
# Using checkpointer=False or similar, but the create_unified_graph tries to get it from DB.
# Instead of DB checkpointer, let's mock the checkpointer or ensure it runs in-memory.
# Actually create_unified_graph uses a Postgres checkpointer if available.
# We will just pass the messages array explicitly to simulate history propagation.
# The graph doesn't need a checkpointer if we inject history explicitly, as per `checkpointer_available` memory notes.

from microservices.orchestrator_service.src.services.overmind.graph.main import create_unified_graph
from langchain_core.messages import HumanMessage, AIMessage

logging.basicConfig(level=logging.ERROR)

async def test_followup():
    graph = create_unified_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    print("=== TURN 1 ===")
    state1 = {
        "query": "أين تقع فرنسا؟",
        "messages": [HumanMessage(content="أين تقع فرنسا؟")]
    }

    # We invoke graph directly
    response1 = await graph.ainvoke(state1, config=config)

    # Assuming response contains final_response and messages
    messages = response1.get("messages", [])
    print(f"\nResponse 1: {response1.get('final_response', '')}\n")

    print("=== TURN 2 ===")
    # Simulate the second turn.
    # The client adds the new user query to the history.
    messages.append(HumanMessage(content="ما هي عاصمتها؟"))

    state2 = {
        "query": "ما هي عاصمتها؟",
        "messages": messages
    }

    response2 = await graph.ainvoke(state2, config=config)
    print(f"\nResponse 2: {response2.get('final_response', '')}\n")

if __name__ == "__main__":
    asyncio.run(test_followup())
