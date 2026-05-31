"""Unit tests for the observability module."""

import json
import logging
from unittest.mock import patch

import pytest

from agentManager.observability.logging import (
    JSONFormatter,
    StructuredLogger,
    clear_request_context,
    get_request_id,
    get_workflow_id,
    new_request_id,
    set_request_context,
    setup_logging,
)
from agentManager.observability.audit import (
    AuditEvent,
    AuditEventType,
    configure_audit_sinks,
    log_config_validation_failed,
    log_recovery_upgrade,
    log_sandbox_denied,
    log_task_executed,
    log_workflow_created,
    record_audit_event,
    register_audit_handler,
    reset_audit_sinks,
    unregister_audit_handler,
    _custom_audit_handlers,
    _get_audit_sinks,
    _override_sinks,
)
from agentManager.observability.tracing import (
    create_span,
    get_current_span,
    setup_tracing,
    trace_task,
    trace_workflow,
    _NoOpSpan,
)


# ── Logging tests ────────────────────────────────────────────────────────────


class TestCorrelationContext:
    def test_default_ids_are_none(self):
        clear_request_context()
        assert get_request_id() is None
        assert get_workflow_id() is None

    def test_set_and_get_request_id(self):
        set_request_context(request_id="req-abc")
        assert get_request_id() == "req-abc"
        clear_request_context()

    def test_set_and_get_workflow_id(self):
        set_request_context(workflow_id="wf-123")
        assert get_workflow_id() == "wf-123"
        clear_request_context()

    def test_new_request_id_is_hex(self):
        rid = new_request_id()
        assert len(rid) == 32
        int(rid, 16)  # Should not raise


class TestJSONFormatter:
    def _make_record(self, msg: str = "hello", **kwargs):
        record = logging.LogRecord(
            name="test", level=logging.INFO, pathname="test.py",
            lineno=1, msg=msg, args=(), exc_info=None,
        )
        record.request_id = kwargs.get("request_id", "")
        record.workflow_id = kwargs.get("workflow_id", "")
        return record

    def test_json_output_is_valid(self):
        fmt = JSONFormatter()
        record = self._make_record()
        output = fmt.format(record)
        data = json.loads(output)
        assert data["msg"] == "hello"
        assert data["level"] == "INFO"
        assert "ts" in data

    def test_correlation_ids_included(self):
        fmt = JSONFormatter()
        record = self._make_record(request_id="req-1", workflow_id="wf-2")
        data = json.loads(fmt.format(record))
        assert data["request_id"] == "req-1"
        assert data["workflow_id"] == "wf-2"

    def test_correlation_ids_omitted_when_empty(self):
        fmt = JSONFormatter()
        record = self._make_record()
        data = json.loads(fmt.format(record))
        assert "request_id" not in data
        assert "workflow_id" not in data

    def test_exception_info(self):
        fmt = JSONFormatter()
        record = self._make_record()
        try:
            raise ValueError("boom")
        except ValueError:
            import sys
            record.exc_info = sys.exc_info()
        data = json.loads(fmt.format(record))
        assert "exception" in data
        assert "ValueError" in data["exception"]


class TestSetupLogging:
    def test_setup_json(self, capsys):
        setup_logging(level="DEBUG", json_output=True)
        test_logger = logging.getLogger("test_setup_json")
        test_logger.info("json test")
        captured = capsys.readouterr()
        data = json.loads(captured.out.strip().split("\n")[-1])
        assert data["msg"] == "json test"

    def test_setup_plain(self, capsys):
        setup_logging(level="INFO", json_output=False)
        test_logger = logging.getLogger("test_setup_plain")
        test_logger.info("plain test")
        captured = capsys.readouterr()
        assert "plain test" in captured.out

    def test_setup_reads_env(self):
        with patch.dict("os.environ", {"LOG_LEVEL": "WARNING", "LOG_JSON": "false"}):
            setup_logging()
            root = logging.getLogger()
            assert root.level == logging.WARNING


class TestStructuredLogger:
    def test_native_logger(self):
        sl = StructuredLogger("my.module")
        assert sl.native.name == "my.module"

    def test_bind_returns_adapter(self):
        sl = StructuredLogger("my.module")
        adapter = sl.bind(user="alice")
        assert isinstance(adapter, logging.LoggerAdapter)


# ── Tracing tests ────────────────────────────────────────────────────────────


