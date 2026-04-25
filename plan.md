1. **Execution Paths Table**: Analyze all entrypoints and how they interact with LangGraph vs Manual Agents.
2. **LangGraph Memory Behavior**: Explain how LangGraph handles memory via checkpointer and thread IDs.
3. **Manual Agent Memory Behavior**: Explain how OrchestratorAgent uses the history passed in context.
4. **Hydration Behavior**: Deconstruct `_build_graph_messages` and its effect on state.
5. **Collision Explanation**: Detail exactly what happens when both paths collide.
6. **Root Cause Chain**: Construct a root cause logic flow to prove exactly how context is lost.
