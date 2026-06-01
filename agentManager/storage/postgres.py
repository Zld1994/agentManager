"""Durable state repository interfaces and PostgreSQL implementation."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
import json
from typing import Any, Optional

from agentManager.domain.models import TaskRun, Workflow
from agentManager.engine.state_manager import StateTransition, TaskState


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class AuditRecord:
    """Append-only audit record for durable state changes."""

    action: str
    entity_id: str
    payload: dict[str, Any]
    timestamp: datetime = field(default_factory=utc_now)
    content_hash: Optional[str] = None


class StateRepository(ABC):
    """Persistence boundary for task state and audit history."""

    @abstractmethod
    def save_task_state(self, task_id: str, state: TaskState) -> None:
        """Persist the current state for a task."""

    @abstractmethod
    def load_task_state(self, task_id: str) -> Optional[TaskState]:
        """Load the current state for a task, if present."""

    @abstractmethod
    def save_transition(self, transition: StateTransition) -> None:
        """Persist one state transition."""

    @abstractmethod
    def load_transitions(self, task_id: str) -> list[StateTransition]:
        """Load transition history for a task."""

    @abstractmethod
    def append_audit_record(self, record: AuditRecord) -> None:
        """Append a durable audit record."""

    @abstractmethod
    def save_workflow(self, workflow: Workflow) -> None:
        """Persist a workflow aggregate."""

    @abstractmethod
    def load_workflow(self, workflow_id: str) -> Optional[Workflow]:
        """Load a workflow aggregate."""

    @abstractmethod
    def save_task_run(self, task_run: TaskRun) -> None:
        """Persist a task-run execution attempt."""

    @abstractmethod
    def load_task_run(self, run_id: str) -> Optional[TaskRun]:
        """Load a task-run execution attempt."""


class PostgresStateRepository(StateRepository):
    """PostgreSQL-backed state repository.

    The class accepts an existing DB-API/psycopg connection for testability. Use
    ``from_database_url`` in production wiring to create the connection lazily.
    """

    def __init__(self, connection: Any):
        self.connection = connection

    @classmethod
    def from_database_url(cls, database_url: str) -> "PostgresStateRepository":
        """Create a repository from a PostgreSQL connection URL."""
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:
            raise RuntimeError(
                "psycopg is required for PostgresStateRepository"
            ) from exc

        return cls(psycopg.connect(database_url, row_factory=dict_row))

    def initialize_schema(self) -> None:
        """Create durable state tables when they do not already exist."""
        statements = (
            """
            CREATE TABLE IF NOT EXISTS task_state (
                task_id TEXT PRIMARY KEY,
                state TEXT NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS task_state_transition (
                id BIGSERIAL PRIMARY KEY,
                task_id TEXT NOT NULL,
                from_state TEXT NOT NULL,
                to_state TEXT NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                reason TEXT NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS workflow (
                workflow_id TEXT PRIMARY KEY,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS task_run (
                run_id TEXT PRIMARY KEY,
                task_id TEXT NOT NULL,
                workflow_id TEXT NOT NULL,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS audit_record (
                id BIGSERIAL PRIMARY KEY,
                action TEXT NOT NULL,
                entity_id TEXT NOT NULL,
                payload JSONB NOT NULL,
                timestamp TIMESTAMPTZ NOT NULL,
                content_hash TEXT
            )
            """,
            """
            DO $$
            BEGIN
                IF NOT EXISTS (
                    SELECT 1
                    FROM information_schema.columns
                    WHERE table_name = 'audit_record'
                      AND column_name = 'content_hash'
                ) THEN
                    ALTER TABLE audit_record ADD COLUMN content_hash TEXT;
                END IF;
            END $$
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_audit_payload
            ON audit_record USING GIN (payload)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_audit_action
            ON audit_record (action)
            """,
        )
        with self.connection.cursor() as cursor:
            for statement in statements:
                cursor.execute(statement)
        self.connection.commit()

    def save_task_state(self, task_id: str, state: TaskState) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO task_state (task_id, state, updated_at)
                VALUES (%s, %s, %s)
                ON CONFLICT (task_id)
                DO UPDATE SET state = EXCLUDED.state, updated_at = EXCLUDED.updated_at
                """,
                (task_id, state.value, utc_now()),
            )
        self.connection.commit()

    def load_task_state(self, task_id: str) -> Optional[TaskState]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT state FROM task_state WHERE task_id = %s",
                (task_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return TaskState(_row_value(row, "state", 0))

    def save_transition(self, transition: StateTransition) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO task_state_transition
                (task_id, from_state, to_state, timestamp, reason)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    transition.task_id,
                    transition.from_state.value,
                    transition.to_state.value,
                    transition.timestamp,
                    transition.reason,
                ),
            )
        self.connection.commit()

    def load_transitions(self, task_id: str) -> list[StateTransition]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT task_id, from_state, to_state, timestamp, reason
                FROM task_state_transition
                WHERE task_id = %s
                ORDER BY timestamp ASC, id ASC
                """,
                (task_id,),
            )
            rows = cursor.fetchall()

        return [_transition_from_row(row) for row in rows]

    def append_audit_record(self, record: AuditRecord) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO audit_record
                (action, entity_id, payload, timestamp, content_hash)
                VALUES (%s, %s, %s::jsonb, %s, %s)
                """,
                (
                    record.action,
                    record.entity_id,
                    json.dumps(record.payload),
                    record.timestamp,
                    record.content_hash,
                ),
            )
        self.connection.commit()

    def save_workflow(self, workflow: Workflow) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO workflow (workflow_id, payload, updated_at)
                VALUES (%s, %s::jsonb, %s)
                ON CONFLICT (workflow_id)
                DO UPDATE SET payload = EXCLUDED.payload, updated_at = EXCLUDED.updated_at
                """,
                (workflow.workflow_id, json.dumps(workflow.to_dict()), utc_now()),
            )
        self.connection.commit()

    def load_workflow(self, workflow_id: str) -> Optional[Workflow]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload FROM workflow WHERE workflow_id = %s",
                (workflow_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return Workflow.from_dict(_payload_from_row(row))

    def save_task_run(self, task_run: TaskRun) -> None:
        with self.connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO task_run (run_id, task_id, workflow_id, payload, updated_at)
                VALUES (%s, %s, %s, %s::jsonb, %s)
                ON CONFLICT (run_id)
                DO UPDATE SET
                    task_id = EXCLUDED.task_id,
                    workflow_id = EXCLUDED.workflow_id,
                    payload = EXCLUDED.payload,
                    updated_at = EXCLUDED.updated_at
                """,
                (
                    task_run.run_id,
                    task_run.task_id,
                    task_run.workflow_id,
                    json.dumps(task_run.to_dict()),
                    utc_now(),
                ),
            )
        self.connection.commit()

    def load_task_run(self, run_id: str) -> Optional[TaskRun]:
        with self.connection.cursor() as cursor:
            cursor.execute(
                "SELECT payload FROM task_run WHERE run_id = %s",
                (run_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return TaskRun.from_dict(_payload_from_row(row))


def _row_value(row: Any, key: str, index: int) -> Any:
    """Read either dict-like or tuple-like DB cursor rows."""
    if isinstance(row, dict):
        return row[key]
    return row[index]


def _transition_from_row(row: Any) -> StateTransition:
    timestamp = _row_value(row, "timestamp", 3)
    if isinstance(timestamp, str):
        timestamp = datetime.fromisoformat(timestamp)
    return StateTransition(
        task_id=_row_value(row, "task_id", 0),
        from_state=TaskState(_row_value(row, "from_state", 1)),
        to_state=TaskState(_row_value(row, "to_state", 2)),
        timestamp=timestamp,
        reason=_row_value(row, "reason", 4),
    )


def _payload_from_row(row: Any) -> dict[str, Any]:
    payload = _row_value(row, "payload", 0)
    if isinstance(payload, str):
        return json.loads(payload)
    return payload
