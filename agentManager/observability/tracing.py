"""OpenTelemetry tracing helpers with no-op fallback.

Provides ``trace_workflow``, ``trace_task``, and ``create_span`` context
managers that are safe to call even when the OpenTelemetry SDK is not
installed or the exporter is unreachable.  When OTel is unavailable every
call degrades to a no-op so business logic is never affected.
"""

from __future__ import annotations

import logging
import os
from contextlib import contextmanager
from typing import Any, Dict, Iterator, Optional

logger = logging.getLogger(__name__)

_OTEL_ENABLED: Optional[bool] = None
_tracer: Any = None


def _is_otel_enabled() -> bool:
    global _OTEL_ENABLED, _tracer
    if _OTEL_ENABLED is not None:
        return _OTEL_ENABLED

    enabled = os.getenv("OTEL_TRACING_ENABLED", "false").lower() in ("true", "1", "yes")
    if not enabled:
        _OTEL_ENABLED = False
        return False

    try:
        from opentelemetry import trace

        provider = trace.get_tracer_provider()
        _tracer = trace.get_tracer("agentmanager", "0.1.0")
        _OTEL_ENABLED = True
    except Exception:
        logger.debug("OpenTelemetry SDK not available; tracing disabled")
        _OTEL_ENABLED = False

    return _OTEL_ENABLED


def setup_tracing() -> None:
    """Initialise the OTel tracer provider from environment configuration.

    Safe to call multiple times.  When ``OTEL_TRACING_ENABLED`` is not set
    or the SDK is not installed this is a no-op.
    """
    global _OTEL_ENABLED, _tracer

    enabled = os.getenv("OTEL_TRACING_ENABLED", "false").lower() in ("true", "1", "yes")
    if not enabled:
        _OTEL_ENABLED = False
        return

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource

        endpoint = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        resource = Resource.create(
            {"service.name": "agentmanager", "service.version": "0.1.0"}
        )
        provider = TracerProvider(resource=resource)

        if endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                    OTLPSpanExporter,
                )

                exporter = OTLPSpanExporter(endpoint=endpoint, insecure=True)
                provider.add_span_processor(BatchSpanProcessor(exporter))
            except Exception:
                logger.debug("OTLP exporter not available; spans will not be exported")

        trace.set_tracer_provider(provider)
        _tracer = trace.get_tracer("agentmanager", "0.1.0")
        _OTEL_ENABLED = True
        logger.info("OpenTelemetry tracing enabled, endpoint=%s", endpoint or "(none)")
    except Exception:
        logger.debug("OpenTelemetry SDK not available; tracing disabled")
        _OTEL_ENABLED = False


@contextmanager
def create_span(
    name: str,
    attributes: Optional[Dict[str, Any]] = None,
) -> Iterator[Any]:
    """Create a generic OTel span.  No-op when tracing is disabled."""
    if not _is_otel_enabled() or _tracer is None:
        yield None
        return

    try:
        from opentelemetry import trace

        with _tracer.start_as_current_span(name) as span:
            if attributes and span.is_recording():
                for key, value in attributes.items():
                    span.set_attribute(key, value)
            yield span
    except Exception:
        yield None


@contextmanager
def trace_workflow(workflow_id: str) -> Iterator[Any]:
    """Context manager that creates a workflow-level span."""
    with create_span(
        "workflow.execute",
        {"workflow.id": workflow_id},
    ) as span:
        yield span


@contextmanager
def trace_task(task_id: str, task_type: str = "") -> Iterator[Any]:
    """Context manager that creates a task-level span."""
    attrs: Dict[str, Any] = {"task.id": task_id}
    if task_type:
        attrs["task.type"] = task_type
    with create_span("task.execute", attrs) as span:
        yield span
