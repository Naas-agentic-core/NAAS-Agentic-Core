from microservices.reasoning_agent.src.compat import (
    Context,
    Event,
    StartEvent,
    StopEvent,
    Workflow,
    step,
)
from microservices.reasoning_agent.src.core.logging import get_logger
from microservices.reasoning_agent.src.services.ai_service import ai_service
from microservices.reasoning_agent.src.services.strategies.mcts import mcts_strategy

logger = get_logger("reasoning-workflow")


class RetrievalEvent(Event):
    query: str
    context: str


class ReasoningWorkflow(Workflow):
    def __init__(self, timeout: int = 300, verbose: bool = True):
        super().__init__(timeout=timeout, verbose=verbose)
        self.strategy = mcts_strategy

    @step
    async def retrieve(self, ctx: Context, ev: StartEvent) -> RetrievalEvent:
        query = ev.get("query")
        context_str = ev.get("context", "")

        logger.info(f"Workflow started for query: {query}")

        # In a real scenario, this would call Research Agent.
        # For now, we accept context passed in or use a placeholder if empty.
        if not context_str:
            context_str = "No external context provided. Relying on internal knowledge."

        return RetrievalEvent(query=query, context=context_str)

    @step
    async def reason(self, ctx: Context, ev: RetrievalEvent) -> StopEvent:
        query = ev.query
        context = ev.context

        logger.info("Executing MCTS Strategy...")
        best_node = await self.strategy.execute(root_content=f"Analyze: {query}", context=context)

        logger.info(f"Selected best path: {best_node.content}")

        # Final Synthesis
        system_prompt = (
            "You are the Overmind Super Reasoner.\n"
            "Synthesize a final answer based on the provided reasoning path."
        )

        final_prompt = f"Query: {query}\nContext: {context}\nReasoning Path: {best_node.content}\n"

        result = await ai_service.generate_text(prompt=final_prompt, system_prompt=system_prompt)

        return StopEvent(result=result)


reasoning_workflow = ReasoningWorkflow()