class TestTracing:
    def test_disabled_by_default(self):
        result = setup_tracing(enabled=False)
        assert result is False

    def test_noop_span_context_manager(self):
        with create_span("test") as span:
            assert isinstance(span, _NoOpSpan)
            span.set_attribute("key", "val")

    def test_trace_workflow_noop(self):
        with trace_workflow("wf-1") as span:
            assert isinstance(span, _NoOpSpan)

    def test_trace_task_noop(self):
        with trace_task("task-1", "compute") as span:
            assert isinstance(span, _NoOpSpan)

    def test_get_current_span_noop(self):
        span = get_current_span()
        assert isinstance(span, _NoOpSpan)

    def test_missing_packages_returns_false(self):
        # Even with enabled=True, missing packages should return False
        with patch.dict("os.environ", {"OTEL_TRACING_ENABLED": "true"}):
            result = setup_tracing(enabled=True)
            # Will be False because opentelemetry is not installed
            assert result is False


# ── Audit tests ──────────────────────────────────────────────────────────────


class TestAuditEvent:
    def test_event_creation(self):
        event = AuditEvent(
            event_type=AuditEventType.WORKFLOW_CREATED,
            actor="user-1",
            resource="wf-abc",
        )
        assert event.event_type == AuditEventType.WORKFLOW_CREATED
        assert event.outcome == "success"
        d = event.to_dict()
        assert d["event_type"] == "workflow_created"
        assert d["actor"] == "user-1"

    def test_event_type_enum_values(self):
        assert AuditEventType.SANDBOX_DENIED.value == "sandbox_denied"
        assert AuditEventType.RECOVERY_UPGRADE.value == "recovery_upgrade"


class TestAuditHelpers:
    def test_log_workflow_created(self, caplog):
        with caplog.at_level(logging.INFO, logger="agentManager.audit"):
            log_workflow_created("wf-1", actor="admin", task_count=5)
        assert len(caplog.records) == 1
        rec = caplog.records[0]
        assert rec.name == "agentManager.audit"
        audit_data = rec.extra.get("audit", {}) if hasattr(rec, "extra") else {}
        # Extra is stored in record.__dict__
        audit_data = getattr(rec, "audit", None)
        if audit_data is None:
            # Fallback: check the message
            assert "AUDIT" in rec.getMessage()

    def test_log_task_executed(self, caplog):
        with caplog.at_level(logging.INFO, logger="agentManager.audit"):
            log_task_executed("task-1", task_type="compute", duration_ms=150.0)
        assert len(caplog.records) == 1

    def test_log_sandbox_denied(self, caplog):
        with caplog.at_level(logging.INFO, logger="agentManager.audit"):
            log_sandbox_denied("task-2", reason="mount_blocked", policy="deny_docker_sock")
        assert len(caplog.records) == 1

    def test_log_recovery_upgrade(self, caplog):
        with caplog.at_level(logging.INFO, logger="agentManager.audit"):
            log_recovery_upgrade("task-3", from_strategy="retry", to_strategy="escalate")
        assert len(caplog.records) == 1

    def test_log_config_validation_failed(self, caplog):
        with caplog.at_level(logging.INFO, logger="agentManager.audit"):
            log_config_validation_failed("POSTGRES_PASSWORD", reason="weak_password")
        assert len(caplog.records) == 1

    def test_record_audit_event_direct(self, caplog):
        with caplog.at_level(logging.INFO, logger="agentManager.audit"):
            record_audit_event(AuditEvent(
                event_type=AuditEventType.CUSTOM,
                detail={"custom_key": "custom_value"},
            ))
        assert len(caplog.records) == 1


# ── Module import tests ──────────────────────────────────────────────────────


class TestModuleImports:
    def test_init_exports(self):
        """Verify all __all__ exports are importable."""
        import agentManager.observability as obs
        for name in obs.__all__:
            assert hasattr(obs, name), f"Missing export: {name}"


# ── Audit multi-sink tests ──────────────────────────────────────────────────


