import asyncio
import logging
import sys
from unittest.mock import AsyncMock, MagicMock, patch

from langchain_core.messages import AIMessage, HumanMessage

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("verify_supervisor")

# --- MOCKING HEAVY DEPENDENCIES ---
# We mock these BEFORE importing app code to avoid installation requirements
sys.modules["llama_index"] = MagicMock()
sys.modules["llama_index.core"] = MagicMock()
sys.modules["llama_index.core.schema"] = MagicMock()
sys.modules["llama_index.core.workflow"] = MagicMock()
sys.modules["llama_index.core.retrievers"] = MagicMock()
sys.modules["llama_index.core.postprocessor"] = MagicMock()
sys.modules["llama_index.embeddings.huggingface"] = MagicMock()
sys.modules["llama_index.embeddings.openai"] = MagicMock()
sys.modules["llama_index.llms.openai"] = MagicMock()
sys.modules["llama_index.vector_stores.qdrant"] = MagicMock()
sys.modules["dspy"] = MagicMock()

# Mock settings to avoid database connection
sys.modules["app.core.database"] = MagicMock()
sys.modules["app.core.database"].get_db = MagicMock()

# Mock retrieval specifically to avoid loading heavy machinery
mock_retriever = MagicMock()
sys.modules["microservices.research_agent.src.search_engine.retriever"] = mock_retriever
# Mock the specific llama_retriever to avoid metaclass conflicts
sys.modules["microservices.research_agent.src.search_engine.llama_retriever"] = MagicMock()

# Mock Overmind Factory
sys.modules["microservices.orchestrator_service.src.services.overmind.factory"] = MagicMock()
# ----------------------------------


# Mock AI Logic
async def handle_send_message(system_prompt, user_message):
    logger.info(f"AI Client invoked. Prompt snippet: {system_prompt[:30]}...")

    # PRIORITY ORDER IS CRITICAL

    # 7. Review Passed (9.0) -> FINISH
    if "Last Review Score: 9.0" in user_message:
        logger.info("  -> [Sim] Decision: FINISH")
        return '{"next": "FINISH", "reason": "Quality met"}'

    # 6. Retry Done -> Reviewer
    if "Draft response (v2)" in user_message:
        logger.info("  -> [Sim] Decision: REVIEWER (RE-CHECK)")
        return '{"next": "reviewer", "reason": "Re-review v2"}'

    # 5. Review Failed (5.0) -> Writer (Retry)
    if "Last Review Score: 5.0" in user_message:
        logger.info("  -> [Sim] Decision: WRITER (RETRY)")
        return '{"next": "writer", "reason": "Fix draft based on feedback"}'

    # 4. Draft Done -> Reviewer
    if "Draft response" in user_message and "Last Review Score: None" in user_message:
        logger.info("  -> [Sim] Decision: REVIEWER")
        return '{"next": "reviewer", "reason": "Quality Check"}'

    # 3. Research Done -> Writer
    if "Found some info" in user_message:
        logger.info("  -> [Sim] Decision: WRITER")
        return '{"next": "writer", "reason": "Have info, write draft"}'

    # 2. Plan Created -> Researcher (Only if not already found info)
    if (
        "Current Plan: ['search', 'write']" in user_message
        and "Current Step Index: 0" in user_message
    ):
        logger.info("  -> [Sim] Decision: RESEARCHER")
        return '{"next": "researcher", "reason": "Execute search step"}'

    # 1. New Request -> Planner
    if "No history" in user_message or "Current Plan: []" in user_message:
        logger.info("  -> [Sim] Decision: PLANNER")
        return '{"next": "planner", "reason": "New request"}'

    logger.warning("  -> [Sim] Fallback Decision: FINISH")
    return '{"next": "FINISH", "reason": "Fallback"}'


# Mock Nodes
async def mock_planner(state, ai_client):
    logger.info(">>> Node: PLANNER")
    return {"plan": ["search", "write"], "messages": [AIMessage(content="Plan created")]}


async def mock_researcher(state, tools):
    logger.info(">>> Node: RESEARCHER")
    return {
        "search_results": [{"content": "Info found"}],
        "messages": [AIMessage(content="Found some info")],
    }


async def mock_writer(state, ai_client):
    logger.info(">>> Node: WRITER")
    score = state.get("review_score")
    msg = "Draft response (v2)" if score == 5.0 else "Draft response"
    return {"final_response": msg, "messages": [AIMessage(content=msg)]}


async def mock_reviewer(state, ai_client):
    logger.info(">>> Node: REVIEWER")
    last_response = state.get("final_response", "")
    score = 9.0 if "v2" in last_response else 5.0
    logger.info(f"    Score: {score}")
    return {
        "review_score": score,
        "review_feedback": "Check accuracy",
        "messages": [AIMessage(content=f"Review: {score}")],
    }


async def run_verification():
    # Import locally to apply mocks
    try:
        import app.services.chat.graph.workflow as workflow_module
    except ImportError as e:
        logger.error(f"Import Error: {e}")
        raise

    # Patch attributes on the imported module
    with (
        patch.object(workflow_module, "planner_node", side_effect=mock_planner),
        patch.object(workflow_module, "researcher_node", side_effect=mock_researcher),
        patch.object(workflow_module, "writer_node", side_effect=mock_writer),
        patch.object(workflow_module, "reviewer_node", side_effect=mock_reviewer),
    ):
        # Setup AI Client Mock
        ai_client = MagicMock()
        ai_client.send_message = AsyncMock(side_effect=handle_send_message)

        graph = workflow_module.create_multi_agent_graph(ai_client, MagicMock())

        inputs = {"messages": [HumanMessage(content="Explain quantum physics.")]}

        logger.info("=== STARTING GRAPH EXECUTION ===")
        try:
            async for output in graph.astream(inputs, {"recursion_limit": 20}):
                for node, state in output.items():
                    if "supervisor" in node:
                        routing_trace = state.get("routing_trace")
                        reason = routing_trace[0].get("reason") if routing_trace else "Unknown"
                        logger.info(f"SUPERVISOR: Next -> {state.get('next')} ({reason})")
                    else:
                        logger.info(f"--- Node '{node}' Finished ---")
        except Exception as e:
            logger.error(f"Execution failed: {e}")
            raise


if __name__ == "__main__":
    asyncio.run(run_verification())
