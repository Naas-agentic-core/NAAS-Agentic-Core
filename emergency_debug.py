import asyncio
import logging
import traceback

from langchain_core.messages import HumanMessage
from langgraph.checkpoint.memory import MemorySaver

from microservices.orchestrator_service.src.services.overmind.graph.main import create_unified_graph

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


async def main():
    try:
        # 1. Initialize the Checkpointer
        checkpointer = MemorySaver()

        # 2. Create the Graph
        graph = create_unified_graph(checkpointer=checkpointer)

        # Setup config with thread_id
        config = {"configurable": {"thread_id": "test-session-123"}}

        logger.info("\n--- TURN 1 ---")
        query1 = "أين تقع الجزائر؟"
        logger.info("Input: %s", query1)

        state1 = {"messages": [HumanMessage(content=query1)], "query": query1}
        output1 = await graph.ainvoke(state1, config=config)

        logger.info("\nOutput 1:")
        logger.info(output1.get("final_response"))
        logger.info("\nState 1 messages:")
        logger.info(output1.get("messages", []))

        logger.info("\n--- TURN 2 ---")
        query2 = "ما هي عاصمتها؟"
        logger.info("Input: %s", query2)

        state2 = {"messages": [HumanMessage(content=query2)], "query": query2}
        output2 = await graph.ainvoke(state2, config=config)

        logger.info("\nOutput 2:")
        logger.info(output2.get("final_response"))
        logger.info("\nState 2 messages:")
        logger.info(output2.get("messages", []))

    except Exception:
        logger.info("\n--- TRACEBACK ---")
        logger.info(traceback.format_exc())


if __name__ == "__main__":
    asyncio.run(main())
