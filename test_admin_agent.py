import asyncio
from langchain_core.messages import HumanMessage
from microservices.orchestrator_service.src.services.overmind.graph.admin import AdminAgentNode

async def test():
    node = AdminAgentNode()
    state = {"messages": [HumanMessage(content="حساب عدد الملفات")]}
    res = await node(state)
    print("AdminAgentNode Response:", res)

asyncio.run(test())
