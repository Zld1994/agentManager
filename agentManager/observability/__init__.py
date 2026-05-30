"""Observability module for agentManager.

Provides structured logging, OpenTelemetry tracing, and audit event capabilities
for production monitoring and security auditing.
"""

from agentManager.observability.logging import (
    StructuredLogger,
    setup_logging,
    get_request_id,
    get_correlation_id,
    set_correlation_id,
    clear_correlation_id,
    get_workflow_id,
    set_request_context,
    clear_request_context,
)
from agentManager.observability.tracing import (
    setup_tracing,
    trace_workflow,
    trace_task,
    create_span,
    trace_operation,
    get_current_span,
)
from agentManager.observability.audit import (
    AuditEvent,
    AuditEventType,
    record_audit_event,
    log_workflow_created,
    log_task_executed,
    audit_task_execution,
    log_sandbox_denied,
    log_recovery_upgrade,
    audit_recovery_escalated,
    log_config_validation_failed,
)

__all__ = [
    # Logging
    "StructuredLogger",
    "setup_logging",
    "get_request_id",
    "get_correlation_id",
    "get_workflow_id",
    "set_request_context",
    "clear_request_context",
    # Tracing
    "setup_tracing",
    "trace_workflow",
    "trace_task",
    "create_span",
    "trace_operation",
    "get_current_span",
    # Audit
    "AuditEvent",
    "AuditEventType",
    "record_audit_event",
    "log_workflow_created",
    "log_task_executed",
    "audit_task_execution",
    "log_sandbox_denied",
    "log_recovery_upgrade",
    "audit_recovery_escalated",
    "log_config_validation_failed",
]