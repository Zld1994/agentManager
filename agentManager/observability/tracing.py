"""OpenTelemetry tracing integration (opt-in, disabled by default).

When OTEL_TRACING_ENABLED=true, initialises an OTLP exporter and provides
context-manager / decorator helpers for creating spans.
When disabled, all helpers are no-ops so callers don't need guards.
"""

from __future__ import annotations

import os
import logging
from contextlib import contextmanager
from typing import Any, Generator, Optional

logger = logging.getLogger(__name__)

_tracer: Any = None

_VALID_PROTOCOLS = {"grpc", "http/protobuf"}


def setup_tracing(
    enabled: Optional[bool] = None,
    service_name: Optional[str] = None,
    endpoint: Optional[str] = None,
) -> bool:
    """Initialise OpenTelemetry if enabled.

    Returns True when tracing is active.
    Reads defaults from environment:
      - OTEL_TRACING_ENABLED (default false)
      - OTEL_SERVICE_NAME  (default "agentManager")
      - OTEL_EXPORTER_OTLP_ENDPOINT (default "http://localhost:4317")
      - OTEL_EXPORTER_OTLP_PROTOCOL (default "grpc", supports "http/protobuf")
      - OTEL_TRACING_SAMPLE_RATE (default 1.0, 0.0 to 1.0)
    """
    global _tracer

    if enabled is None:
        enabled = os.getenv("OTEL_TRACING_ENABLED", "false").lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.debug("OpenTelemetry tracing is disabled")
        return False

    service_name = service_name or os.getenv("OTEL_SERVICE_NAME", "agentManager")
    endpoint = endpoint or os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:4317")
    protocol = os.getenv("OTEL_EXPORTER_OTLP_PROTOCOL", "grpc")

    if protocol not in _VALID_PROTOCOLS:
        logger.warning(
            "Invalid OTEL_EXPORTER_OTLP_PROTOCOL=%r (must be one of %s). "
            "Falling back to 'grpc'.",
            protocol,
            sorted(_VALID_PROTOCOLS),
        )
        protocol = "grpc"

    sample_rate_raw = os.getenv("OTEL_TRACING_SAMPLE_RATE", "1.0")
    try:
        sample_rate = float(sample_rate_raw)
    except ValueError:
        logger.warning(
            "Invalid OTEL_TRACING_SAMPLE_RATE=%r (not a number). " "Falling back to 1.0.",
            sample_rate_raw,
        )
        sample_rate = 1.0

    if sample_rate < 0.0 or sample_rate > 1.0:
        logger.warning(
            "OTEL_TRACING_SAMPLE_RATE=%.4f is outside [0, 1]. Clamping to range.",
            sample_rate,
        )
        sample_rate = max(0.0, min(1.0, sample_rate))

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import TraceIdRatioBased
        from opentelemetry.sdk.resources import Resource

        sampler = TraceIdRatioBased(sample_rate)

        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource, sampler=sampler)

        if protocol == "http/protobuf":
            from opentelemetry.exporter.otlp.proto.http.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint)
        else:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)

        provider.add_span_processor(BatchSpanProcessor(exporter))
        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer(service_name)
        logger.info(
            "OpenTelemetry tracing enabled: service=%s endpoint=%s protocol=%s sample_rate=%.2f",
            service_name,
            endpoint,
            protocol,
            sample_rate,
        )
        return True
    except ImportError:
        logger.warning(
            "OpenTelemetry packages not installed; tracing disabled. "
            "Install with: pip install opentelemetry-api opentelemetry-sdk "
            "opentelemetry-exporter-otlp"
        )
        return False
    except Exception:
        logger.exception("Failed to initialise OpenTelemetry tracing")
        return False


# ── No-op span for when tracing is off ──────────────────────────────────────


class _NoOpSpan:
    """Minimal no-op span that supports context-manager, set_attribute, and end."""

    def set_attribute(self, key: str, value: Any) -> None:
        pass

    def set_status(self, status: Any) -> None:
        pass

    def record_exception(self, exc: BaseException) -> None:
        pass

    def end(self) -> None:
        pass

    def __enter__(self) -> "_NoOpSpan":
        return self

    def __exit__(self, *args: Any) -> None:
        pass


@contextmanager
def create_span(
    name: str, attributes: Optional[dict[str, Any]] = None
) -> Generator[Any, None, None]:
    """Create a tracing span (no-op when tracing is disabled)."""
    if _tracer is None:
        yield _NoOpSpan()
        return

    with _tracer.start_as_current_span(name) as span:
        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)
        try:
            yield span
        except Exception as exc:
            span.record_exception(exc)
            try:
                from opentelemetry.trace import Status, StatusCode

                span.set_status(Status(StatusCode.ERROR, str(exc)))
            except ImportError:
                pass
            raise


@contextmanager
def trace_workflow(workflow_id: str) -> Generator[Any, None, None]:
    """Wrap an entire workflow run in a top-level span."""
    with create_span(
        "workflow.run",
        {"workflow.id": workflow_id},
    ) as span:
        yield span


@contextmanager
def trace_task(task_id: str, task_type: str = "unknown") -> Generator[Any, None, None]:
    """Wrap a single task execution in a span."""
    with create_span(
        "task.execute",
        {"task.id": task_id, "task.type": task_type},
    ) as span:
        yield span


def get_current_span() -> Any:
    """Return the currently active span, or a no-op span."""
    if _tracer is None:
        return _NoOpSpan()
    try:
        from opentelemetry import trace

        return trace.get_current_span()
    except ImportError:
        return _NoOpSpan()


# Compatibility alias: context-manager wrapper for create_span
@contextmanager
def trace_operation(name: str, **attributes: Any) -> Generator[Any, None, None]:
    """Compatibility wrapper: create a span from name + keyword arguments.

    Use as a context manager::

        with trace_operation("my.op", key="val") as span:
            ...
    """
    with create_span(name, attributes=attributes if attributes else None) as span:
        yield span
