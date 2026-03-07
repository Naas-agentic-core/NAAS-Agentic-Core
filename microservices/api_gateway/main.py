import asyncio
import hashlib
import logging
from contextlib import asynccontextmanager

import uvicorn
from fastapi import Depends, FastAPI, Request, WebSocket
from fastapi.responses import StreamingResponse

# Local imports
from microservices.api_gateway.config import settings
from microservices.api_gateway.middleware import (
    RequestIdMiddleware,
    StructuredLoggingMiddleware,
    TraceContextMiddleware,
)
from microservices.api_gateway.proxy import GatewayProxy
from microservices.api_gateway.security import create_service_token, verify_gateway_request
from microservices.api_gateway.websockets import websocket_proxy

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("api_gateway")

# Initialize the proxy handler
proxy_handler = GatewayProxy()
legacy_ws_sessions_total: dict[str, int] = {}


def _record_ws_session_metric(route_id: str) -> None:
    """يسجل عداد جلسات WS الحديثة مع وسم route_id وlegacy_flag=false."""
    legacy_ws_sessions_total[route_id] = legacy_ws_sessions_total.get(route_id, 0) + 1
    logger.info(
        "legacy_ws_sessions_total=%s route_id=%s legacy_flag=false",
        legacy_ws_sessions_total[route_id],
        route_id,
    )


def _rollout_bucket(identity: str) -> int:
    """يولّد Bucket حتمي بين 0 و99 لدعم canary تدريجي آمن وقابل للإرجاع."""
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def _should_route_to_conversation(identity: str, rollout_percent: int) -> bool:
    """يحدد قرار التوجيه التدريجي إلى Conversation Service وفق نسبة مئوية مضبوطة."""
    normalized = max(0, min(100, rollout_percent))
    if normalized == 0:
        return False
    if normalized == 100:
        return True
    return _rollout_bucket(identity) < normalized


