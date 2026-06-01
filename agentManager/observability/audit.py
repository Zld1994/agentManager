"""Audit event sinks for durable audit trail persistence.

Provides:
- ``AuditEvent``: domain-level audit event model
- ``AuditSink``: abstract base for audit sinks
- ``PostgresAuditSink``: writes audit events via ``StateRepository``
- ``ObjectStoreAuditSink``: writes audit events as individual JSON files
  with hourly key prefix aggregation
- ``LogAuditSink``: always-on fallback that writes to the Python logger
- ``configure_audit_sinks``: factory for wiring sinks from environment
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AuditEventType(str, Enum):
    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_STATE_TRANSITIONED = "task_state_transitioned"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    CHECKPOINT_SAVED = "checkpoint_saved"
    SANDBOX_CREATED = "sandbox_created"
    SANDBOX_EXECUTED = "sandbox_executed"
    REPAIR_STARTED = "repair_started"
    REPAIR_COMPLETED = "repair_completed"


class AuditOutcome(str, Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    DEGRADED = "degraded"


@dataclass
class AuditEvent:
    """Domain-level audit event.

    Maps to the ``audit_record`` table via explicit column mapping:
      - ``timestamp`` → ``timestamp``
      - ``event_type.value`` → ``action``
      - ``resource`` → ``entity_id``
      - ``actor``, ``outcome``, ``detail`` → keys in ``payload`` (JSONB)
    """

    event_type: AuditEventType
    resource: str
    timestamp: datetime = field(default_factory=utc_now)
    actor: str = ""
    outcome: AuditOutcome = AuditOutcome.SUCCESS
    detail: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))


class AuditSink(ABC):
    """Abstract base for audit event sinks."""

    @abstractmethod
    def write(self, event: AuditEvent) -> None:
        """Persist an audit event."""


class PostgresAuditSink(AuditSink):
    """Write audit events to PostgreSQL via ``StateRepository``.

    Reuses the existing connection pool and ``append_audit_record()`` method.
    Does **not** open its own database connections.
    """

    def __init__(self, repository: Any):
        self.repository = repository

    def write(self, event: AuditEvent) -> None:
        from agentManager.storage.postgres import AuditRecord

        payload = {
            "actor": event.actor,
            "outcome": event.outcome.value,
            "detail": event.detail,
        }
        record = AuditRecord(
            action=event.event_type.value,
            entity_id=event.resource,
            payload=payload,
            timestamp=event.timestamp,
        )
        self.repository.append_audit_record(record)


class ObjectStoreAuditSink(AuditSink):
    """Write audit events as individual JSON files to an object store.

    Key format: ``audit/{yyyy-mm-dd}/{hh}/{event_id}.json``

    Each event is written as a separate file, so there are no concurrent
    write conflicts.  Query by key prefix ``audit/{date}/{hour}/`` for
    bulk retrieval.
    """

    def __init__(self, object_store: Any):
        self.object_store = object_store

    def write(self, event: AuditEvent) -> None:
        key = (
            f"audit/{event.timestamp.strftime('%Y-%m-%d')}"
            f"/{event.timestamp.strftime('%H')}"
            f"/{event.event_id}.json"
        )
        data = json.dumps(
            {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "resource": event.resource,
                "actor": event.actor,
                "outcome": event.outcome.value,
                "detail": event.detail,
                "timestamp": event.timestamp.isoformat(),
            }
        ).encode("utf-8")
        self.object_store.put_bytes(key, data, content_type="application/json")


class LogAuditSink(AuditSink):
    """Always-on fallback sink that writes audit events to the Python logger."""

    def write(self, event: AuditEvent) -> None:
        logger.info(
            "audit event: type=%s resource=%s actor=%s outcome=%s",
            event.event_type.value,
            event.resource,
            event.actor,
            event.outcome.value,
        )


def configure_audit_sinks(
    repository: Any = None,
    object_store: Any = None,
) -> List[AuditSink]:
    """Build the audit sink chain from available backends.

    The log sink is always appended first so that no events are lost even
    when durable backends are unavailable.
    """
    sinks: List[AuditSink] = [LogAuditSink()]

    sink_config = os.getenv("AUDIT_SINK", "log").lower()
    if "db" in sink_config or "postgres" in sink_config:
        if repository is not None:
            sinks.append(PostgresAuditSink(repository))
        else:
            logger.warning("AUDIT_SINK includes db but no repository provided")

    if "object_storage" in sink_config or "s3" in sink_config:
        if object_store is not None:
            sinks.append(ObjectStoreAuditSink(object_store))
        else:
            logger.warning("AUDIT_SINK includes object_storage but no store provided")

    return sinks
