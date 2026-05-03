import asyncio
import contextlib
import logging
import threading
from collections import deque
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from fastapi import Request

from app.services.boundaries.schemas import MetricType as SchemaMetricType
from app.services.boundaries.schemas import TelemetryData
from app.telemetry.aggregator import TelemetryAggregator

if TYPE_CHECKING:
    pass
from app.telemetry.analyzer import TelemetryAnalyzer
from app.telemetry.metrics import MetricRecord, MetricsManager
from app.telemetry.models import (
    CorrelatedLog,
    MetricSample,
    MetricType,
    TraceContext,
    UnifiedSpan,
    UnifiedTrace,
)
from app.telemetry.structured_logging import LoggingManager, LogRecord
from app.telemetry.tracing import TracingManager

logger = logging.getLogger(__name__)


class UnifiedObservabilityService:
    """
    خدمة المراقبة الموحدة.
    تعمل كواجهة (Facade) مركزية لإدارة التتبع، القياسات، والسجلات، بالإضافة إلى التحليل والتجميع.

    Unified Observability Service.
    Acts as a central Facade for managing tracing, metrics, and logs, as well as analysis and aggregation.
    """

    def __init__(
        self,
        service_name: str = "cogniforge",
        sample_rate: float = 1.0,
        sla_target_ms: float = 100.0,
    ):
        # 1. المكونات الأساسية (Core Managers)
        self.tracing = TracingManager(service_name, sample_rate, sla_target_ms)
        self.metrics = MetricsManager()
        self.logging = LoggingManager()

        self.service_name = service_name

        # 2. المكونات الذكية (Smart Components)
        self.analyzer = TelemetryAnalyzer(
            self.tracing, self.metrics, latency_p99_target=sla_target_ms
        )
        self.aggregator = TelemetryAggregator(
            self.tracing, self.metrics, self.logging, service_name
        )

        # قفل للتوافق مع الواجهة القديمة
        self.lock = threading.RLock()

        # Microservice Sync
        self._sync_task: asyncio.Task | None = None
        self._stop_event: asyncio.Event | None = None

        from app.services.boundaries.observability_client import ObservabilityServiceClient

        self.client = ObservabilityServiceClient()

    async def start_background_sync(self) -> None:
        """Start the background metrics synchronization task."""
        if self._sync_task is not None and not self._sync_task.done():
            self._sync_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._sync_task
            self._sync_task = None
        self._stop_event = asyncio.Event()
        self._sync_task = asyncio.create_task(self._background_sync_loop())
        logger.info("Unified Observability background sync started.")

    async def stop_background_sync(self) -> None:
        """Stop the background metrics synchronization task."""
        if self._sync_task:
            if self._stop_event is not None:
                self._stop_event.set()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sync_task
            self._sync_task = None
            await self.client.close()
            logger.info("Unified Observability background sync stopped.")

    async def _background_sync_loop(self) -> None:
        """Periodic loop to flush metrics to the microservice."""
        while self._stop_event is None or not self._stop_event.is_set():
            try:
                await self._flush_metrics_to_microservice()
            except Exception as e:
                logger.error(f"Error in background sync loop: {e}")

            if self._stop_event is None:
                await asyncio.sleep(5.0)
                continue
            # Sleep with check for stop event
            try:
                await asyncio.wait_for(self._stop_event.wait(), timeout=5.0)
            except TimeoutError:
                continue

    async def _flush_metrics_to_microservice(self) -> None:
        """Drain the metrics buffer and send to microservice."""
        # Drain buffer under lock (copy and clear)
        samples_to_send = []
        with self.metrics.lock:
            while self.metrics.metrics_buffer:
                samples_to_send.append(self.metrics.metrics_buffer.popleft())

        if not samples_to_send:
            return

        for sample in samples_to_send:
            # Skip if critical fields are missing
            if not sample.name:
                continue

            # Map MetricType (Monolith) to SchemaMetricType (Boundary/Microservice)
            metric_type_val = SchemaMetricType.LATENCY
            if isinstance(sample.metric_type, MetricType):
                with contextlib.suppress(ValueError):
                    metric_type_val = SchemaMetricType(sample.metric_type.value)
            elif isinstance(sample.metric_type, str):
                with contextlib.suppress(ValueError):
                    metric_type_val = SchemaMetricType(sample.metric_type)

            data = TelemetryData(
                metric_id=sample.name,
                service_name=self.service_name,
                metric_type=metric_type_val,
                value=sample.value,
                timestamp=datetime.fromtimestamp(sample.timestamp, UTC),
                labels=sample.labels,
                unit="",  # Optional
            )
            await self.client.collect_telemetry(data)

    # --- Tracing Delegates ---

    @property
    def active_traces(self) -> dict[str, UnifiedTrace]:
        """التتبعات النشطة حالياً"""
        return self.tracing.active_traces

    @property
    def active_spans(self) -> dict[str, UnifiedSpan]:
        """النطاقات النشطة حالياً"""
        return self.tracing.active_spans

    @property
    def completed_traces(self) -> deque[UnifiedTrace]:
        """سجل التتبعات المكتملة"""
        return self.tracing.completed_traces

    def start_trace(
        self,
        operation_name: str,
        parent_context: TraceContext | None = None,
        tags: dict[str, object] | None = None,
        request: Request | None = None,
    ) -> TraceContext:
        """بدء تتبع جديد"""
        return self.tracing.start_trace(operation_name, parent_context, tags, request)

    def end_span(
        self,
        span_id: str,
        status: str = "OK",
        error_message: str | None = None,
        metrics: dict[str, float] | None = None,
    ) -> None:
        """إنهاء نطاق تتبع"""
        self.tracing.end_span(span_id, status, error_message, metrics)
        # منطق الارتباط (Correlation) يتم الآن ضمنياً عبر المعرفات المشتركة
        # لا حاجة لاستدعاء _correlate_trace يدوياً هنا

    def add_span_event(
        self, span_id: str, event_name: str, attributes: dict[str, object] | None = None
    ) -> None:
        """إضافة حدث إلى نطاق تتبع"""
        self.tracing.add_span_event(span_id, event_name, attributes)

    # --- Metrics Delegates ---

    @property
    def metrics_buffer(self) -> deque[MetricSample]:
        return self.metrics.metrics_buffer

    @property
    def counters(self) -> dict[str, float]:
        return self.metrics.counters

    @property
    def gauges(self) -> dict[str, float]:
        return self.metrics.gauges

    @property
    def histograms(self) -> dict[str, deque[float]]:
        return self.metrics.histograms

    @property
    def trace_metrics(self) -> dict[str, list[MetricSample]]:
        return self.metrics.trace_metrics

    def record_metric(
        self,
        name: str,
        value: float,
        labels: dict[str, str] | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> None:
        """تسجيل مقياس جديد"""
        self.metrics.record_metric(
            MetricRecord(
                name=name,
                value=value,
                labels=labels or {},
                trace_id=trace_id,
                span_id=span_id,
            )
        )

    def increment_counter(
        self, name: str, amount: float = 1.0, labels: dict[str, str] | None = None
    ) -> None:
        """زيادة عداد"""
        self.metrics.increment_counter(name, amount, labels)

    def set_gauge(self, name: str, value: float, labels: dict[str, str] | None = None) -> None:
        """تعيين قيمة مقياس ثابت"""
        self.metrics.set_gauge(name, value, labels)

    def get_percentiles(self, metric_name: str) -> dict[str, float]:
        """حساب النسب المئوية لمقياس"""
        return self.metrics.get_percentiles(metric_name)

    def export_prometheus_metrics(self) -> str:
        """تصدير المقاييس بتنسيق Prometheus"""
        return self.metrics.export_prometheus_metrics()

    # --- Logging Delegates ---

    @property
    def logs_buffer(self) -> deque[CorrelatedLog]:
        return self.logging.logs_buffer

    @property
    def trace_logs(self) -> dict[str, list[CorrelatedLog]]:
        return self.logging.trace_logs

    def log(
        self,
        level: str,
        message: str,
        context: dict[str, object] | None = None,
        exception: Exception | None = None,
        trace_id: str | None = None,
        span_id: str | None = None,
    ) -> None:
        """تسجيل رسالة سجل مترابطة"""
        self.logging.log(
            LogRecord(
                level=level,
                message=message,
                context=context or {},
                exception=exception,
                trace_id=trace_id,
                span_id=span_id,
            )
        )

    # --- Aggregation Delegates (via Aggregator) ---

    def get_trace_with_correlation(self, trace_id: str) -> dict[str, object] | None:
        """استرجاع تتبع كامل مع البيانات المترابطة"""
        return self.aggregator.get_trace_with_correlation(trace_id)

    def find_traces_by_criteria(
        self,
        min_duration_ms: float | None = None,
        has_errors: bool | None = None,
        operation_name: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, object]]:
        """البحث عن التتبعات"""
        return self.aggregator.find_traces_by_criteria(
            min_duration_ms, has_errors, operation_name, limit
        )

    def get_service_dependencies(self) -> dict[str, list[str]]:
        """استنتاج اعتماديات الخدمة"""
        return self.aggregator.get_service_dependencies()

    # --- Analysis Delegates (via Analyzer) ---

    def get_golden_signals(self, time_window_seconds: int = 300) -> dict[str, object]:
        """حساب الإشارات الذهبية"""
        return self.analyzer.get_golden_signals(time_window_seconds)

    def detect_anomalies(self) -> list[dict[str, object]]:
        """اكتشاف الشذوذ"""
        return self.analyzer.detect_anomalies()

    # --- Legacy/Support Methods ---

    def _generate_trace_id(self) -> str:
        return self.tracing._generate_trace_id()

    def _generate_span_id(self) -> str:
        return self.tracing._generate_span_id()

    @property
    def anomaly_alerts(self) -> deque:
        """للتيوافق مع الكود القديم الذي يصل للخاصية مباشرة"""
        return self.analyzer.anomaly_alerts

    def get_statistics(self) -> dict[str, object]:
        """إحصائيات مجمعة للنظام"""
        with self.lock, self.tracing.lock, self.metrics.lock, self.logging.lock:
            return {
                "anomalies_detected": self.analyzer.anomalies_detected_count,
                **self.tracing.stats,
                **self.metrics.stats,
                **self.logging.stats,
                "active_traces": len(self.tracing.active_traces),
                "active_spans": len(self.tracing.active_spans),
                "completed_traces": len(self.tracing.completed_traces),
                "metrics_buffer_size": len(self.metrics.metrics_buffer),
                "logs_buffer_size": len(self.logging.logs_buffer),
                "anomaly_alerts": len(self.analyzer.anomaly_alerts),
            }


# Singleton Instance Management
_unified_observability: UnifiedObservabilityService | None = None
_obs_lock = threading.Lock()


def get_unified_observability() -> UnifiedObservabilityService:
    global _unified_observability
    if _unified_observability is None:
        with _obs_lock:
            if _unified_observability is None:
                _unified_observability = UnifiedObservabilityService()
    return _unified_observability
