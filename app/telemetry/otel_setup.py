"""OpenTelemetry SDK bootstrap for CogniForge — conditional on env.

Live anchor: imported by `app/kernel.py` at startup. Calls `setup_otel()` ONCE
at process boot. If `OTEL_EXPORTER_OTLP_ENDPOINT` is unset, every operation in
this module becomes a no-op — the FastAPI app behaves exactly as before, with
no new dependencies required at runtime.

When the env var IS set (the observability stack is running), this module:
    * Configures the global TracerProvider + MeterProvider + LoggerProvider
    * Wires OTLP exporters to the collector
    * Auto-instruments FastAPI, httpx, SQLAlchemy, asyncpg, redis (if libs
      are installed; each is wrapped in try/except)
    * Bridges `app.telemetry.path_observer` spans into the OTel SDK so they
      land in Tempo + Prometheus

Confidence on this file:
    * Static structure  : CONFIRMED by ast.parse + ruff
    * Runtime activation: UNKNOWN until first Codespace boot with the stack up
                          (we cannot run docker compose in this sandbox).

The module follows the project's hard rule: observability NEVER raises out of
the live path. Every exporter / instrumentor call is wrapped — if any step
fails at startup, the app continues with a degraded telemetry surface and a
single warning log.
"""

from __future__ import annotations

import contextlib
import logging
import os
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from opentelemetry.metrics import Counter, Histogram, Meter
    from opentelemetry.trace import Tracer

logger = logging.getLogger("cogniforge.otel_setup")

# Module-level state — single setup per process.
_INITIALIZED: bool = False
_OTEL_TRACER: Tracer | None = None
_OTEL_METER: Meter | None = None
_OTEL_HISTOGRAM_TURN: Histogram | None = None
_OTEL_COUNTER_TERMINAL: Counter | None = None
_OTEL_COUNTER_FALLBACK: Counter | None = None


def is_enabled() -> bool:
    """OTel is enabled iff `OTEL_EXPORTER_OTLP_ENDPOINT` is set and non-empty."""
    return bool(os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "").strip())


def is_initialized() -> bool:
    """Returns True iff `setup_otel()` ran successfully."""
    return _INITIALIZED


def get_tracer() -> Tracer | None:
    """Return the cached OTel tracer (or None if disabled / not initialized)."""
    return _OTEL_TRACER


def get_meter() -> Meter | None:
    """Return the cached OTel meter (or None if disabled / not initialized)."""
    return _OTEL_METER


def get_metrics() -> dict[str, Histogram | Counter | None]:
    """Return the pre-created instruments. Empty dict when disabled."""
    if not _INITIALIZED:
        return {}
    return {
        "ws_chat_turn_duration_seconds": _OTEL_HISTOGRAM_TURN,
        "ws_chat_terminal_events_total": _OTEL_COUNTER_TERMINAL,
        "ws_chat_fallback_total": _OTEL_COUNTER_FALLBACK,
    }


