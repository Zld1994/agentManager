"""Unit tests for production observability helpers."""

import json
import logging

import pytest

from agentManager.observability.audit import (
    AuditEventType,
    audit_config_validation_failed,
    audit_recovery_escalated,
    audit_sandbox_denied,
    audit_task_execution,
    audit_workflow_created,
    configure_audit_logger,
)
from agentManager.observability.logging import (
    JsonLogFormatter,
    clear_correlation_id,
    get_correlation_id,
    set_correlation_id,
)
from agentManager.observability.tracing import (
    configure_tracing,
    is_tracing_enabled,
    trace_operation,
)


def test_json_log_formatter_includes_correlation_id():
    """JSON logs should include request/workflow correlation IDs."""
    set_correlation_id("req-123")
    try:
        record = logging.LogRecord(
            name="agentManager.test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="created task",
            args=(),
            exc_info=None,
        )

        payload = json.loads(JsonLogFormatter().format(record))

        assert payload["level"] == "INFO"
        assert payload["logger"] == "agentManager.test"
        assert payload["message"] == "created task"
        assert payload["correlation_id"] == "req-123"
    finally:
        clear_correlation_id()


def test_json_log_formatter_preserves_audit_event_payload():
    """Audit events should remain structured in JSON logs."""
    record = logging.LogRecord(
        name="agentManager.audit",
        level=logging.INFO,
        pathname=__file__,
        lineno=20,
        msg="audit_event",
        args=(),
        exc_info=None,
    )
    record.audit_event = {"event_type": "workflow_created", "workflow_id": "wf-1"}

    payload = json.loads(JsonLogFormatter().format(record))

    assert payload["message"] == "audit_event"
    assert payload["audit_event"] == {
        "event_type": "workflow_created",
        "workflow_id": "wf-1",
    }


def test_correlation_id_context_is_clearable():
    """Correlation IDs should be request-scoped and clearable."""
    set_correlation_id("request-a")
    assert get_correlation_id() == "request-a"

    clear_correlation_id()

    assert get_correlation_id() is None


def test_audit_event_helpers_create_structured_security_events():
    """Audit helpers should produce structured, minimal security events."""
    event = audit_workflow_created("wf-1", actor="alice", correlation_id="req-1")

    assert event.event_type == AuditEventType.WORKFLOW_CREATED
    assert event.actor == "alice"
    assert event.workflow_id == "wf-1"
    assert event.correlation_id == "req-1"
    assert event.details == {}
    assert event.to_dict()["event_type"] == "workflow_created"


def test_audit_logger_name_is_configurable():
    """Audit logger names should follow observability settings."""
    configure_audit_logger({"audit_logger_name": "custom.audit"})
    try:
        event = audit_workflow_created("wf-2")
        assert event.event_type == AuditEventType.WORKFLOW_CREATED
    finally:
        configure_audit_logger({"audit_logger_name": "agentManager.audit"})


@pytest.mark.parametrize(
    ("helper", "event_type"),
    [
        (lambda: audit_task_execution("wf-1", "task-1"), AuditEventType.TASK_EXECUTION),
        (
            lambda: audit_sandbox_denied("wf-1", "task-1", "mount denied"),
            AuditEventType.SANDBOX_DENIED,
        ),
        (
            lambda: audit_recovery_escalated("wf-1", "task-1", "hitl"),
            AuditEventType.RECOVERY_ESCALATED,
        ),
        (
            lambda: audit_config_validation_failed("SECRET_KEY", "weak value"),
            AuditEventType.CONFIG_VALIDATION_FAILED,
        ),
    ],
)
def test_audit_helpers_cover_task8_security_events(helper, event_type):
    """Task 8 audit helpers should cover all required sensitive events."""
    assert helper().event_type == event_type


def test_tracing_is_disabled_by_default_and_records_noop_spans():
    """Local development should not require an OpenTelemetry dependency."""
    configure_tracing({"otel_tracing_enabled": False})

    with trace_operation("workflow.run", workflow_id="wf-1") as span:
        span.set_attribute("task_count", 2)

    assert is_tracing_enabled() is False
    assert span.name == "workflow.run"
    assert span.attributes["workflow_id"] == "wf-1"
    assert span.attributes["task_count"] == 2
    assert span.error is None


def test_trace_operation_records_exceptions_before_reraising():
    """Trace spans should capture exceptions without swallowing them."""
    with pytest.raises(RuntimeError, match="boom"):
        with trace_operation("task.run") as span:
            raise RuntimeError("boom")

    assert span.error == "boom"
