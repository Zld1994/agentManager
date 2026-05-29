"""Audit event helpers for security-sensitive operations."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging
from typing import Any
import uuid

from agentManager.observability.logging import get_correlation_id

audit_logger = logging.getLogger("agentManager.audit")


def configure_audit_logger(settings: dict[str, Any]) -> None:
    """Configure the logger used for audit events."""
    global audit_logger
    audit_logger = logging.getLogger(settings.get("audit_logger_name", "agentManager.audit"))


class AuditEventType(str, Enum):
    """Security-sensitive audit event types."""

    WORKFLOW_CREATED = "workflow_created"
    TASK_EXECUTION = "task_execution"
    SANDBOX_DENIED = "sandbox_denied"
    RECOVERY_ESCALATED = "recovery_escalated"
    CONFIG_VALIDATION_FAILED = "config_validation_failed"


@dataclass
class AuditEvent:
    """Structured audit event."""

    event_type: AuditEventType
    actor: str = "system"
    workflow_id: str | None = None
    task_id: str | None = None
    correlation_id: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    def to_dict(self) -> dict[str, Any]:
        """Convert an audit event to a log-safe dictionary."""
        return {
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "actor": self.actor,
            "workflow_id": self.workflow_id,
            "task_id": self.task_id,
            "correlation_id": self.correlation_id,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


def record_audit_event(event: AuditEvent) -> AuditEvent:
    """Record an audit event and return it for tests/callers."""
    audit_logger.info("audit_event", extra={"audit_event": event.to_dict()})
    return event


def _event(
    event_type: AuditEventType,
    workflow_id: str | None = None,
    task_id: str | None = None,
    actor: str = "system",
    correlation_id: str | None = None,
    **details: Any,
) -> AuditEvent:
    return record_audit_event(
        AuditEvent(
            event_type=event_type,
            actor=actor,
            workflow_id=workflow_id,
            task_id=task_id,
            correlation_id=correlation_id or get_correlation_id(),
            details={key: value for key, value in details.items() if value is not None},
        )
    )


def audit_workflow_created(
    workflow_id: str,
    actor: str = "system",
    correlation_id: str | None = None,
) -> AuditEvent:
    """Record workflow creation."""
    return _event(
        AuditEventType.WORKFLOW_CREATED,
        workflow_id=workflow_id,
        actor=actor,
        correlation_id=correlation_id,
    )


def audit_task_execution(
    workflow_id: str,
    task_id: str,
    actor: str = "system",
) -> AuditEvent:
    """Record task execution."""
    return _event(AuditEventType.TASK_EXECUTION, workflow_id, task_id, actor)


def audit_sandbox_denied(
    workflow_id: str,
    task_id: str,
    reason: str,
    actor: str = "system",
) -> AuditEvent:
    """Record a sandbox policy denial."""
    return _event(
        AuditEventType.SANDBOX_DENIED,
        workflow_id,
        task_id,
        actor,
        reason=reason,
    )


def audit_recovery_escalated(
    workflow_id: str,
    task_id: str,
    reason: str,
    actor: str = "system",
) -> AuditEvent:
    """Record a recovery escalation."""
    return _event(
        AuditEventType.RECOVERY_ESCALATED,
        workflow_id,
        task_id,
        actor,
        reason=reason,
    )


def audit_config_validation_failed(
    setting_name: str,
    reason: str,
    actor: str = "system",
) -> AuditEvent:
    """Record configuration validation failure without leaking secret values."""
    return _event(
        AuditEventType.CONFIG_VALIDATION_FAILED,
        actor=actor,
        setting_name=setting_name,
        reason=reason,
    )
