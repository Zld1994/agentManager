"""Optional tracing hooks with no-op local defaults."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_tracing_enabled = False


@dataclass
class NoopSpan:
    """In-memory span shape used when OpenTelemetry is disabled."""

    name: str
    attributes: dict[str, Any] = field(default_factory=dict)
    error: str | None = None

    def set_attribute(self, key: str, value: Any) -> None:
        """Set a span attribute."""
        self.attributes[key] = value


class TraceOperation:
    """Context manager for one traced operation."""

    def __init__(self, name: str, **attributes: Any) -> None:
        self.span = NoopSpan(name=name, attributes=dict(attributes))

    def __enter__(self) -> NoopSpan:
        return self.span

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if exc is not None:
            self.span.error = str(exc)
        return False


def configure_tracing(settings: dict[str, Any]) -> None:
    """Configure tracing. OpenTelemetry export is opt-in."""
    global _tracing_enabled
    _tracing_enabled = bool(settings.get("otel_tracing_enabled", False))


def is_tracing_enabled() -> bool:
    """Return whether tracing is enabled."""
    return _tracing_enabled


def trace_operation(name: str, **attributes: Any) -> TraceOperation:
    """Create a trace operation context manager."""
    return TraceOperation(name, **attributes)