def _resolve_chat_ws_target(route_id: str, upstream_path: str) -> str:
    """يحدد هدف WS الحديث بين orchestrator وconversation وفق canary تدريجي."""
    identity = f"{route_id}:{upstream_path}"
    use_conversation = _should_route_to_conversation(
        identity, settings.ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT
    )
    if use_conversation:
        candidate = settings.CONVERSATION_WS_URL.rstrip("/")
        logger.info("chat_ws_candidate route_id=%s legacy=false target=%s", route_id, candidate)
        return f"{candidate}/{upstream_path}"

    fallback_target = settings.ORCHESTRATOR_SERVICE_URL.replace("http", "ws", 1).rstrip("/")
    logger.info(
        "chat_ws_orchestrator route_id=%s legacy=false target=%s", route_id, fallback_target
    )
    return f"{fallback_target}/{upstream_path}"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI application.
    Handles startup and shutdown events.
    """
    logger.info("Starting API Gateway...")
    yield
    logger.info("Shutting down API Gateway...")
    await proxy_handler.close()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# Add Middleware
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(TraceContextMiddleware)


@app.get("/health")
async def health_check():
    """
    Health check endpoint that verifies connectivity to downstream services.
    Returns a detailed status report.
    """
    services = {
        "planning_agent": settings.PLANNING_AGENT_URL,
        "memory_agent": settings.MEMORY_AGENT_URL,
        "user_service": settings.USER_SERVICE_URL,
        "observability_service": settings.OBSERVABILITY_SERVICE_URL,
        "research_agent": settings.RESEARCH_AGENT_URL,
        "reasoning_agent": settings.REASONING_AGENT_URL,
        "orchestrator_service": settings.ORCHESTRATOR_SERVICE_URL,
    }

    async def check_service(name: str, url: str):
        try:
            # Short timeout for health checks
            resp = await proxy_handler.client.get(f"{url}/health", timeout=2.0)
            status = "UP" if resp.status_code == 200 else f"DOWN ({resp.status_code})"
            return name, status
        except Exception as e:
            return name, f"DOWN ({e!s})"

    # Run checks concurrently
    results = await asyncio.gather(*(check_service(name, url) for name, url in services.items()))
    dependencies = dict(results)

    # Determine overall status
    overall_status = "ok"
    if any(s.startswith("DOWN") for s in dependencies.values()):
        overall_status = "degraded"

    return {
        "status": overall_status,
        "service": "api-gateway",
        "dependencies": dependencies,
    }


@app.get("/gateway/health")
async def gateway_health_check():
    """
    Alias for /health.
    Matches legacy documentation expectations.
    """
    return await health_check()


# --- Smart Routing ---


@app.websocket("/api/chat/ws")
async def chat_ws_proxy(websocket: WebSocket):
    """
    Customer Chat WebSocket (Modern Target).
    TARGET: Orchestrator Service / Conversation Service
    """
    route_id = "chat_ws_customer"
    logger.info("Chat WebSocket route_id=%s legacy_flag=false", route_id)
    _record_ws_session_metric(route_id)
    target_url = _resolve_chat_ws_target(route_id, "api/chat/ws")
    await websocket_proxy(websocket, target_url)


@app.websocket("/admin/api/chat/ws")
async def admin_chat_ws_proxy(websocket: WebSocket):
    """
    Admin Chat WebSocket (Modern Target).
    TARGET: Orchestrator Service / Conversation Service
    """
    route_id = "chat_ws_admin"
    logger.info("Chat WebSocket route_id=%s legacy_flag=false", route_id)
    _record_ws_session_metric(route_id)
    target_url = _resolve_chat_ws_target(route_id, "admin/api/chat/ws")
    await websocket_proxy(websocket, target_url)


@app.api_route(
    "/api/v1/planning/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def planning_proxy(path: str, request: Request) -> StreamingResponse:
    return await proxy_handler.forward(
        request, settings.PLANNING_AGENT_URL, path, service_token=create_service_token()
    )


@app.api_route(
    "/api/v1/memory/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def memory_proxy(path: str, request: Request) -> StreamingResponse:
    return await proxy_handler.forward(
        request, settings.MEMORY_AGENT_URL, path, service_token=create_service_token()
    )


@app.api_route(
    "/api/v1/users/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def user_proxy(path: str, request: Request) -> StreamingResponse:
    return await proxy_handler.forward(
        request, settings.USER_SERVICE_URL, path, service_token=create_service_token()
    )


@app.api_route(
    "/api/v1/auth/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def auth_proxy(path: str, request: Request) -> StreamingResponse:
    """
    Proxy Auth routes (Login/Register) to User Service.
    Resolves ambiguity between Monolith UMS and Microservice.
    """
    return await proxy_handler.forward(
        request,
        settings.USER_SERVICE_URL,
        f"api/v1/auth/{path}",
        service_token=create_service_token(),
    )


@app.api_route(
    "/api/v1/observability/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def observability_proxy(path: str, request: Request) -> StreamingResponse:
    return await proxy_handler.forward(
        request,
        settings.OBSERVABILITY_SERVICE_URL,
        path,
        service_token=create_service_token(),
    )


@app.api_route(
    "/api/v1/research/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def research_proxy(path: str, request: Request) -> StreamingResponse:
    return await proxy_handler.forward(
        request, settings.RESEARCH_AGENT_URL, path, service_token=create_service_token()
    )


@app.api_route(
    "/api/v1/reasoning/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def reasoning_proxy(path: str, request: Request) -> StreamingResponse:
    return await proxy_handler.forward(
        request, settings.REASONING_AGENT_URL, path, service_token=create_service_token()
    )


@app.api_route(
    "/api/v1/overmind/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def orchestrator_proxy(path: str, request: Request) -> StreamingResponse:
    return await proxy_handler.forward(
        request,
        settings.ORCHESTRATOR_SERVICE_URL,
        path,
        service_token=create_service_token(),
    )


@app.api_route(
    "/api/v1/missions",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def missions_root_proxy(request: Request) -> StreamingResponse:
    """
    Strangler Fig: Route missions root to Orchestrator Service.
    Decouples mission control from the Monolith.
    """
    return await proxy_handler.forward(
        request,
        settings.ORCHESTRATOR_SERVICE_URL,
        "missions",
        service_token=create_service_token(),
    )


@app.api_route(
    "/api/v1/missions/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    dependencies=[Depends(verify_gateway_request)],
)
async def missions_path_proxy(path: str, request: Request) -> StreamingResponse:
    """
    Strangler Fig: Route missions paths to Orchestrator Service.
    """
    return await proxy_handler.forward(
        request,
        settings.ORCHESTRATOR_SERVICE_URL,
        f"missions/{path}",
        service_token=create_service_token(),
    )


# --- COMPATIBILITY ROUTES (MICROSERVICES TARGETS) ---


@app.api_route(
    "/admin/ai-config",
    methods=["GET", "PUT", "OPTIONS", "HEAD"],
    include_in_schema=False,
    deprecated=True,
)
async def admin_ai_config_proxy(request: Request) -> StreamingResponse:
    """
    [LEGACY] Strangler Fig: Route AI Config to Monolith.
    TARGET: User Service (Pending Migration)
    """
    logger.info("Route accessed: /admin/ai-config -> user-service")
    return await proxy_handler.forward(
        request,
        settings.USER_SERVICE_URL,
        "api/v1/admin/ai-config",
        service_token=create_service_token(),
    )


@app.api_route(
    "/admin/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def admin_proxy(path: str, request: Request) -> StreamingResponse:
    """
    Proxy Admin routes to User Service (UMS).
    Rewrite: /admin/{path} -> /api/v1/admin/{path}
    """
    # This is NOT legacy monolith, it points to USER_SERVICE.
    return await proxy_handler.forward(
        request,
        settings.USER_SERVICE_URL,
        f"api/v1/admin/{path}",
        service_token=create_service_token(),
    )


@app.api_route(
    "/api/security/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    include_in_schema=False,
)
async def security_proxy(path: str, request: Request) -> StreamingResponse:
    """
    Proxy Security routes to User Service (Auth).
    Rewrite: /api/security/{path} -> /api/v1/auth/{path}
    """
    # This is NOT legacy monolith, it points to USER_SERVICE.
    return await proxy_handler.forward(
        request,
        settings.USER_SERVICE_URL,
        f"api/v1/auth/{path}",
        service_token=create_service_token(),
    )


@app.api_route(
    "/api/chat/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    include_in_schema=False,
    deprecated=True,
)
async def chat_http_proxy(path: str, request: Request) -> StreamingResponse:
    """
    HTTP Chat Proxy (Modern Target).
    TARGET: Orchestrator Service / Conversation Service
    """
    logger.info("Route accessed: /api/chat/%s (modern routing)", path)
    identity = request.headers.get("x-request-id", request.url.path)
    target_url = settings.ORCHESTRATOR_SERVICE_URL
    if _should_route_to_conversation(
        identity, settings.ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT
    ):
        target_url = settings.CONVERSATION_SERVICE_URL

    return await proxy_handler.forward(
        request,
        target_url,
        f"api/chat/{path}",
        service_token=create_service_token(),
    )


@app.api_route(
    "/v1/content/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    include_in_schema=False,
    deprecated=True,
)
async def content_proxy(path: str, request: Request) -> StreamingResponse:
    """
    [LEGACY] Content Service Proxy.
    TARGET: Content Service (To Be Extracted)
    """
    logger.info("Route accessed: /v1/content/%s -> research-agent", path)
    return await proxy_handler.forward(
        request,
        settings.RESEARCH_AGENT_URL,
        f"v1/content/{path}",
        service_token=create_service_token(),
    )


@app.api_route(
    "/api/v1/data-mesh/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    include_in_schema=False,
    deprecated=True,
)
async def datamesh_proxy(path: str, request: Request) -> StreamingResponse:
    """
    [LEGACY] Data Mesh Proxy.
    TARGET: Data Mesh Service
    """
    logger.info("Route accessed: /api/v1/data-mesh/%s -> observability-service", path)
    return await proxy_handler.forward(
        request,
        settings.OBSERVABILITY_SERVICE_URL,
        f"api/v1/data-mesh/{path}",
        service_token=create_service_token(),
    )


@app.api_route(
    "/system/{path:path}",
    methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS", "HEAD"],
    include_in_schema=False,
    deprecated=True,
)
async def system_proxy(path: str, request: Request) -> StreamingResponse:
    """
    [LEGACY] System Routes Proxy.
    TARGET: System Service
    """
    logger.info("Route accessed: /system/%s -> orchestrator-service", path)
    return await proxy_handler.forward(
        request,
        settings.ORCHESTRATOR_SERVICE_URL,
        f"system/{path}",
        service_token=create_service_token(),
    )


if __name__ == "__main__":
    uvicorn.run("microservices.api_gateway.main:app", host="0.0.0.0", port=8000, reload=True)
