import asyncio
from langchain_core.messages import HumanMessage
from microservices.orchestrator_service.src.services.overmind.graph.main import ChatFallbackNode, AgentState

async def main():
    node = ChatFallbackNode()
    state = AgentState(
        messages=[
            HumanMessage(content="أين تقع المجر ؟"),
            HumanMessage(content="أين تقع الجزائر ؟"),
            HumanMessage(content="أين تقع الجزائر"),
            HumanMessage(content="أين تقع الجزائر"),
            HumanMessage(content="أين تقع الجزائر"),
        ],
        query="أين تقع الجزائر",
        intent="chat",
        filters={},
        retrieved_docs=[],
        reranked_docs=[],
        used_web=False,
        final_response={},
        tools_executed=False,
    )
    result = await node(state)
    print("Result:", result)

if __name__ == "__main__":
    asyncio.run(main())
