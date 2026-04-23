import asyncio
import uuid
import logging

from microservices.orchestrator_service.src.services.overmind.graph.main import create_unified_graph
from langchain_core.messages import HumanMessage, AIMessage

logging.basicConfig(level=logging.ERROR)

class MockClient:
    async def chat_completion(self, messages, temperature=0.7):
        return "Mock Response"

async def test_followup():
    graph = create_unified_graph()
    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    import microservices.orchestrator_service.src.services.overmind.graph.general_knowledge as gk
    gk.get_ai_client = lambda: MockClient()

    print("=== TURN 1 ===")
    state1 = {
        "query": "أين تقع فرنسا؟",
        "messages": [HumanMessage(content="أين تقع فرنسا؟")]
    }

    # We invoke graph directly
    response1 = await graph.ainvoke(state1, config=config)
    messages = response1.get("messages", [])
    print(f"\nResponse 1: {response1.get('final_response', '')}\n")

    print("=== TURN 2 ===")
    # Simulate the second turn.
    messages.append(HumanMessage(content="ما هي عاصمتها؟"))

    state2 = {
        "query": "ما هي عاصمتها؟",
        "messages": messages
    }

    response2 = await graph.ainvoke(state2, config=config)
    print(f"\nResponse 2: {response2.get('final_response', '')}\n")

if __name__ == "__main__":
    asyncio.run(test_followup())
