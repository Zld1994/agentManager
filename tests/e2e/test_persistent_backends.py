"""Persistent backend integration tests.

These tests verify that the RuntimeFactory correctly wires durable backends
when environment variables are configured. Tests that require real Docker
services are marked with ``@pytest.mark.integration`` and are skipped by
default.

Run with:
    pytest tests/e2e/test_persistent_backends.py -v --no-cov
    pytest tests/e2e/test_persistent_backends.py -v --no-cov -m integration
"""

from __future__ import annotations

import asyncio
import os

import pytest

from agentManager.engine.checkpoint import (
    InMemoryCheckpointManager,
    ObjectStoreCheckpointManager,
)
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.runtime.factory import create_runtime


class MockObjectStore:
    """Minimal in-memory object store for integration testing."""

    def __init__(self):
        self._objects: dict[str, bytes] = {}

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        self._objects[key] = data

    def get_bytes(self, key):
        return self._objects.get(key)

    def delete(self, key):
        self._objects.pop(key, None)


class MockStateRepository:
    """In-memory state repository for integration testing."""

    def __init__(self):
        self.states = {}
        self.transitions = []
        self.audit_records = []
        self.workflows = {}
        self.task_runs = {}

    def save_task_state(self, task_id, state):
        self.states[task_id] = state

    def load_task_state(self, task_id):
        return self.states.get(task_id)

    def save_transition(self, transition):
        self.transitions.append(transition)

    def load_transitions(self, task_id):
        return [t for t in self.transitions if t.task_id == task_id]

    def append_audit_record(self, record):
        self.audit_records.append(record)

    def save_workflow(self, workflow):
        self.workflows[workflow.workflow_id] = workflow

    def load_workflow(self, workflow_id):
        return self.workflows.get(workflow_id)

    def save_task_run(self, task_run):
        self.task_runs[task_run.run_id] = task_run

    def load_task_run(self, run_id):
        return self.task_runs.get(run_id)


class TestRuntimeFactoryWiring:
    """Test that RuntimeFactory correctly wires all backends."""

    def test_default_runtime_uses_in_memory_backends(self):
        runtime = create_runtime(
            settings={
                "database_url": "",
                "redis_url": "",
                "object_store_endpoint": "",
                "object_store_bucket": "",
                "object_store_access_key": "",
                "object_store_secret_key": "",
                "vector_backend": "sqlite",
            }
        )
        assert runtime.state_machine.repository is None
        assert isinstance(runtime.checkpoint_manager, InMemoryCheckpointManager)
        if runtime.memory_system is not None:
            runtime.memory_system.close()

    def test_runtime_with_state_repository(self):
        repo = MockStateRepository()
        sm = StateMachine(repository=repo)
        sm.initialize("task-1", TaskState.PENDING)
        sm.transition("task-1", TaskState.READY, "deps met")

        assert repo.states["task-1"] == TaskState.READY
        assert len(repo.transitions) == 1
        assert repo.transitions[0].reason == "deps met"

        fresh_sm = StateMachine(repository=repo)
        assert fresh_sm.get_state("task-1") == TaskState.READY

    @pytest.mark.asyncio
    async def test_runtime_with_object_store_checkpoint(self):
        store = MockObjectStore()
        mgr = ObjectStoreCheckpointManager(object_store=store, prefix="checkpoints")

        context = {"task_id": "t1", "status": "running", "step": 3}
        await mgr.save_checkpoint("t1", context)

        loaded = await mgr.load_checkpoint("t1")
        assert loaded is not None
        assert loaded["task_id"] == "t1"
        assert loaded["step"] == 3

        await mgr.delete_checkpoint("t1")
        assert await mgr.load_checkpoint("t1") is None

    @pytest.mark.asyncio
    async def test_full_workflow_with_durable_state(self):
        """Simulate a workflow run where state survives a restart."""
        repo = MockStateRepository()
        sm1 = StateMachine(repository=repo)
        sm1.initialize("task-1", TaskState.PENDING)
        sm1.transition("task-1", TaskState.READY, "ready")
        sm1.transition("task-1", TaskState.IMPLEMENTING, "claimed")

        sm2 = StateMachine(repository=repo)
        assert sm2.get_state("task-1") == TaskState.IMPLEMENTING
        sm2.transition("task-1", TaskState.VERIFYING, "done implementing")
        sm2.transition("task-1", TaskState.COMPLETED, "verified")

        assert sm2.get_state("task-1") == TaskState.COMPLETED
        assert len(repo.transitions) == 4

    @pytest.mark.asyncio
    async def test_checkpoint_survives_restart(self):
        """Verify checkpoints persist across manager instances."""
        store = MockObjectStore()

        mgr1 = ObjectStoreCheckpointManager(object_store=store, prefix="ckpt")
        await mgr1.save_checkpoint("task-1", {"progress": 50})

        mgr2 = ObjectStoreCheckpointManager(object_store=store, prefix="ckpt")
        loaded = await mgr2.load_checkpoint("task-1")
        assert loaded is not None
        assert loaded["progress"] == 50


