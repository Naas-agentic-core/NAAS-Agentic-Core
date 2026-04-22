import logging

from langchain_core.messages import AIMessage, SystemMessage

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

        system_message = SystemMessage(
            content="""أنت مساعد ذكي متخصص في الإجابة على أسئلة المعرفة العامة.
قم بالإجابة بشكل مباشر ودقيق باللغة العربية.
تجنب الإطالة وركز على إعطاء المعلومة المطلوبة بوضوح."""
        )

        # Build context: SystemMessage + last 6 messages + current query
        # Filter messages to ensure we only take the last 6 excluding system messages if needed,
        # but the requirement states: SystemMessage + last 6 messages + current query.

        # Determine the last 6 messages (excluding the very last one which is usually the current query,
        # but since we pass the current query separately, let's take up to 6 from history).
        # Actually, state["messages"] might already include the user's current query as the last message.
        # So we can take messages[-7:-1] to get the 6 before the current query, or just take messages[-6:].

        context_messages = []
        if len(messages) > 1:
            # exclude the last message if it's the current query, and take up to 6 of the remaining
            context_messages = messages[:-1][-6:]
        elif len(messages) == 1:
            # If there's only 1 message, it's probably the current query.
            pass

        # Build the final prompt list
        prompt_messages = [system_message, *context_messages]

        try:
            # We call the model
            # Note: ai_client.chat_completion typically takes a list of dicts or similar,
            # but AIClient in this repo might take a list of langchain messages or custom format.
            # Let's inspect AIClient or use a generic approach.

            # Since this repo uses langchain messages (e.g., `AIMessage` is used),
            # we should format them to the format expected by `ai_client.chat_completion()`.
            # Typically `chat_completion` expects `[{"role": "system", "content": "..."}, {"role": "user", "content": "..."}]`

            formatted_msgs = []
            for msg in prompt_messages:
                role = (
                    "system"
                    if getattr(msg, "type", "") == "system"
                    else getattr(msg, "type", getattr(msg, "role", "user"))
                )
                content = getattr(msg, "content", str(msg))
                formatted_msgs.append({"role": role, "content": content})

            formatted_msgs.append({"role": "user", "content": query})

            response_content = await ai_client.chat_completion(
                messages=formatted_msgs, temperature=0.3
            )

            emit_telemetry(node_name="GeneralKnowledgeNode", start_time=start_time, state=state)
            return {
                "final_response": response_content.strip(),
                "messages": [AIMessage(content=response_content.strip())]
            }

        except Exception as error:
            logger.error(f"GeneralKnowledgeNode failed: {error}", exc_info=True)
            fallback_response = "عذراً، لم أتمكن من استرجاع هذه المعلومة الآن."
            emit_telemetry(
                node_name="GeneralKnowledgeNode", start_time=start_time, state=state, error=error
            )
            return {
                "final_response": fallback_response,
                "messages": [AIMessage(content=fallback_response)]
            }
