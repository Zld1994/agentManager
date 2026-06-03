"""Shared domain models for workflow orchestration entities."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import Enum
from typing import Any, TypeVar
import uuid


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _require_non_empty(value: str, field_name: str) -> None:
    if not value:
        raise ValueError(f"{field_name} is required")


def _coerce_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        parsed = datetime.fromisoformat(value)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return utc_now()


EnumType = TypeVar("EnumType", bound=Enum)


def _coerce_enum(value: Any, enum_cls: type[EnumType], field_name: str) -> EnumType:
    if isinstance(value, enum_cls):
        return value
    if isinstance(value, str):
        return enum_cls(value)
    raise ValueError(f"{field_name} must be of type {enum_cls.__name__}")


def _serialize_value(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, list):
        return [_serialize_value(item) for item in value]
    if isinstance(value, dict):
        return {key: _serialize_value(item) for key, item in value.items()}
    return value


def _model_to_dict(instance: Any) -> dict[str, Any]:
    return {
        model_field.name: _serialize_value(getattr(instance, model_field.name))
        for model_field in fields(instance)
    }


class WorkflowStatus(str, Enum):
    """Workflow lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class TaskStatus(str, Enum):
    """Task lifecycle states."""

    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED_REPAIR = "blocked_repair"
    BLOCKED_HITL = "blocked_hitl"


