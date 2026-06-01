"""Audit event helpers for security-critical actions.

All audit events are emitted as structured JSON log records at INFO level
under the ``agentManager.audit`` logger namespace. They can also be written
to PostgreSQL database and object storage for long-term retention via the
AUDIT_SINK environment variable (default: "log").
"""

from __future__ import annotations

import json
import hashlib
import logging
import os
import uuid
from copy import deepcopy
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import TYPE_CHECKING, Any, Callable, Dict, FrozenSet, List, Optional

from prometheus_client import Counter

if TYPE_CHECKING:
    from agentManager.storage import ObjectStore, StateRepository


logger = logging.getLogger("agentManager.audit")

_VALID_SINKS = frozenset({"log", "db", "object_storage"})
_DEFAULT_REDACT_FIELDS = frozenset({"api_key", "password", "token"})

AUDIT_SINK_FAILURES = Counter(
    "agentmanager_audit_sink_failures_total",
    "Total audit sink write failures.",
    ["sink"],
)

_override_sinks: Optional[str] = None
_state_repository: Optional[StateRepository] = None
_object_store: Optional[ObjectStore] = None


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


def configure_audit_sinks(
    sinks: str,
    repository: Optional[StateRepository] = None,
    object_store: Optional[ObjectStore] = None,
) -> None:
    """Set the audit sinks for the current process (in-process override).

    This takes precedence over the ``AUDIT_SINK`` environment variable and
    is safe to use in multi-threaded contexts.  Call
    :func:`reset_audit_sinks` to restore default behaviour.
    """
    global _override_sinks, _state_repository, _object_store
    _override_sinks = sinks
    _state_repository = repository
    _object_store = object_store


def reset_audit_sinks() -> None:
    """Clear the in-process sink override, reverting to env / default."""
    global _override_sinks, _state_repository, _object_store
    _override_sinks = None
    _state_repository = None
    _object_store = None


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


class PostgresAuditSink:
    """Audit sink backed by the configured state repository."""

    def __init__(self, repository: "StateRepository"):
        self.repository = repository

    def write(self, event: AuditEvent) -> None:
        from agentManager.storage import AuditRecord

        redacted = redact_audit_event(event)
        payload = {
            "actor": redacted.actor,
            "outcome": redacted.outcome,
            "detail": redacted.detail,
        }
        self.repository.append_audit_record(
            AuditRecord(
                action=redacted.event_type.value,
                entity_id=redacted.resource,
                payload=payload,
                timestamp=_parse_event_timestamp(redacted.timestamp),
                content_hash=_content_hash(payload),
            )
        )


class ObjectStoreAuditSink:
    """Audit sink that archives one JSON object per audit event."""

    def __init__(self, object_store: "ObjectStore", prefix: str = "audit"):
        self.object_store = object_store
        self.prefix = prefix.strip("/")

    def write(self, event: AuditEvent) -> None:
        redacted = redact_audit_event(event)
        timestamp = _parse_event_timestamp(redacted.timestamp)
        key = (
            f"{self.prefix}/{timestamp:%Y-%m-%d}/{timestamp:%H}/"
            f"{uuid.uuid4().hex}.json"
        )
        self.object_store.put_bytes(
            key,
            json.dumps(redacted.to_dict(), sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )


def redact_audit_event(event: AuditEvent) -> AuditEvent:
    """Return a copy of an audit event with sensitive detail fields redacted."""
    redacted = AuditEvent(
        event_type=event.event_type,
        actor=event.actor,
        resource=event.resource,
        outcome=event.outcome,
        detail=_redact_value(deepcopy(event.detail), _redact_fields()),
        timestamp=event.timestamp,
    )
    return redacted


def _redact_fields() -> FrozenSet[str]:
    raw = os.getenv("AUDIT_REDACT_FIELDS")
    if raw is None:
        return _DEFAULT_REDACT_FIELDS
    fields = {field.strip().lower() for field in raw.split(",") if field.strip()}
    return frozenset(fields)


def _redact_value(value: Any, fields: FrozenSet[str]) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if str(key).lower() in fields else _redact_value(val, fields)
            for key, val in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item, fields) for item in value]
    return value


def _parse_event_timestamp(timestamp: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
    except ValueError:
        return datetime.now(timezone.utc)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _content_hash(payload: Dict[str, Any]) -> str:
    """Return a stable non-secret integrity hash for an audit payload."""
    encoded = json.dumps(payload, sort_keys=True, default=str).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


_custom_audit_handlers: List[Callable[[AuditEvent], None]] = []


def record_audit_event(event: AuditEvent) -> None:
    """Emit an audit event to configured sinks."""
    sinks = _get_audit_sinks()
    redacted_event = redact_audit_event(event)
    event_dict = redacted_event.to_dict()

    if "log" in sinks:
        logger.info("AUDIT", extra={"audit": event_dict})

    if "db" in sinks:
        try:
            _write_to_db(redacted_event)
        except Exception:
            AUDIT_SINK_FAILURES.labels(sink="db").inc()
            logger.exception("Failed to write audit event to database")

    if "object_storage" in sinks:
        try:
            _write_to_object_storage(redacted_event)
        except Exception:
            AUDIT_SINK_FAILURES.labels(sink="object_storage").inc()
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
    if _state_repository is None:
        raise RuntimeError("Configure a StateRepository to enable database audit storage")
    PostgresAuditSink(_state_repository).write(event)


def _write_to_object_storage(event: AuditEvent) -> None:
    """Write audit event to object storage if available."""
    if _object_store is None:
        raise RuntimeError("Configure an ObjectStore to enable object storage audit archival")
    ObjectStoreAuditSink(_object_store).write(event)


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
