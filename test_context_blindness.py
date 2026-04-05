import asyncio
from langchain_core.messages import HumanMessage, AIMessage
from microservices.orchestrator_service.src.services.overmind.graph.main import QueryRewriterNode, AgentState, build_conversation_context

async def main():
    node = QueryRewriterNode()
    messages = [
        HumanMessage(content="أين تقع الجزائر"),
        AIMessage(content='{"الإجابة": "تقع الجزائر في شمال أفريقيا"}'),
        HumanMessage(content="ما هي عاصمتها ؟"),
    ]
    state = AgentState(
        messages=messages,
        query="ما هي عاصمتها ؟",
        intent="search",
        filters={},
        retrieved_docs=[],
        reranked_docs=[],
        used_web=False,
        final_response={},
        tools_executed=False,
    )
    print("History:")
    print(repr(build_conversation_context(messages)))
    print("Needs rewrite?", node._needs_rewrite("ما هي عاصمتها ؟", messages))
    result = await node(state)
    print("Result:", result)

if __name__ == "__main__":
    asyncio.run(main())