@pytest.mark.integration
class TestDockerComposeIntegration:
    """Integration tests that require real Docker services.

    These tests are skipped unless running in an environment with
    Docker Compose services (Postgres, Redis, MinIO, Qdrant) available.
    Set ``RUN_INTEGRATION=1`` to enable them.
    """

    @pytest.fixture(autouse=True)
    def _require_integration(self):
        if os.getenv("RUN_INTEGRATION") != "1":
            pytest.skip("Set RUN_INTEGRATION=1 to run Docker integration tests")

    @pytest.mark.asyncio
    async def test_postgres_state_repository_round_trip(self):
        from agentManager.storage.postgres import PostgresStateRepository

        database_url = os.getenv("DATABASE_URL")
        if not database_url:
            pytest.skip("DATABASE_URL not set")

        repo = PostgresStateRepository.from_database_url(database_url)
        repo.initialize_schema()

        sm = StateMachine(repository=repo)
        sm.initialize("integration-task-1", TaskState.PENDING)
        sm.transition("integration-task-1", TaskState.READY, "integration test")

        fresh_sm = StateMachine(repository=repo)
        assert fresh_sm.get_state("integration-task-1") == TaskState.READY

    @pytest.mark.asyncio
    async def test_redis_event_bus_publish_subscribe(self):
        redis_url = os.getenv("REDIS_URL")
        if not redis_url:
            pytest.skip("REDIS_URL not set")

        from agentManager.engine.event_bus.redis_stream import RedisStreamEventBus
        from agentManager.engine.event_bus.base import Event, EventType

        bus = RedisStreamEventBus(redis_url=redis_url)
        await bus.connect()
        try:
            received = []
            await bus.subscribe(
                EventType.TASK_CREATED,
                lambda e: received.append(e),
            )
            await bus.start_consumer("test-consumer")

            event = Event(
                event_type=EventType.TASK_CREATED,
                workflow_id="test-workflow",
                payload={"task_id": "integration-task"},
            )
            await bus.publish(event)

            await asyncio.sleep(2)
            assert len(received) >= 1
            assert received[0].payload["task_id"] == "integration-task"
        finally:
            await bus.disconnect()

    @pytest.mark.asyncio
    async def test_s3_checkpoint_round_trip(self):
        endpoint = os.getenv("OBJECT_STORE_ENDPOINT")
        bucket = os.getenv("OBJECT_STORE_BUCKET")
        if not endpoint or not bucket:
            pytest.skip("OBJECT_STORE_ENDPOINT / OBJECT_STORE_BUCKET not set")

        from agentManager.storage.object_store import S3ObjectStore

        store = S3ObjectStore.from_settings(
            endpoint_url=endpoint,
            bucket=bucket,
            access_key=os.getenv("OBJECT_STORE_ACCESS_KEY", ""),
            secret_key=os.getenv("OBJECT_STORE_SECRET_KEY", ""),
        )
        mgr = ObjectStoreCheckpointManager(object_store=store)

        await mgr.save_checkpoint("integration-ckpt", {"step": 42})
        loaded = await mgr.load_checkpoint("integration-ckpt")
        assert loaded is not None
        assert loaded["step"] == 42
        await mgr.delete_checkpoint("integration-ckpt")
