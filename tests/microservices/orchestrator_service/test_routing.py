import pytest

from microservices.orchestrator_service.src.services.overmind.graph.main import (
    ChatFallbackNode,
    SupervisorNode,
)


@pytest.mark.asyncio
async def test_supervisor_routing():
    node = SupervisorNode()

    # 1. Unknown input (needs to go to chat, not blank)
    res = await node({"query": "hello"})
    print("HELLO ROUTE:", res)

    # 2. General conversation
    res = await node({"query": "كيف حالك"})
    print("HOW ARE YOU ROUTE:", res)


@pytest.mark.asyncio
async def test_chat_fallback():
    node = ChatFallbackNode()
    res = await node({"query": "السلام عليكم"})
    print("CHAT FALLBACK OUTPUT:", res)


@pytest.mark.asyncio
async def test_supervisor_search():
    node = SupervisorNode()
    res = await node({"query": "تمرين في الرياضيات سنة 2024"})
    print("MATH ROUTE:", res)

    res = await node({"query": "بحث"})
    print("SEARCH ROUTE:", res)


@pytest.mark.asyncio
async def test_search_analyzer():
    from microservices.orchestrator_service.src.services.overmind.graph.search import (
        QueryAnalyzerNode,
    )

    node = QueryAnalyzerNode()
    res = await node({"query": "تمرين في الرياضيات سنة 2024"})
    print("ANALYZER:", res)


@pytest.mark.asyncio
async def test_analyzer_history():
    from microservices.orchestrator_service.src.services.overmind.graph.search import (
        QueryAnalyzerNode,
    )

    node = QueryAnalyzerNode()
    res = await node(
        {
            "query": "وماذا عن السؤال الثاني؟",
            "messages": [
                {"role": "user", "content": "تمرين في الرياضيات سنة 2024"},
                {"role": "assistant", "content": "السؤال الأول هو..."},
            ],
        }
    )
    print("ANALYZER HISTORY:", res)


@pytest.mark.asyncio
async def test_full_chat_flow():
    from langchain_core.messages import HumanMessage

    from microservices.orchestrator_service.src.services.overmind.graph.main import (
        create_unified_graph,
    )

    graph = create_unified_graph()

    # Send first message
    inputs = {"query": "hello", "messages": [HumanMessage(content="hello")]}
    res = await graph.ainvoke(inputs, config={"configurable": {"thread_id": "1"}})
    print("\nTURN 1:", res.get("final_response"))
    print("\nMESSAGES TURN 1:", res.get("messages", []))

    # Send second message without history (simulating route logic)
    inputs = {"query": "كيف حالك", "messages": [HumanMessage(content="كيف حالك")]}
    res = await graph.ainvoke(inputs, config={"configurable": {"thread_id": "1"}})
    print("\nTURN 2:", res.get("final_response"))
    print("\nMESSAGES TURN 2:", res.get("messages", []))
