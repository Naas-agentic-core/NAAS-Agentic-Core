import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import ParamSpec, TypeVar

import httpx
from fastapi import HTTPException, Request, status
from fastapi.responses import StreamingResponse

from microservices.api_gateway.config import settings

logger = logging.getLogger("api_gateway")

P = ParamSpec("P")
R = TypeVar("R")


class CircuitState(StrEnum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreaker:
    """
    Implements the Circuit Breaker pattern to prevent cascading failures.
    Tracks failures and opens the circuit when a threshold is reached.
    """

    def __init__(
        self,
        name: str,
        failure_threshold: int = settings.CIRCUIT_BREAKER_FAILURE_THRESHOLD,
        recovery_timeout: float = settings.CIRCUIT_BREAKER_RECOVERY_TIMEOUT,
    ):
        self.name = name
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.state = CircuitState.CLOSED
        self.failures = 0
        self.last_failure_time = 0.0

    async def execute(
        self, func: Callable[P, Awaitable[R]], *args: P.args, **kwargs: P.kwargs
    ) -> R:
        """
        Executes the given async function with circuit breaker logic.
        """
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                logger.info(
                    f"Circuit '{self.name}' state changed to HALF_OPEN. Testing connection..."
                )
            else:
                # Circuit is open, fail fast
                logger.warning(f"Circuit '{self.name}' is OPEN. Blocking request.")
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail=f"Service '{self.name}' is temporarily unavailable.",
                )

        try:
            result = await func(*args, **kwargs)

            # If successful and was half-open, close it
            if self.state == CircuitState.HALF_OPEN:
                self.state = CircuitState.CLOSED
                self.failures = 0
                logger.info(f"Circuit '{self.name}' recovered. State changed to CLOSED.")

            return result
        except HTTPException:
            # Re-raise HTTP exceptions (like 404, 400) without counting as system failure
            raise
        except Exception as e:
            # Count failure for network/system errors
            self.failures += 1
            self.last_failure_time = time.time()
            logger.error(f"Circuit '{self.name}' recorded failure #{self.failures}: {e!s}")

            if self.state == CircuitState.HALF_OPEN or self.failures >= self.failure_threshold:
                self.state = CircuitState.OPEN
                logger.error(f"Circuit '{self.name}' threshold reached. State changed to OPEN.")

            raise e


class GatewayProxy:
    """
    Reverse proxy handler with Circuit Breaker support, Streaming, and Retries.
    """

    def __init__(self):
        # We will use a single client for connection pooling
        limits = httpx.Limits(
            max_keepalive_connections=settings.POOL_LIMIT,
            max_connections=settings.POOL_LIMIT,
        )
        timeouts = httpx.Timeout(
            connect=settings.CONNECT_TIMEOUT,
            read=settings.READ_TIMEOUT,
            write=settings.WRITE_TIMEOUT,
            pool=settings.CONNECT_TIMEOUT,
        )
        self.client = httpx.AsyncClient(timeout=timeouts, limits=limits)

        # Store circuit breakers for each target host
        self.breakers: dict[str, CircuitBreaker] = {}

    async def close(self):
        await self.client.aclose()

    def _get_breaker(self, target_url: str) -> CircuitBreaker:
        if target_url not in self.breakers:
            self.breakers[target_url] = CircuitBreaker(name=target_url)
        return self.breakers[target_url]

    async def forward(
        self,
        request: Request,
        target_url: str,
        path: str,
        service_token: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> StreamingResponse:
        """
        Forward the incoming request to the target service using Circuit Breaker and Streaming.
        """
        breaker = self._get_breaker(target_url)

        async def _do_request() -> httpx.Response:
            url = f"{target_url}/{path}"

            # Prepare headers
            headers = dict(request.headers)
            headers.pop("host", None)
            headers.pop("content-length", None)

            if service_token:
                headers["X-Service-Token"] = service_token
            correlation_id = headers.get("X-Correlation-ID") or getattr(
                request.state, "correlation_id", None
            )
            if correlation_id:
                headers["X-Correlation-ID"] = str(correlation_id)
            if extra_headers:
                headers.update(extra_headers)

            # Retry Logic
            retries = settings.MAX_RETRIES
            # Only retry safe/idempotent methods to avoid data corruption or stream exhaustion
            can_retry = request.method in ["GET", "HEAD", "OPTIONS"]

            for attempt in range(retries + 1):
                try:
                    # Build request with streaming content
                    # Note: request.stream() consumes the receive channel.
                    # It cannot be reused if it was consumed in a previous failed attempt.
                    # Hence we strictly limit retries.

                    req = self.client.build_request(
                        method=request.method,
                        url=url,
                        headers=headers,
                        content=request.stream(),
                        params=request.query_params,
                    )

                    # Send request with stream=True to get headers back immediately
                    return await self.client.send(req, stream=True)

                except (
                    httpx.ConnectError,
                    httpx.ConnectTimeout,
                    httpx.ReadTimeout,
                ) as exc:
                    if can_retry and attempt < retries:
                        sleep_time = settings.RETRY_BACKOFF_FACTOR * (2**attempt)
                        logger.warning(
                            f"Retry {attempt + 1}/{retries} for {url} ({request.method}) due to {exc}. Sleeping {sleep_time}s"
                        )
                        await asyncio.sleep(sleep_time)
                    else:
                        logger.error(
                            f"Request failed for {url}: {exc} (Retries exhausted or unsafe)"
                        )
                        raise exc
                except Exception as exc:
                    # Other errors (e.g. WriteError) - do not retry blindly
                    logger.error(f"Proxy request error to {url}: {exc}")
                    raise exc

            # This point is logically unreachable due to the loop structure (attempt > retries -> else -> raise)
            # But to satisfy static analysis (RET503)
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Proxy retry loop exhausted without result.",
            )

        try:
            # Execute the request logic wrapped in Circuit Breaker
            upstream_response = await breaker.execute(_do_request)

            # Create an async generator to stream the response content
            async def response_iterator():
                try:
                    async for chunk in upstream_response.aiter_bytes():
                        yield chunk
                except Exception as e:
                    logger.error(f"Error streaming response from {target_url}: {e}")
                finally:
                    await upstream_response.aclose()

            return StreamingResponse(
                response_iterator(),
                status_code=upstream_response.status_code,
                headers=dict(upstream_response.headers),
                media_type=upstream_response.headers.get("content-type"),
            )

        except HTTPException as e:
            raise e
        except Exception as exc:
            # Map generic exception to HTTP 502/503
            logger.error(f"Final proxy error to {target_url}: {exc}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Error communicating with upstream service: {exc!s}",
            ) from exc
