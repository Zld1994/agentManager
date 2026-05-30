"""Structured logging with JSON output and request/workflow correlation IDs.

Uses Python stdlib logging with a custom JSON formatter.
Correlation IDs are stored in contextvars for async-safe propagation.
"""

from __future__ import annotations

import json
import logging
import os
import sys
import uuid
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import Any, Optional


# ── Correlation context variables ────────────────────────────────────────────

_request_id_var: ContextVar[Optional[str]] = ContextVar("request_id", default=None)
_workflow_id_var: ContextVar[Optional[str]] = ContextVar("workflow_id", default=None)


def get_request_id() -> Optional[str]:
    return _request_id_var.get()


# Compatibility aliases
get_correlation_id = get_request_id


def set_correlation_id(value: Optional[str]) -> None:
    """Set the correlation (request) ID.

    Passing None explicitly clears the request ID, equivalent to calling
    clear_correlation_id(). This differs from set_request_context() where
    None means "don't change this value".
    """
    if value is None:
        _request_id_var.set(None)
    else:
        _request_id_var.set(value)


def clear_correlation_id() -> None:
    clear_request_context()


def get_workflow_id() -> Optional[str]:
    return _workflow_id_var.get()


def set_request_context(
    request_id: Optional[str] = None,
    workflow_id: Optional[str] = None,
) -> None:
    """Set correlation IDs for the current async context."""
    if request_id is not None:
        _request_id_var.set(request_id)
    if workflow_id is not None:
        _workflow_id_var.set(workflow_id)


def clear_request_context() -> None:
    _request_id_var.set(None)
    _workflow_id_var.set(None)


def new_request_id() -> str:
    return uuid.uuid4().hex


# ── JSON log record factory ──────────────────────────────────────────────────

_original_factory = logging.getLogRecordFactory()


def _correlated_factory(*args: Any, **kwargs: Any) -> logging.LogRecord:
    record = _original_factory(*args, **kwargs)
    record.request_id = _request_id_var.get() or ""  # type: ignore[attr-defined]
    record.workflow_id = _workflow_id_var.get() or ""  # type: ignore[attr-defined]
    return record


# ── JSON Formatter ───────────────────────────────────────────────────────────

class _JSONEncoder(json.JSONEncoder):
    def default(self, o: Any) -> Any:
        if isinstance(o, datetime):
            return o.isoformat()
        if isinstance(o, BaseException):
            return repr(o)
        return super().default(o)


class JSONFormatter(logging.Formatter):
    """Emit each log record as a single JSON line."""

    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        # Correlation
        req_id = getattr(record, "request_id", "")
        wf_id = getattr(record, "workflow_id", "")
        if req_id:
            payload["request_id"] = req_id
        if wf_id:
            payload["workflow_id"] = wf_id

        # Source location
        payload["module"] = record.module
        payload["func"] = record.funcName
        payload["line"] = record.lineno

        # Exception info
        if record.exc_info and record.exc_info[0] is not None:
            payload["exception"] = self.formatException(record.exc_info)

        # Extra fields (skip internal LogRecord attrs)
        _skip = {
            "name", "msg", "args", "created", "relativeCreated",
            "exc_info", "exc_text", "stack_info", "lineno", "funcName",
            "filename", "module", "pathname", "thread", "threadName",
            "process", "processName", "levelname", "levelno", "message",
            "msecs", "taskName", "request_id", "workflow_id",
        }
        for key, val in record.__dict__.items():
            if key not in _skip and not key.startswith("_"):
                payload[key] = val

        return json.dumps(payload, cls=_JSONEncoder, ensure_ascii=False)


# ── StructuredLogger wrapper ────────────────────────────────────────────────

class StructuredLogger:
    """Thin convenience wrapper around a stdlib logger."""

    def __init__(self, name: str) -> None:
        self._logger = logging.getLogger(name)

    def bind(self, **extra: Any) -> logging.LoggerAdapter:
        return logging.LoggerAdapter(self._logger, extra)

    @property
    def native(self) -> logging.Logger:
        return self._logger


# ── Setup entry point ────────────────────────────────────────────────────────

def setup_logging(
    level: Optional[str] = None,
    json_output: Optional[bool] = None,
) -> None:
    """Configure root logger with optional JSON formatter.

    Reads defaults from environment when parameters are not given:
      - LOG_LEVEL (default INFO)
      - LOG_JSON  (default True)
    """
    if level is None:
        level = os.getenv("LOG_LEVEL", "INFO").upper()
    if json_output is None:
        log_json_env = os.getenv("LOG_JSON", "true").lower()
        json_output = log_json_env in {"1", "true", "yes", "on"}

    root = logging.getLogger()
    root.setLevel(getattr(logging, level, logging.INFO))

    # Install correlation-aware record factory (idempotent)
    logging.setLogRecordFactory(_correlated_factory)

    handler = logging.StreamHandler(sys.stdout)
    if json_output:
        handler.setFormatter(JSONFormatter())
    else:
        handler.setFormatter(
            logging.Formatter(
                "%(asctime)s [%(levelname)s] %(name)s: %(message)s"
            )
        )

    # Replace only our own previously-added handler to avoid duplicate output,
    # while preserving handlers from other libraries (Sentry, RotatingFileHandler, etc.)
    our_handler = getattr(root, "_agentmanager_handler", None)
    if our_handler is not None:
        root.removeHandler(our_handler)

    root.addHandler(handler)
    root._agentmanager_handler = handler  # type: ignore[attr-defined]
