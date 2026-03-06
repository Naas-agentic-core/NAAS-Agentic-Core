import pytest

from microservices.orchestrator_service.src.services.overmind.langgraph.context_enricher import ContextEnricher


class DummyPayload:
    def __init__(self, text: str, metadata: dict[str, object]) -> None:
        self.text = text
        self.metadata = metadata


class DummyNode:
    def __init__(self, payload: DummyPayload) -> None:
        self.node = payload
        self.score = 0.0


from microservices.orchestrator_service.src.services.overmind.langgraph.context_contracts import Snippet


class DummyRetriever:
    """Mock retriever matching SnippetRetriever protocol."""

    def __init__(self, snippets: list[Snippet]) -> None:
        self._snippets = snippets

    async def retrieve(
        self,
        query: str,
        *,
        context: dict[str, object],
        metadata: dict[str, object],
        max_snippets: int,
    ) -> list[Snippet]:
        # Return reversed list to simulate 'reranking' logic or just different order
        return list(reversed(self._snippets))[:max_snippets]


@pytest.mark.asyncio
async def test_enrich_applies_reranker(monkeypatch: pytest.MonkeyPatch) -> None:
    # 1. Setup Data
    snippet_a = Snippet(text="النص الأول", metadata={"id": "a"})
    snippet_b = Snippet(text="النص الثاني", metadata={"id": "b"})

    # 2. Inject Mock Retriever
    # Note: Reranking logic is now assumed to be part of the retriever implementation
    # or the retriever we pass in already does it.
    retriever = DummyRetriever([snippet_a, snippet_b])

    # 3. Initialize Enricher with Mock
    enricher = ContextEnricher(max_snippets=2, retriever=retriever)

    # 4. Execute
    result = await enricher.enrich("اختبار التكامل", {})

    # 5. Verify
    # DummyRetriever reverses the list, so B comes before A
    assert result.snippets[0]["text"] == "النص الثاني"
    assert result.snippets[1]["text"] == "النص الأول"
