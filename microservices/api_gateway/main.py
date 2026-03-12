import asyncio
import hashlib
import importlib
import logging
from contextlib import asynccontextmanager
from urllib.parse import urlparse

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


def _to_ws_base_url(http_base_url: str) -> str:
    """يحوّل عنوان HTTP إلى WS بشكل صريح لتوحيد وجهة التوجيه بين HTTP وWebSocket."""
    parsed = urlparse(http_base_url)
    scheme = "wss" if parsed.scheme == "https" else "ws"
    netloc = parsed.netloc
    return f"{scheme}://{netloc}".rstrip("/")


def _resolve_chat_target_base(route_id: str, identity: str, rollout_percent: int) -> str:
    """يوحد قرار الوجهة بين HTTP وWS لمنع divergence لنفس النية."""
    use_conversation = _should_route_to_conversation(identity, rollout_percent)
    if use_conversation:
        target_base = settings.CONVERSATION_SERVICE_URL.rstrip("/")
        target_service = "conversation-service"
    else:
        target_base = settings.ORCHESTRATOR_SERVICE_URL.rstrip("/")
        target_service = "orchestrator-service"

    logger.info(
        "chat_routing_decision route_id=%s identity=%s rollout=%s target_service=%s target_base=%s",
        route_id,
        identity,
        rollout_percent,
        target_service,
        target_base,
    )
    return target_base


def _resolve_chat_ws_target(route_id: str, upstream_path: str) -> str:
    """يحدد هدف WS الحديث باستخدام نفس محرك القرار الخاص بمسار HTTP."""
    identity = f"{route_id}:{upstream_path}"
    target_base = _resolve_chat_target_base(
        route_id=route_id,
        identity=identity,
        rollout_percent=settings.ROUTE_CHAT_WS_CONVERSATION_ROLLOUT_PERCENT,
    )
    ws_base = _to_ws_base_url(target_base)
    return f"{ws_base}/{upstream_path}"


import uuid


class _NoOpSpan:
    """يمثل Span افتراضيًا لا ينفذ أي تتبع عند غياب حزمة OpenTelemetry."""

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


class _NoOpTracer:
    """يوفّر واجهة تتبع بديلة تضمن استمرار عمل البوابة دون تبعيات اختيارية."""

    def start_as_current_span(self, _name: str, attributes: dict[str, str] | None = None):
        _ = attributes
        return _NoOpSpan()


def _build_tracer() -> object:
    """ينشئ كائن التتبع الحقيقي إذا توفر OpenTelemetry وإلا يعيد بديلًا آمنًا."""
    if importlib.util.find_spec("opentelemetry"):
        import opentelemetry.trace
        return opentelemetry.trace.get_tracer(__name__)
    return _NoOpTracer()


def _inject_trace_context(headers: dict[str, str]) -> None:
    """يحقن سياق التتبع داخل الترويسات عند توفر وحدة propagate."""
    try:
        propagate_spec = importlib.util.find_spec("opentelemetry.propagate")
    except ModuleNotFoundError:
        return

    if propagate_spec is None:
        return

    propagate_module = importlib.import_module("opentelemetry.propagate")
    propagate_module.inject(headers)


tracer = _build_tracer()


def log_telemetry(event_name: str, trace_id: str):
    logger.info(f"TELEMETRY: {event_name} [trace_id: {trace_id}]")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Lifespan context manager for the FastAPI application.
    Handles startup and shutdown events.
    """
    logger.info("Starting API Gateway...")
    orchestrator_url = settings.ORCHESTRATOR_SERVICE_URL
    if not orchestrator_url:
        raise RuntimeError("ORCHESTRATOR_SERVICE_URL is missing")

    # Check orchestrator health
    for attempt in range(3):
        try:
            # Short timeout for health checks
            resp = await proxy_handler.client.get(f"{orchestrator_url}/health", timeout=2.0)
            if resp.status_code == 200:
                log_telemetry("gateway.ready", trace_id=str(uuid.uuid4()))
                break
        except Exception:
            pass
        if attempt == 2:
            raise RuntimeError("orchestrator-service is down")
        await asyncio.sleep(2**attempt)

    yield
    logger.info("Shutting down API Gateway...")
    await proxy_handler.close()


app = FastAPI(title=settings.PROJECT_NAME, lifespan=lifespan)

# Add Middleware
app.add_middleware(StructuredLoggingMiddleware)
app.add_middleware(RequestIdMiddleware)
app.add_middleware(TraceContextMiddleware)


# --- WebSocket Routes MUST BE FIRST to avoid being shadowed by wildcard API routes ---


@app.websocket("/api/chat/ws")
async def chat_ws_proxy(websocket: WebSocket):
    """
    Customer Chat WebSocket (Modern Target).
    TARGET: Orchestrator Service / Conversation Service
    """
    from starlette.websockets import WebSocketState

    route_id = "chat_ws_customer"
    with tracer.start_as_current_span("ws.proxy", attributes={"agent": "orchestrator"}):
        headers = {}
        _inject_trace_context(headers)
        logger.info(
            f"Chat WebSocket route_id={route_id} legacy_flag=false traceparent={headers.get('traceparent', 'unknown')}"
        )
        _record_ws_session_metric(route_id)
        target_url = _resolve_chat_ws_target(route_id, "api/chat/ws")
        try:
            await websocket_proxy(websocket, target_url)
        except Exception:
            log_telemetry("ws.proxy.failed", trace_id=str(uuid.uuid4()))
            if websocket.client_state == WebSocketState.UNCONNECTED:
                await websocket.accept()
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(
                    {"error": "تعذر فتح جلسة الدردشة حالياً.", "request_id": str(uuid.uuid4())}
                )
                await websocket.close()


@app.websocket("/admin/api/chat/ws")
async def admin_chat_ws_proxy(websocket: WebSocket):
    """
    Admin Chat WebSocket (Modern Target).
    TARGET: Orchestrator Service / Conversation Service
    """
    from starlette.websockets import WebSocketState

    route_id = "chat_ws_admin"
    with tracer.start_as_current_span("ws.proxy", attributes={"agent": "orchestrator"}):
        headers = {}
        _inject_trace_context(headers)
        logger.info(
            f"Chat WebSocket route_id={route_id} legacy_flag=false traceparent={headers.get('traceparent', 'unknown')}"
        )
        _record_ws_session_metric(route_id)
        target_url = _resolve_chat_ws_target(route_id, "admin/api/chat/ws")
        try:
            await websocket_proxy(websocket, target_url)
        except Exception:
            log_telemetry("ws.proxy.failed", trace_id=str(uuid.uuid4()))
            if websocket.client_state == WebSocketState.UNCONNECTED:
                await websocket.accept()
            if websocket.client_state == WebSocketState.CONNECTED:
                await websocket.send_json(
                    {
                        "error": "تعذر فتح جلسة الدردشة الإدارية حالياً.",
                        "request_id": str(uuid.uuid4()),
                    }
                )
                await websocket.close()


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
    target_url = _resolve_chat_target_base(
        route_id="chat_http",
        identity=identity,
        rollout_percent=settings.ROUTE_CHAT_HTTP_CONVERSATION_ROLLOUT_PERCENT,
    )

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
