import asyncio
from microservices.orchestrator_service.src.services.overmind.graph.search import QueryAnalyzerNode

async def run_trace():
    print("[QUERY_PATH] Tracing QueryAnalyzerNode")
    node = QueryAnalyzerNode()

    q1 = "تمرين الاحتمالات بكالوريا شعبة علوم تجريبية"
    q2 = "تمرين الاعداد المركبة لسنة 2024"

    res1 = await node({"query": q1, "messages": []})
    print(f"[QUERY_PATH] Q1 Output: {res1}")

    res2 = await node({"query": q2, "messages": []})
    print(f"[QUERY_PATH] Q2 Output: {res2}")

if __name__ == "__main__":
    asyncio.run(run_trace())
