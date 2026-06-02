"""Tests for durable audit sinks and degradation behavior."""

from __future__ import annotations

import json
import hashlib
from datetime import datetime, timezone
from unittest.mock import MagicMock

from prometheus_client import REGISTRY

from agentManager.observability.audit import (
    AuditEvent,
    AuditEventType,
    ObjectStoreAuditSink,
    PostgresAuditSink,
    configure_audit_sinks,
    record_audit_event,
    reset_audit_sinks,
)


def teardown_function():
    reset_audit_sinks()


def _sample_event() -> AuditEvent:
    return AuditEvent(
        event_type=AuditEventType.TASK_EXECUTED,
        actor="agent-1",
        resource="task-1",
        outcome="success",
        detail={"duration_ms": 12.5},
        timestamp="2026-06-01T10:15:30+00:00",
    )


def test_postgres_audit_sink_maps_event_to_audit_record():
    repository = MagicMock()
    sink = PostgresAuditSink(repository)

    sink.write(_sample_event())

    record = repository.append_audit_record.call_args.args[0]
    assert record.action == "task_executed"
    assert record.entity_id == "task-1"
    assert record.payload == {
        "actor": "agent-1",
        "outcome": "success",
        "detail": {"duration_ms": 12.5},
    }
    assert record.timestamp == datetime(2026, 6, 1, 10, 15, 30, tzinfo=timezone.utc)
    expected_payload = {
        "actor": "agent-1",
        "outcome": "success",
        "detail": {"duration_ms": 12.5},
    }
    assert (
        record.content_hash
        == hashlib.sha256(
            json.dumps(expected_payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    )


def test_postgres_audit_sink_hashes_redacted_payload():
    repository = MagicMock()
    sink = PostgresAuditSink(repository)
    event = AuditEvent(
        event_type=AuditEventType.TASK_EXECUTED,
        actor="agent-1",
        resource="task-1",
        detail={"token": "secret", "safe": "value"},
        timestamp="2026-06-01T10:15:30+00:00",
    )

    sink.write(event)

    record = repository.append_audit_record.call_args.args[0]
    assert record.payload["detail"]["token"] == "***REDACTED***"
    assert (
        record.content_hash
        == hashlib.sha256(
            json.dumps(record.payload, sort_keys=True, default=str).encode("utf-8")
        ).hexdigest()
    )


def test_object_store_audit_sink_writes_hourly_json_object():
    object_store = MagicMock()
    sink = ObjectStoreAuditSink(object_store)

    sink.write(_sample_event())

    key, body = object_store.put_bytes.call_args.args[:2]
    kwargs = object_store.put_bytes.call_args.kwargs
    assert key.startswith("audit/2026-06-01/10/")
    assert key.endswith(".json")
    assert kwargs["content_type"] == "application/json"
    payload = json.loads(body.decode("utf-8"))
    assert payload["event_type"] == "task_executed"
    assert payload["resource"] == "task-1"
    assert payload["detail"] == {"duration_ms": 12.5}


def test_record_audit_event_uses_configured_durable_sinks():
    repository = MagicMock()
    object_store = MagicMock()
    configure_audit_sinks("db,object_storage", repository=repository, object_store=object_store)

    record_audit_event(_sample_event())

    repository.append_audit_record.assert_called_once()
    object_store.put_bytes.assert_called_once()


def test_audit_sink_failure_counter_increments_when_sink_fails():
    repository = MagicMock()
    repository.append_audit_record.side_effect = RuntimeError("db down")
    configure_audit_sinks("log,db", repository=repository)

    before = (
        REGISTRY.get_sample_value("agentmanager_audit_sink_failures_total", {"sink": "db"}) or 0
    )
    record_audit_event(_sample_event())
    after = REGISTRY.get_sample_value("agentmanager_audit_sink_failures_total", {"sink": "db"})

    assert after == before + 1
