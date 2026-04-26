import logging

from langchain_core.messages import AIMessage

from microservices.orchestrator_service.src.core.ai_gateway import get_ai_client

from .main import AgentState
from .supervisor import format_conversation_history

logger = logging.getLogger("graph")


class GeneralKnowledgeNode:
    """عقدة مسؤولة عن الإجابة على أسئلة المعرفة العامة (مثل العواصم، التعداد السكاني، إلخ)."""

    async def __call__(self, state: AgentState) -> dict:
        import time

        from .telemetry import emit_telemetry

        start_time = time.time()

        logger.info(f"[GK] state keys={list(state.keys())}")
        logger.info(f"[GK] query={state.get('query')}")
        logger.info(f"[GK] messages[-1]={state.get('messages', [])[-1] if state.get('messages') else 'EMPTY'}")

        messages = state.get("messages", [])

        # DO NOT override state["query"] with raw message content if it exists
        query = state.get("query")
        if not query and messages:
            last_msg = messages[-1]
            query = last_msg.get("content") if isinstance(last_msg, dict) else getattr(last_msg, "content", "")
        query = str(query or "").strip()

        logger.info(f"[FINAL QUERY USED]: {query}")

        # Exclude ONLY the message matching the active query to prevent prompt contamination.
        # State is NOT modified. Do not use blanket slice messages[:-1].
        prompt_messages = []
        original_query_normalized = str(state.get("original_query") or "").strip()
        query_normalized = query.strip()

        for msg in messages:
            role = msg.get("role") or msg.get("type") if isinstance(msg, dict) else getattr(msg, "type", getattr(msg, "role", ""))
            content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")

            if role in ("human", "user"):
                content_normalized = str(content).strip()
                if content_normalized == query_normalized or (original_query_normalized and content_normalized == original_query_normalized):
                    continue
            prompt_messages.append(msg)

        history = format_conversation_history(prompt_messages)

        if not history.strip():
            print("🚨 FAILURE: EMPTY HISTORY")

        if "ها" in query and "فرنسا" not in query:
            print("🚨 PRONOUN LEAK DETECTED")

        if "فرنسا" not in history:
            print("🚨 ENTITY LOST IN HISTORY")

        print("=== FINAL LLM INPUT ===")
        print("HISTORY:", history)
        print("QUERY:", query)

        ai_client = get_ai_client()

        system_content = "أجب بدقة اعتماداً على سياق المحادثة. لا تتجاهل السياق أبداً."
        user_content = f"السياق:\n{history}\n\nالسؤال:\n{query}"

        try:
            response_content = await ai_client.send_message(
                system_prompt=system_content, user_message=user_content, temperature=0.3
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
