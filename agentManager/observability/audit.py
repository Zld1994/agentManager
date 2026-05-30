"""Audit event helpers for security-critical actions.

All audit events are emitted as structured JSON log records at INFO level
under the ``agentManager.audit`` logger namespace.  They can be forwarded to any log
aggregator (Loki, ELK, CloudWatch) without additional infrastructure.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, Optional


logger = logging.getLogger("agentManager.audit")


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


def record_audit_event(event: AuditEvent) -> None:
    """Emit an audit event as a structured log record."""
    logger.info("AUDIT", extra={"audit": event.to_dict()})


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