class TaskRunStatus(str, Enum):
    """Task run lifecycle states."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELED = "canceled"


class AgentStatus(str, Enum):
    """Agent availability states."""

    IDLE = "idle"
    BUSY = "busy"
    OFFLINE = "offline"
    DISABLED = "disabled"


class WorkerStatus(str, Enum):
    """Worker runtime states."""

    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"
    DRAINING = "draining"


class ArtifactType(str, Enum):
    """Artifact categories."""

    LOG = "log"
    REPORT = "report"
    SNAPSHOT = "snapshot"
    DATASET = "dataset"
    BINARY = "binary"
    OTHER = "other"


class EventType(str, Enum):
    """Domain event categories."""

    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_BLOCKED = "task_blocked"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"
    AGENT_REGISTERED = "agent_registered"
    WORKER_REGISTERED = "worker_registered"
    ARTIFACT_CREATED = "artifact_created"
    CHECKPOINT_SAVED = "checkpoint_saved"
    TASK_PLAN_CREATED = "task_plan_created"
    TASK_PLAN_UPDATED = "task_plan_updated"
    TASK_PLAN_CONFIRMED = "task_plan_confirmed"
    TASK_PLAN_CONFIRM_FAILED = "task_plan_confirm_failed"
    AGENT_ASSIGNED = "agent_assigned"


@dataclass
class Workflow:
    """Represents a workflow definition and aggregate state."""

    workflow_id: str
    name: str = ""
    status: WorkflowStatus | str = WorkflowStatus.PENDING
    task_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_non_empty(self.workflow_id, "workflow_id")
        self.status = _coerce_enum(self.status, WorkflowStatus, "status")
        self.created_at = _coerce_datetime(self.created_at)
        self.updated_at = _coerce_datetime(self.updated_at)

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Workflow":
        return cls(**data)


@dataclass
class Task:
    """Represents a workflow task."""

    task_id: str
    workflow_id: str
    task_type: str
    status: TaskStatus | str = TaskStatus.PENDING
    dependencies: list[str] = field(default_factory=list)
    input_data: dict[str, Any] = field(default_factory=dict)
    output_data: dict[str, Any] = field(default_factory=dict)
    assignee_agent_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_non_empty(self.task_id, "task_id")
        _require_non_empty(self.workflow_id, "workflow_id")
        _require_non_empty(self.task_type, "task_type")
        self.status = _coerce_enum(self.status, TaskStatus, "status")
        self.created_at = _coerce_datetime(self.created_at)
        self.updated_at = _coerce_datetime(self.updated_at)

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Task":
        return cls(**data)


@dataclass
class TaskRun:
    """Represents one execution attempt for a task."""

    run_id: str
    task_id: str
    workflow_id: str
    status: TaskRunStatus | str = TaskRunStatus.PENDING
    attempt: int = 1
    started_at: datetime | None = None
    finished_at: datetime | None = None
    result: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_non_empty(self.run_id, "run_id")
        _require_non_empty(self.task_id, "task_id")
        _require_non_empty(self.workflow_id, "workflow_id")
        self.status = _coerce_enum(self.status, TaskRunStatus, "status")
        self.started_at = _coerce_datetime(self.started_at) if self.started_at else None
        self.finished_at = _coerce_datetime(self.finished_at) if self.finished_at else None
        self.created_at = _coerce_datetime(self.created_at)

    def mark_running(self) -> None:
        self.status = TaskRunStatus.RUNNING
        self.started_at = self.started_at or utc_now()

    def mark_completed(self, result: dict[str, Any] | None = None) -> None:
        self.status = TaskRunStatus.COMPLETED
        self.finished_at = utc_now()
        if result is not None:
            self.result = result

    def mark_failed(self, error: str) -> None:
        self.status = TaskRunStatus.FAILED
        self.finished_at = utc_now()
        self.error = error

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "TaskRun":
        return cls(**data)


@dataclass
class Agent:
    """Represents an agent definition."""

    agent_id: str
    name: str
    status: AgentStatus | str = AgentStatus.IDLE
    capabilities: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_non_empty(self.agent_id, "agent_id")
        _require_non_empty(self.name, "name")
        self.status = _coerce_enum(self.status, AgentStatus, "status")
        self.created_at = _coerce_datetime(self.created_at)

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Agent":
        return cls(**data)


@dataclass
class Worker:
    """Represents a worker capable of running tasks."""

    worker_id: str
    agent_id: str | None = None
    status: WorkerStatus | str = WorkerStatus.OFFLINE
    capacity: int = 1
    labels: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_non_empty(self.worker_id, "worker_id")
        self.status = _coerce_enum(self.status, WorkerStatus, "status")
        if self.capacity < 1:
            raise ValueError("capacity must be >= 1")
        self.created_at = _coerce_datetime(self.created_at)
        self.updated_at = _coerce_datetime(self.updated_at)

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Worker":
        return cls(**data)


@dataclass
class Artifact:
    """Represents output generated by workflows/tasks/runs."""

    artifact_id: str
    artifact_type: ArtifactType | str
    uri: str
    workflow_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    size_bytes: int | None = None
    checksum: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_non_empty(self.artifact_id, "artifact_id")
        _require_non_empty(self.uri, "uri")
        self.artifact_type = _coerce_enum(self.artifact_type, ArtifactType, "artifact_type")
        if self.size_bytes is not None and self.size_bytes < 0:
            raise ValueError("size_bytes must be >= 0")
        self.created_at = _coerce_datetime(self.created_at)

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Artifact":
        return cls(**data)


@dataclass
class Checkpoint:
    """Represents a persisted recovery checkpoint."""

    checkpoint_id: str
    workflow_id: str
    task_id: str | None = None
    run_id: str | None = None
    sequence: int = 0
    payload: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        _require_non_empty(self.checkpoint_id, "checkpoint_id")
        _require_non_empty(self.workflow_id, "workflow_id")
        if self.sequence < 0:
            raise ValueError("sequence must be >= 0")
        self.created_at = _coerce_datetime(self.created_at)

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Checkpoint":
        return cls(**data)


@dataclass
class Event:
    """Represents a domain event."""

    event_type: EventType | str
    workflow_id: str
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    task_id: str | None = None
    run_id: str | None = None
    agent_id: str | None = None
    worker_id: str | None = None
    payload: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=utc_now)

    def __post_init__(self) -> None:
        self.event_type = _coerce_enum(self.event_type, EventType, "event_type")
        _require_non_empty(self.workflow_id, "workflow_id")
        _require_non_empty(self.event_id, "event_id")
        self.timestamp = _coerce_datetime(self.timestamp)

    def __hash__(self) -> int:
        return hash(self.event_id)

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Event":
        return cls(**data)
