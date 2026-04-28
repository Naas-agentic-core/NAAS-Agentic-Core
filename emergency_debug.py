import asyncio
import traceback
from langgraph.checkpoint.memory import MemorySaver
from microservices.orchestrator_service.src.services.overmind.graph.main import create_unified_graph
from langchain_core.messages import HumanMessage

async def main():
    try:
        # 1. Initialize the Checkpointer
        checkpointer = MemorySaver()

        # 2. Create the Graph
        graph = create_unified_graph(checkpointer=checkpointer)

        # Setup config with thread_id
        config = {"configurable": {"thread_id": "test-session-123"}}

        print("\n--- TURN 1 ---")
        query1 = "أين تقع الجزائر؟"
        print(f"Input: {query1}")

        state1 = {"messages": [HumanMessage(content=query1)], "query": query1}
        output1 = await graph.ainvoke(state1, config=config)

        print("\nOutput 1:")
        print(output1.get("final_response"))
        print("\nState 1 messages:")
        print(output1.get("messages", []))

        print("\n--- TURN 2 ---")
        query2 = "ما هي عاصمتها؟"
        print(f"Input: {query2}")

        state2 = {"messages": [HumanMessage(content=query2)], "query": query2}
        output2 = await graph.ainvoke(state2, config=config)

        print("\nOutput 2:")
        print(output2.get("final_response"))
        print("\nState 2 messages:")
        print(output2.get("messages", []))

    except Exception as e:
        print("\n--- TRACEBACK ---")
        print(traceback.format_exc())

if __name__ == "__main__":
    asyncio.run(main())
