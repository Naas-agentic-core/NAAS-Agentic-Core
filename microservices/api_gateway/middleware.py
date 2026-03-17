import logging
import time
import uuid
from collections.abc import Callable

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware

logger = logging.getLogger("api_gateway")


def _build_traceparent() -> str:
    trace_id = uuid.uuid4().hex + uuid.uuid4().hex[:16]
    parent_id = uuid.uuid4().hex[:16]
    return f"00-{trace_id}-{parent_id}-01"


class RequestIdMiddleware(BaseHTTPMiddleware):
    """
    Middleware to ensure every request has a unique ID.
    This ID is attached to the request state and the response headers.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        # Generate a new Request ID if not present in headers (or always generate new one)
        # Prioritizing generating a new one to ensure uniqueness within our system
        incoming_correlation_id = request.headers.get("X-Correlation-ID")
        request_id = incoming_correlation_id or str(uuid.uuid4())
        request.state.request_id = request_id
        request.state.correlation_id = request_id

        # Process the request
        response = await call_next(request)

        # Attach to response
        response.headers["X-Request-ID"] = request_id
        response.headers["X-Correlation-ID"] = request_id
        return response


class StructuredLoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware to log request details in a structured format.
    Logs entry and exit of requests with timing and status codes.
    """

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        request_id = getattr(request.state, "request_id", "unknown")
        start_time = time.perf_counter()
        method = request.method
        path = request.url.path
        client_host = request.client.host if request.client else "unknown"

        # Log Request Start
        # In a real "structured" logger (like structlog), this would be a dict.
        # Here we use a key-value string format for easy parsing.
        logger.info(
            f"request_started method={method} path={path} "
            f"client_ip={client_host} request_id={request_id}"
        )

        try:
            response = await call_next(request)
            process_time = time.perf_counter() - start_time

            # Log Request Completion
            logger.info(
                f"request_completed method={method} path={path} "
                f"status={response.status_code} duration={process_time:.4f}s "
                f"request_id={request_id}"
            )
            return response

        except Exception as e:
            process_time = time.perf_counter() - start_time
            logger.error(
                f"request_failed method={method} path={path} "
                f"duration={process_time:.4f}s request_id={request_id} "
                f"error={e!s}"
            )
            raise e


class TraceContextMiddleware(BaseHTTPMiddleware):
    """يضمن تمرير سياق W3C traceparent عبر البوابة إلى الخدمات الخلفية."""

    async def dispatch(self, request: Request, call_next: Callable) -> Response:
        traceparent = request.headers.get("traceparent") or _build_traceparent()
        request.state.traceparent = traceparent
        response = await call_next(request)
        response.headers["traceparent"] = traceparent
        return response
