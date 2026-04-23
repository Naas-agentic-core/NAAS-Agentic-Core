import logging

from langchain_core.messages import AIMessage

from microservices.orchestrator_service.src.core.ai_gateway import get_ai_client

from .main import AgentState

logger = logging.getLogger("graph")


class GeneralKnowledgeNode:
    """عقدة مسؤولة عن الإجابة على أسئلة المعرفة العامة (مثل العواصم، التعداد السكاني، إلخ)."""

    async def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()
        query = state.get("query", "")
        messages = state.get("messages", [])

        ai_client = get_ai_client()

        from .main import format_conversation_history

        # EXCLUDE raw pronoun question from history to prevent LLM from seeing it
        history = format_conversation_history(messages[:-1]) if messages else ""

        # FORENSIC PRINTS
        logger.debug(f"RAW QUERY: {messages[-1].content if messages else ''}")
        logger.debug(f"STATE QUERY: {query}")
        logger.debug(f"HISTORY: {history}")

        prompt_messages = [
            {"role": "system", "content": "أجب بدقة اعتماداً على سياق المحادثة"},
            {"role": "user", "content": f"Context:\n{history}\n\nQuestion:\n{query}"}
        ]

        try:
            # MANDATORY FORENSIC PRINTS BEFORE LLM CALL
            logger.debug("=== FINAL LLM INPUT ===")
            logger.debug(f"HISTORY: {history}")
            logger.debug(f"QUERY: {query}")

            response_content = await ai_client.chat_completion(
                messages=prompt_messages, temperature=0.3
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