class TestAuditMultiSink:
    def setup_method(self):
        _custom_audit_handlers.clear()
        reset_audit_sinks()

    def teardown_method(self):
        _custom_audit_handlers.clear()
        reset_audit_sinks()

    def test_get_audit_sinks_default(self):
        with patch.dict("os.environ", {}, clear=True):
            sinks = _get_audit_sinks()
            assert "log" in sinks

    def test_get_audit_sinks_multiple(self):
        configure_audit_sinks("log,db,object_storage")
        sinks = _get_audit_sinks()
        assert sinks == frozenset({"log", "db", "object_storage"})

    def test_get_audit_sinks_rereads_override(self):
        configure_audit_sinks("log")
        assert "db" not in _get_audit_sinks()
        configure_audit_sinks("log,db")
        assert "db" in _get_audit_sinks()

    def test_configure_audit_sinks(self):
        configure_audit_sinks("log,db")
        sinks = _get_audit_sinks()
        assert "log" in sinks
        assert "db" in sinks

    def test_reset_audit_sinks(self):
        configure_audit_sinks("log,db")
        assert "db" in _get_audit_sinks()
        reset_audit_sinks()
        with patch.dict("os.environ", {"AUDIT_SINK": "log"}, clear=True):
            assert "db" not in _get_audit_sinks()

    def test_override_takes_priority_over_env(self):
        configure_audit_sinks("log,object_storage")
        with patch.dict("os.environ", {"AUDIT_SINK": "log,db"}, clear=True):
            sinks = _get_audit_sinks()
            assert sinks == frozenset({"log", "object_storage"})
            assert "db" not in sinks

    def test_invalid_sink_warns_and_ignored(self, caplog):
        with patch.dict("os.environ", {"AUDIT_SINK": "log,foo,bar"}, clear=True):
            with caplog.at_level(logging.WARNING, logger="agentManager.audit"):
                sinks = _get_audit_sinks()
            assert sinks == frozenset({"log"})
            assert any("foo" in r.getMessage() for r in caplog.records)
            assert any("bar" in r.getMessage() for r in caplog.records)

    def test_all_invalid_sinks_falls_back_to_log(self, caplog):
        with patch.dict("os.environ", {"AUDIT_SINK": "foo,bar"}, clear=True):
            with caplog.at_level(logging.WARNING, logger="agentManager.audit"):
                sinks = _get_audit_sinks()
            assert sinks == frozenset({"log"})

    def test_db_sink_emits_warning(self, caplog):
        configure_audit_sinks("log,db")
        with caplog.at_level(logging.WARNING, logger="agentManager.audit"):
            record_audit_event(AuditEvent(
                event_type=AuditEventType.TASK_EXECUTED,
                resource="task-1",
            ))
        assert any("placeholder" in r.getMessage().lower() for r in caplog.records)

    def test_object_storage_sink_emits_warning(self, caplog):
        configure_audit_sinks("log,object_storage")
        with caplog.at_level(logging.WARNING, logger="agentManager.audit"):
            record_audit_event(AuditEvent(
                event_type=AuditEventType.TASK_EXECUTED,
                resource="task-1",
            ))
        assert any("placeholder" in r.getMessage().lower() for r in caplog.records)

    def test_register_custom_handler(self):
        received = []
        register_audit_handler(lambda e: received.append(e))
        record_audit_event(AuditEvent(
            event_type=AuditEventType.CUSTOM,
            resource="test",
        ))
        assert len(received) == 1
        assert received[0].resource == "test"

    def test_unregister_custom_handler(self):
        received = []
        handler = lambda e: received.append(e)
        register_audit_handler(handler)
        unregister_audit_handler(handler)
        record_audit_event(AuditEvent(
            event_type=AuditEventType.CUSTOM,
            resource="test",
        ))
        assert len(received) == 0

    def test_unregister_missing_handler_no_error(self):
        unregister_audit_handler(lambda e: None)

    def test_custom_handler_exception_does_not_break_others(self):
        received = []
        register_audit_handler(lambda e: 1 / 0)
        register_audit_handler(lambda e: received.append(e))
        record_audit_event(AuditEvent(
            event_type=AuditEventType.CUSTOM,
            resource="test",
        ))
        assert len(received) == 1


# ── Tracing configuration tests ─────────────────────────────────────────────


class TestTracingConfiguration:
    def test_invalid_protocol_falls_back_with_warning(self, caplog):
        with patch.dict("os.environ", {
            "OTEL_TRACING_ENABLED": "true",
            "OTEL_EXPORTER_OTLP_PROTOCOL": "invalid_proto",
        }, clear=False):
            with caplog.at_level(logging.WARNING):
                result = setup_tracing(enabled=True)
            assert result is False
            assert any("invalid" in r.getMessage().lower() and "protocol" in r.getMessage().lower() for r in caplog.records)

    def test_invalid_sample_rate_falls_back(self, caplog):
        with patch.dict("os.environ", {
            "OTEL_TRACING_ENABLED": "true",
            "OTEL_TRACING_SAMPLE_RATE": "not_a_number",
        }, clear=False):
            with caplog.at_level(logging.WARNING):
                result = setup_tracing(enabled=True)
            assert result is False
            assert any("sample_rate" in r.getMessage().lower() for r in caplog.records)

    def test_out_of_range_sample_rate_clamped(self, caplog):
        with patch.dict("os.environ", {
            "OTEL_TRACING_ENABLED": "true",
            "OTEL_TRACING_SAMPLE_RATE": "5.0",
        }, clear=False):
            with caplog.at_level(logging.WARNING):
                result = setup_tracing(enabled=True)
            assert result is False
            assert any("clamping" in r.getMessage().lower() for r in caplog.records)

    def test_negative_sample_rate_clamped(self, caplog):
        with patch.dict("os.environ", {
            "OTEL_TRACING_ENABLED": "true",
            "OTEL_TRACING_SAMPLE_RATE": "-0.5",
        }, clear=False):
            with caplog.at_level(logging.WARNING):
                result = setup_tracing(enabled=True)
            assert result is False
            assert any("clamping" in r.getMessage().lower() for r in caplog.records)
