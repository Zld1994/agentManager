"""Tests for durable storage interface implementations."""

from __future__ import annotations

from datetime import timezone
from unittest.mock import MagicMock, patch

from agentManager.domain.models import TaskRun, Workflow
from agentManager.engine.state_manager import StateTransition, TaskState
from agentManager.storage import AuditRecord, ObjectStore, PostgresStateRepository, StateRepository
from agentManager.storage.object_store import S3ObjectStore


def test_storage_import_surface_exposes_public_interfaces():
    """Storage package should expose the durable backend public API."""
    assert issubclass(PostgresStateRepository, StateRepository)
    assert issubclass(S3ObjectStore, ObjectStore)


def test_audit_record_uses_timezone_aware_timestamp():
    """Audit records should use timezone-aware UTC timestamps by default."""
    record = AuditRecord(action="state_changed", entity_id="task_1", payload={})

    assert record.timestamp.tzinfo is timezone.utc
    assert record.content_hash is None


def test_postgres_initialize_schema_adds_audit_content_hash_column():
    """Schema setup should add the optional content_hash column compatibly."""
    connection = MagicMock()
    cursor_context = connection.cursor.return_value
    cursor = cursor_context.__enter__.return_value

    repository = PostgresStateRepository(connection)
    repository.initialize_schema()

    statements = [call.args[0] for call in cursor.execute.call_args_list]
    assert any("content_hash" in statement for statement in statements)
    assert any(
        "ALTER TABLE audit_record ADD COLUMN content_hash TEXT" in statement
        for statement in statements
    )


def test_postgres_state_repository_persists_state_transition_and_audit_record():
    """Postgres repository should persist state, transitions, and audit rows."""
    connection = MagicMock()
    cursor_context = connection.cursor.return_value
    cursor = cursor_context.__enter__.return_value
    cursor.fetchone.return_value = {"state": "ready"}
    cursor.fetchall.return_value = [
        {
            "task_id": "task_1",
            "from_state": "pending",
            "to_state": "ready",
            "timestamp": "2026-05-29T00:00:00+00:00",
            "reason": "dependency met",
        }
    ]

    repository = PostgresStateRepository(connection)
    transition = StateTransition(
        task_id="task_1",
        from_state=TaskState.PENDING,
        to_state=TaskState.READY,
        reason="dependency met",
    )
    record = AuditRecord(
        action="task_state_transitioned",
        entity_id="task_1",
        payload={},
        content_hash="abc123",
    )

    repository.save_task_state("task_1", TaskState.READY)
    assert repository.load_task_state("task_1") == TaskState.READY
    repository.save_transition(transition)
    assert repository.load_transitions("task_1")[0].reason == "dependency met"
    repository.append_audit_record(record)

    assert cursor.execute.call_count == 5
    connection.commit.assert_called()

    audit_insert = cursor.execute.call_args_list[-1]
    assert "content_hash" in audit_insert.args[0]
    assert audit_insert.args[1][-1] == "abc123"


def test_postgres_state_repository_persists_workflows_and_task_runs():
    """Postgres repository should expose workflow and task-run persistence."""
    connection = MagicMock()
    cursor_context = connection.cursor.return_value
    cursor = cursor_context.__enter__.return_value
    workflow = Workflow(workflow_id="wf-1", name="Demo", task_ids=["task-1"])
    task_run = TaskRun(run_id="run-1", task_id="task-1", workflow_id="wf-1", attempt=2)
    cursor.fetchone.side_effect = [
        {"payload": workflow.to_dict()},
        {"payload": task_run.to_dict()},
    ]

    repository = PostgresStateRepository(connection)

    repository.save_workflow(workflow)
    assert repository.load_workflow("wf-1").workflow_id == "wf-1"
    repository.save_task_run(task_run)
    assert repository.load_task_run("run-1").attempt == 2

    assert cursor.execute.call_count == 4
    connection.commit.assert_called()


def test_s3_object_store_uses_configured_bucket_and_client():
    """S3 object store should delegate byte operations to a provided client."""
    client = MagicMock()
    client.get_object.return_value = {"Body": MagicMock(read=MagicMock(return_value=b"data"))}
    store = S3ObjectStore(bucket="agentmanager", client=client)

    store.put_bytes("checkpoints/task.json", b"data", content_type="application/json")
    assert store.get_bytes("checkpoints/task.json") == b"data"
    store.delete("checkpoints/task.json")

    client.put_object.assert_called_once_with(
        Bucket="agentmanager",
        Key="checkpoints/task.json",
        Body=b"data",
        ContentType="application/json",
    )
    client.get_object.assert_called_once_with(
        Bucket="agentmanager",
        Key="checkpoints/task.json",
    )
    client.delete_object.assert_called_once_with(
        Bucket="agentmanager",
        Key="checkpoints/task.json",
    )


def test_s3_object_store_builds_minio_compatible_client_from_settings():
    """S3 object store should be constructible from endpoint credentials."""
    client = MagicMock()

    with patch("agentManager.storage.object_store.boto3.client", return_value=client) as factory:
        store = S3ObjectStore.from_settings(
            endpoint_url="http://minio:9000",
            bucket="agentmanager",
            access_key="access",
            secret_key="secret",
        )

    assert store.bucket == "agentmanager"
    factory.assert_called_once_with(
        "s3",
        endpoint_url="http://minio:9000",
        aws_access_key_id="access",
        aws_secret_access_key="secret",
    )