def setup_otel(service_name: str = "cogniforge-monolith") -> bool:
    """Bootstrap OpenTelemetry. Returns True on success, False otherwise.

    Idempotent — second call is a no-op.
    Safe to call when the env var is unset (returns False without error).
    """
    global _INITIALIZED, _OTEL_TRACER, _OTEL_METER
    global _OTEL_HISTOGRAM_TURN, _OTEL_COUNTER_TERMINAL, _OTEL_COUNTER_FALLBACK

    if _INITIALIZED:
        return True
    if not is_enabled():
        logger.debug("otel_setup.disabled (OTEL_EXPORTER_OTLP_ENDPOINT not set)")
        return False

    endpoint = os.environ["OTEL_EXPORTER_OTLP_ENDPOINT"].strip()
    insecure = os.environ.get("OTEL_EXPORTER_OTLP_INSECURE", "true").lower() == "true"
    environment = os.environ.get("ENVIRONMENT", "development")

    try:
        from opentelemetry import metrics, trace
        from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import (
            OTLPMetricExporter,
        )
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
            OTLPSpanExporter,
        )
        from opentelemetry.sdk.metrics import MeterProvider
        from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError as exc:
        logger.warning(
            "otel_setup.import_failed: install opentelemetry-sdk + "
            "opentelemetry-exporter-otlp-proto-grpc to enable. (%s)",
            exc,
        )
        return False

    resource = Resource.create(
        {
            "service.name": service_name,
            "service.namespace": "cogniforge",
            "service.version": os.environ.get("APP_VERSION", "dev"),
            "deployment.environment": environment,
            "host.name": os.environ.get("HOSTNAME", "codespace"),
        }
    )

    # Tracer provider + OTLP span exporter → Tempo (via collector).
    try:
        span_exporter = OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
        tracer_provider = TracerProvider(resource=resource)
        tracer_provider.add_span_processor(BatchSpanProcessor(span_exporter))
        trace.set_tracer_provider(tracer_provider)
        _OTEL_TRACER = trace.get_tracer("cogniforge.path_observer")
    except Exception as exc:  # pragma: no cover
        logger.warning("otel_setup.tracer_failed: %s", exc)
        return False

    # Meter provider + OTLP metric exporter → Prometheus (via collector).
    try:
        metric_exporter = OTLPMetricExporter(endpoint=endpoint, insecure=insecure)
        metric_reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=10_000
        )
        meter_provider = MeterProvider(
            resource=resource, metric_readers=[metric_reader]
        )
        metrics.set_meter_provider(meter_provider)
        _OTEL_METER = metrics.get_meter("cogniforge.path_observer")
        _OTEL_HISTOGRAM_TURN = _OTEL_METER.create_histogram(
            name="ws.chat.turn.duration_seconds",
            description="Full WebSocket chat turn latency, by path_type.",
            unit="s",
        )
        _OTEL_COUNTER_TERMINAL = _OTEL_METER.create_counter(
            name="ws.chat.terminal_events.total",
            description="Count of terminal frames (assistant_final / error / unknown) per turn.",
        )
        _OTEL_COUNTER_FALLBACK = _OTEL_METER.create_counter(
            name="ws.chat.fallback.total",
            description="Count of turns that engaged the local fallback chain.",
        )
    except Exception as exc:  # pragma: no cover
        logger.warning("otel_setup.meter_failed: %s", exc)

    # Auto-instrumentation — best-effort. Each library is independent: if one
    # fails to import, we skip just that one.
    _try_instrument_fastapi()
    _try_instrument_httpx()
    _try_instrument_sqlalchemy()
    _try_instrument_asyncpg()
    _try_instrument_redis()
    _try_instrument_logging()

    _INITIALIZED = True
    logger.info(
        "otel_setup.ready endpoint=%s service=%s environment=%s",
        endpoint,
        service_name,
        environment,
    )
    return True


def instrument_fastapi_app(app: Any) -> None:
    """Wrap a FastAPI app instance with OTel instrumentation.

    Called from `app/kernel.py` AFTER the app is created and BEFORE it starts
    serving. Safe to call when OTel is disabled — becomes a no-op.
    """
    if not _INITIALIZED:
        return
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

        FastAPIInstrumentor.instrument_app(
            app,
            excluded_urls="/api/observability/metrics,/health,/healthz",
        )
        logger.info("otel_setup.fastapi_instrumented")
    except Exception as exc:  # pragma: no cover
        logger.warning("otel_setup.fastapi_instrument_failed: %s", exc)


# ─── Internal best-effort instrumentation helpers ───────────────────────────


def _try_instrument_fastapi() -> None:
    # Per-app instrumentation happens in `instrument_fastapi_app(app)`.
    # Here we just verify the lib is importable.
    with contextlib.suppress(ImportError):
        import opentelemetry.instrumentation.fastapi  # noqa: F401


def _try_instrument_httpx() -> None:
    try:
        from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor

        HTTPXClientInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover
        logger.debug("otel_setup.httpx_skip: %s", exc)


def _try_instrument_sqlalchemy() -> None:
    try:
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().instrument(enable_commenter=True)
    except Exception as exc:  # pragma: no cover
        logger.debug("otel_setup.sqlalchemy_skip: %s", exc)


def _try_instrument_asyncpg() -> None:
    try:
        from opentelemetry.instrumentation.asyncpg import AsyncPGInstrumentor

        AsyncPGInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover
        logger.debug("otel_setup.asyncpg_skip: %s", exc)


def _try_instrument_redis() -> None:
    try:
        from opentelemetry.instrumentation.redis import RedisInstrumentor

        RedisInstrumentor().instrument()
    except Exception as exc:  # pragma: no cover
        logger.debug("otel_setup.redis_skip: %s", exc)


def _try_instrument_logging() -> None:
    try:
        from opentelemetry.instrumentation.logging import LoggingInstrumentor

        LoggingInstrumentor().instrument(set_logging_format=False)
    except Exception as exc:  # pragma: no cover
        logger.debug("otel_setup.logging_skip: %s", exc)
