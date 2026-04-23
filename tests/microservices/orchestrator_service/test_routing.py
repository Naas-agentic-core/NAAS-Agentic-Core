import pytest
from langchain_core.messages import AIMessage, HumanMessage

from microservices.orchestrator_service.src.services.overmind.graph.general_knowledge import (
    GeneralKnowledgeNode,
)
from microservices.orchestrator_service.src.services.overmind.graph.main import (
    ChatFallbackNode,
    QueryRewriterNode,
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


@pytest.mark.asyncio
async def test_query_rewriter_contextual_fallback_for_pronouns() -> None:
    node = QueryRewriterNode()
    result = await node(
        {
            "query": "ما هي عاصمتها؟",
            "messages": [
                HumanMessage(content="أين تقع الجزائر؟"),
                AIMessage(content="تقع الجزائر في شمال أفريقيا."),
                HumanMessage(content="ما هي عاصمتها؟"),
            ],
        }
    )

    rewritten = str(result.get("query", ""))
    assert "الجزائر" in rewritten
    assert "ما هي عاصمتها" in rewritten


@pytest.mark.asyncio
async def test_query_rewriter_keeps_self_contained_queries() -> None:
    node = QueryRewriterNode()
    result = await node(
        {
            "query": "ما هي عاصمة الجزائر؟",
            "messages": [
                HumanMessage(content="ما هي عاصمة الجزائر؟"),
            ],
        }
    )

    assert result["query"] == "ما هي عاصمة الجزائر؟"


@pytest.mark.asyncio
async def test_general_knowledge_node_uses_resolved_state_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class _FakeAIClient:
        def __init__(self) -> None:
            self.last_messages: list[dict[str, str]] = []

        async def chat_completion(self, messages: list[dict[str, str]], temperature: float = 0.3) -> str:
            self.last_messages = messages
            return "باريس"

    fake_client = _FakeAIClient()
    monkeypatch.setattr(
        "microservices.orchestrator_service.src.services.overmind.graph.general_knowledge.get_ai_client",
        lambda: fake_client,
    )

    node = GeneralKnowledgeNode()
    result = await node(
        {
            "query": "ما هي عاصمة فرنسا؟",
            "messages": [
                HumanMessage(content="أين تقع فرنسا؟"),
                AIMessage(content="تقع فرنسا في أوروبا."),
                HumanMessage(content="ما هي عاصمتها؟"),
            ],
        }
    )

    payload = fake_client.last_messages[-1]["content"]
    assert "Question:\nما هي عاصمة فرنسا؟" in payload
    assert "ما هي عاصمتها؟" not in payload
    assert "User: أين تقع فرنسا؟" in payload
    assert result["final_response"] == "باريس"


@pytest.mark.asyncio
async def test_supervisor_resolves_arabic_pronoun_followup_from_history() -> None:
    node = SupervisorNode()
    result = await node(
        {
            "query": "ما هي عاصمتها؟",
            "messages": [
                HumanMessage(content="أين تقع فرنسا؟"),
                AIMessage(content="تقع فرنسا في غرب أوروبا."),
                HumanMessage(content="ما هي عاصمتها؟"),
            ],
        }
    )

    assert result["query"] == "ما هي عاصمة فرنسا؟"
