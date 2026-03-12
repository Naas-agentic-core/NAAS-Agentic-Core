import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure models are registered with SQLModel
import microservices.orchestrator_service.src.models.mission  # noqa: F401
from microservices.orchestrator_service.src.api import routes
from microservices.orchestrator_service.src.core.config import settings
from microservices.orchestrator_service.src.core.database import init_db
from microservices.orchestrator_service.src.core.event_bus import event_bus
from microservices.orchestrator_service.src.services.tools.registry import register_all_tools

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("orchestrator_service")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """يدير دورة حياة الخدمة مع ضمان الإقلاع حتى عند غياب تبعيات اختيارية."""
    logger.info("Orchestrator Service Starting...")
    await init_db()

    # ═══ PHASE 1: TOOLS FIRST ══════════════════════════════════
    from microservices.orchestrator_service.src.services.tools.registry import get_registry

    register_all_tools()

    tool_registry = get_registry()
    required = [
        "admin.count_python_files",
        "admin.count_database_tables",
        "admin.get_user_count",
        "admin.list_microservices",
        "admin.calculate_full_stats",
    ]
    missing = [t for t in required if not tool_registry.get(t)]
    if missing:
        raise RuntimeError(f"STARTUP BLOCKED — missing tools: {missing}")

    app.state.admin_app = None
    app.state.app_graph = None

    # ═══ PHASE 2: GRAPHS AFTER TOOLS ═══════════════════════════
    try:
        from langgraph.checkpoint.memory import MemorySaver

        from microservices.orchestrator_service.src.services.overmind.graph.admin import admin_graph
        from microservices.orchestrator_service.src.services.overmind.graph.main import (
            create_unified_graph,
        )

        app.state.admin_app = admin_graph.compile(checkpointer=MemorySaver(), interrupt_before=[])
        app.state.app_graph = create_unified_graph(admin_app=app.state.admin_app)

        # ═══ PHASE 3: WARMUP — PROVE IT WORKS ══════════════════════
        result = await app.state.admin_app.ainvoke(
            {"query": "كم عدد ملفات بايثون", "is_admin_user": True},
            config={"configurable": {"thread_id": "warmup"}},
        )

        final_res = result.get("final_response", {})
        if not final_res.get("tool_name"):
            raise RuntimeError(
                "WARMUP FAILED — tools registered but graph not invoking them. "
                "Check ExecuteToolNode → tool_registry.get() call."
            )

        logger.info(f"✅ SYSTEM READY | warmup tool={final_res['tool_name']}")
    except ModuleNotFoundError as error:
        logger.warning("Graph bootstrap skipped بسبب تبعية غير متاحة: %s", error)

    yield

    # ═══ SHUTDOWN ═══════════════════════════════════════════════
    await event_bus.close()
    tool_registry.clear()
    if hasattr(app.state, "admin_app"):
        del app.state.admin_app
    if hasattr(app.state, "app_graph"):
        del app.state.app_graph


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes.router)


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "orchestrator-service"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "microservices.orchestrator_service.main:app", host="0.0.0.0", port=8000, reload=True
    )
