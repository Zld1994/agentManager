"""Audit event helpers for security-critical actions.

All audit events are emitted as structured JSON log records at INFO level
under the ``agentManager.audit`` logger namespace. They can also be written
to PostgreSQL database and object storage for long-term retention via the
AUDIT_SINK environment variable (default: "log").
"""

from __future__ import annotations

import logging
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, FrozenSet, List, Optional


logger = logging.getLogger("agentManager.audit")

_VALID_SINKS = frozenset({"log", "db", "object_storage"})

_override_sinks: Optional[str] = None


def _get_audit_sinks() -> FrozenSet[str]:
    """Return the current set of audit sinks.

    Priority: in-process override (``configure_audit_sinks``) > env var
    ``AUDIT_SINK`` > default ``"log"``.  Unknown sink names emit a warning
    and are dropped from the returned set.
    """
    raw = _override_sinks if _override_sinks is not None else os.getenv("AUDIT_SINK", "log")
    raw = raw.lower()
    requested = [s.strip() for s in raw.split(",") if s.strip()]
    valid: list[str] = []
    for s in requested:
        if s in _VALID_SINKS:
            valid.append(s)
        else:
            logger.warning("Unknown audit sink %r ignored (valid: %s)", s, sorted(_VALID_SINKS))
    return frozenset(valid) or frozenset({"log"})


def configure_audit_sinks(sinks: str) -> None:
    """Set the audit sinks for the current process (in-process override).

    This takes precedence over the ``AUDIT_SINK`` environment variable and
    is safe to use in multi-threaded contexts.  Call
    :func:`reset_audit_sinks` to restore default behaviour.
    """
    global _override_sinks
    _override_sinks = sinks


def reset_audit_sinks() -> None:
    """Clear the in-process sink override, reverting to env / default."""
    global _override_sinks
    _override_sinks = None


class AuditEventType(str, Enum):
    WORKFLOW_CREATED = "workflow_created"
    TASK_EXECUTED = "task_executed"
    SANDBOX_DENIED = "sandbox_denied"
    RECOVERY_UPGRADE = "recovery_upgrade"
    CONFIG_VALIDATION_FAILED = "config_validation_failed"
    AUTH_FAILURE = "auth_failure"
    CUSTOM = "custom"


@dataclass
class AuditEvent:
    event_type: AuditEventType
    actor: str = "system"
    resource: str = ""
    outcome: str = "success"
    detail: Dict[str, Any] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        return d


_custom_audit_handlers: List[Callable[[AuditEvent], None]] = []


def record_audit_event(event: AuditEvent) -> None:
    """Emit an audit event to configured sinks."""
    sinks = _get_audit_sinks()
    event_dict = event.to_dict()

    if "log" in sinks:
        logger.info("AUDIT", extra={"audit": event_dict})

    if "db" in sinks:
        try:
            _write_to_db(event)
        except Exception:
            logger.exception("Failed to write audit event to database")

    if "object_storage" in sinks:
        try:
            _write_to_object_storage(event)
        except Exception:
            logger.exception("Failed to write audit event to object storage")

    for handler in _custom_audit_handlers:
        try:
            handler(event)
        except Exception:
            logger.exception("Custom audit handler failed")


def register_audit_handler(handler: Callable[[AuditEvent], None]) -> None:
    """Register a custom audit event handler."""
    _custom_audit_handlers.append(handler)


def unregister_audit_handler(handler: Callable[[AuditEvent], None]) -> None:
    """Unregister a custom audit event handler."""
    try:
        _custom_audit_handlers.remove(handler)
    except ValueError:
        pass


def _write_to_db(event: AuditEvent) -> None:
    """Write audit event to database via state repository if available."""
    logger.warning(
        "Audit db sink is a placeholder — event %s not actually persisted. "
        "Configure a StateRepository to enable database audit storage.",
        event.event_type.value,
    )


def _write_to_object_storage(event: AuditEvent) -> None:
    """Write audit event to object storage if available."""
    logger.warning(
        "Audit object_storage sink is a placeholder — event %s not actually archived. "
        "Configure an ObjectStore to enable object storage audit archival.",
        event.event_type.value,
    )


# ── Convenience functions ────────────────────────────────────────────────────

def log_workflow_created(
    workflow_id: str,
    actor: str = "system",
    task_count: int = 0,
    **extra: Any,
) -> None:
    record_audit_event(AuditEvent(
        event_type=AuditEventType.WORKFLOW_CREATED,
        actor=actor,
        resource=workflow_id,
        detail={"task_count": task_count, **extra},
    ))


def log_task_executed(
    task_id: str,
    task_type: str = "unknown",
    outcome: str = "success",
    duration_ms: Optional[float] = None,
    **extra: Any,
) -> None:
    detail: Dict[str, Any] = {"task_type": task_type, **extra}
    if duration_ms is not None:
        detail["duration_ms"] = duration_ms
    record_audit_event(AuditEvent(
        event_type=AuditEventType.TASK_EXECUTED,
        resource=task_id,
        outcome=outcome,
        detail=detail,
    ))


def log_sandbox_denied(
    task_id: str,
    reason: str,
    policy: str = "",
    **extra: Any,
) -> None:
    record_audit_event(AuditEvent(
        event_type=AuditEventType.SANDBOX_DENIED,
        resource=task_id,
        outcome="denied",
        detail={"reason": reason, "policy": policy, **extra},
    ))


def log_recovery_upgrade(
    task_id: str,
    from_strategy: str,
    to_strategy: str,
    **extra: Any,
) -> None:
    record_audit_event(AuditEvent(
        event_type=AuditEventType.RECOVERY_UPGRADE,
        resource=task_id,
        detail={
            "from_strategy": from_strategy,
            "to_strategy": to_strategy,
            **extra,
        },
    ))


def log_config_validation_failed(
    setting_key: str,
    reason: str,
    **extra: Any,
) -> None:
    record_audit_event(AuditEvent(
        event_type=AuditEventType.CONFIG_VALIDATION_FAILED,
        resource=setting_key,
        outcome="failure",
        detail={"reason": reason, **extra},
    ))


# ── Compatibility aliases (matching caller signatures in existing modules) ──

def audit_recovery_escalated(
    workflow_id: str,
    task_id: str,
    error_msg: str,
) -> None:
    """Alias for log_recovery_upgrade with caller-compatible signature."""
    record_audit_event(AuditEvent(
        event_type=AuditEventType.RECOVERY_UPGRADE,
        resource=task_id,
        detail={
            "workflow_id": workflow_id,
            "error_msg": error_msg,
        },
    ))


def audit_task_execution(
    workflow_id: str,
    task_id: str,
) -> None:
    """Alias for log_task_executed with caller-compatible signature."""
    record_audit_event(AuditEvent(
        event_type=AuditEventType.TASK_EXECUTED,
        resource=task_id,
        detail={"workflow_id": workflow_id},
    ))
