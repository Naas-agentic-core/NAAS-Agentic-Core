import logging

from langchain_core.messages import AIMessage, SystemMessage

from microservices.orchestrator_service.src.core.ai_gateway import get_ai_client

from .main import AgentState
from .supervisor import format_conversation_history

logger = logging.getLogger("graph")


def _query_has_resolved_entity(query: str) -> bool:
    words = [word.strip("؟?,.!؛:") for word in query.split() if word.strip("؟?,.!؛:")]
    if len(words) < 2:
        return False

    non_entity_tokens = {
        "ما",
        "ماذا",
        "من",
        "هي",
        "هو",
        "في",
        "على",
        "عن",
        "هل",
        "كم",
        "أين",
        "متى",
        "كيف",
        "لماذا",
    }
    for word in words:
        if word in non_entity_tokens:
            continue
        if word.endswith("ها") or word.endswith("هم") or word.endswith("هن"):
            continue
        if len(word) >= 3:
            return True
    return False


def _assert_query_integrity(query: str) -> None:
    assert "?" in query or "؟" in query or len(query.strip()) > 0
    if "ها" in query and not _query_has_resolved_entity(query):
        print("🚨 RAW PRONOUN LEAK DETECTED")
        raise AssertionError("Unresolved pronoun detected in query")


class GeneralKnowledgeNode:
    """عقدة مسؤولة عن الإجابة على أسئلة المعرفة العامة (مثل العواصم، التعداد السكاني، إلخ)."""

    async def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        messages = state.get("messages", [])
        query = str(state.get("query", "")).strip()
        print("NODE:", "GeneralKnowledgeNode")
        print("QUERY:", query)
        history = format_conversation_history(messages[:-1] if messages else [])
        print("RAW QUERY:", query)
        print("STATE QUERY:", query)
        print("HISTORY:", history)
        if not query:
            print("FAILURE POINT DETECTED:", "state['query'] is empty")
        if not history.strip():
            print("FAILURE POINT DETECTED:", "formatted conversation history is empty")

        ai_client = get_ai_client()

        system_message = SystemMessage(
            content="أجب بدقة اعتماداً على سياق المحادثة"
        )
        user_payload = f"Context:\n{history}\n\nQuestion:\n{query}"
        print("=== FINAL LLM INPUT ===")
        print("HISTORY:", history)
        print("QUERY:", query)

        try:
            _assert_query_integrity(query)
            formatted_msgs = [
                {"role": "system", "content": system_message.content},
                {"role": "user", "content": user_payload},
            ]

            response_content = await ai_client.chat_completion(
                messages=formatted_msgs, temperature=0.3
            )

            emit_telemetry(node_name="GeneralKnowledgeNode", start_time=start_time, state=state)
            return {
                "final_response": response_content.strip(),
                "messages": [AIMessage(content=response_content.strip())],
            }

        except Exception as error:
            logger.error(f"GeneralKnowledgeNode failed: {error}", exc_info=True)
            fallback_response = "عذراً، لم أتمكن من استرجاع هذه المعلومة الآن."
            emit_telemetry(
                node_name="GeneralKnowledgeNode", start_time=start_time, state=state, error=error
            )
            return {
                "final_response": fallback_response,
                "messages": [AIMessage(content=fallback_response)],
            }
