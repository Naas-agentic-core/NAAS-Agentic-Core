import logging
import time

try:
    from opentelemetry import trace
except ModuleNotFoundError:

    class _NoOpSpanContext:
        trace_id = 0

    class _NoOpSpan:
        def get_span_context(self) -> _NoOpSpanContext:
            return _NoOpSpanContext()

        def is_recording(self) -> bool:
            return False

        def add_event(self, *_: object, **__: object) -> None:
            return None

    class _NoOpTrace:
        @staticmethod
        def get_tracer(_: str) -> object:
            return object()

        @staticmethod
        def get_current_span() -> _NoOpSpan:
            return _NoOpSpan()

    trace = _NoOpTrace()  # type: ignore[assignment]

logger = logging.getLogger("graph-telemetry")
tracer = trace.get_tracer(__name__)


def emit_telemetry(
    node_name: str,
    start_time: float,
    state: dict,
    error: Exception | None = None,
    tool_invoked: bool = False,
    retrieval_source: str | None = None,
    confidence: float | None = None,
    trust_score: float | None = None,
    tokens_used: int = 0,
):
    execution_ms = (time.time() - start_time) * 1000
    current_span = trace.get_current_span()
    trace_id = (
        format(current_span.get_span_context().trace_id, "032x")
        if current_span.is_recording()
        else "unknown"
    )

    telemetry_data = {
        "trace_id": trace_id,
        "node_name": node_name,
        "execution_ms": execution_ms,
        "trust_score": trust_score,
        "tool_invoked": tool_invoked,
        "retrieval_source": retrieval_source,
        "confidence": confidence,
        "tokens_used": tokens_used,
        "error": str(error) if error else None,
    }

    # Log via standard logging (caught by configured fluentd/opentelemetry agents in real app)
    logger.info(f"TELEMETRY: {telemetry_data}")

    # Add events to current span
    if current_span.is_recording():
        current_span.add_event("node_execution", attributes=telemetry_data)
