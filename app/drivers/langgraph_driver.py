from typing import Any

from app.core.integration_kernel.contracts import WorkflowEngine
from app.core.integration_kernel.ir import WorkflowPlan
from app.core.logging import get_logger

logger = get_logger(__name__)


class LangGraphDriver(WorkflowEngine):
    """
    Driver for LangGraph workflow execution.
    """

    async def run(self, plan: WorkflowPlan) -> dict[str, Any]:
        """
        Executes a workflow plan using LangGraph.
        """
        try:
            # Lazy import to avoid circular dependencies and ensure isolation
            from microservices.orchestrator_service.src.services.overmind.domain.api_schemas import LangGraphRunRequest
            from microservices.orchestrator_service.src.services.overmind.langgraph.service import create_langgraph_service

            service = create_langgraph_service()
            request = LangGraphRunRequest(
                goal=plan.goal,
                context=plan.context or {},
            )

            result = await service.run(request)

            return {
                "success": True,
                "run_id": result.run_id,
                "final_answer": result.final_answer,
                "steps": result.steps,
            }
        except Exception as e:
            logger.error(f"LangGraph execution error: {e}")
            return {"success": False, "error": str(e)}

    def get_status(self) -> dict[str, Any]:
        """
        Returns the health status of the LangGraph engine.
        """
        try:
            from microservices.orchestrator_service.src.services.overmind.langgraph import LangGraphAgentService  # noqa: F401

            return {
                "status": "active",
                "driver": "LangGraphDriver",
                "agents": ["contextualizer", "strategist", "architect", "operator", "auditor"],
                "supervisor": "active",
            }
        except ImportError:
            return {"status": "unavailable", "error": "LangGraph dependencies missing"}
