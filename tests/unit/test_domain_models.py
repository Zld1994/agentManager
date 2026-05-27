"""Unit tests for shared domain models."""

from datetime import timezone

import pytest

from agentManager.domain import (
    Agent,
    AgentStatus,
    Artifact,
    ArtifactType,
    Checkpoint,
    Event,
    EventType,
    Task,
    TaskRun,
    TaskRunStatus,
    TaskStatus,
    Workflow,
    WorkflowStatus,
    Worker,
    WorkerStatus,
)


class TestWorkflowModel:
    """Tests for workflow model."""

    def test_workflow_defaults(self):
        workflow = Workflow(workflow_id="wf_1")

        assert workflow.status == WorkflowStatus.PENDING
        assert workflow.task_ids == []
        assert workflow.metadata == {}
        assert workflow.created_at.tzinfo == timezone.utc
        assert workflow.updated_at.tzinfo == timezone.utc

    def test_workflow_round_trip(self):
        workflow = Workflow(
            workflow_id="wf_1",
            name="Daily pipeline",
            status=WorkflowStatus.RUNNING,
            task_ids=["task_1", "task_2"],
            metadata={"priority": "high"},
        )

        restored = Workflow.from_dict(workflow.to_dict())
        assert restored == workflow

    def test_workflow_requires_id(self):
        with pytest.raises(ValueError, match="workflow_id is required"):
            Workflow(workflow_id="")


class TestTaskModel:
    """Tests for task model."""

    def test_task_accepts_string_status(self):
        task = Task(
            task_id="task_1",
            workflow_id="wf_1",
            task_type="build",
            status="running",
        )

        assert task.status == TaskStatus.RUNNING

    def test_task_round_trip(self):
        task = Task(
            task_id="task_1",
            workflow_id="wf_1",
            task_type="build",
            dependencies=["task_0"],
            input_data={"source": "repo"},
            output_data={"artifact": "dist"},
            metadata={"attempt": 1},
        )

        restored = Task.from_dict(task.to_dict())
        assert restored == task

    def test_task_requires_ids_and_type(self):
        with pytest.raises(ValueError, match="task_id is required"):
            Task(task_id="", workflow_id="wf_1", task_type="build")
        with pytest.raises(ValueError, match="workflow_id is required"):
            Task(task_id="task_1", workflow_id="", task_type="build")
        with pytest.raises(ValueError, match="task_type is required"):
            Task(task_id="task_1", workflow_id="wf_1", task_type="")


class TestTaskRunModel:
    """Tests for task run model."""

    def test_task_run_sets_terminal_timestamps(self):
        task_run = TaskRun(
            run_id="run_1",
            task_id="task_1",
            workflow_id="wf_1",
            status=TaskRunStatus.PENDING,
        )
        assert task_run.finished_at is None

        task_run.mark_running()
        assert task_run.status == TaskRunStatus.RUNNING
        assert task_run.started_at is not None

        task_run.mark_completed({"ok": True})
        assert task_run.status == TaskRunStatus.COMPLETED
        assert task_run.finished_at is not None
        assert task_run.result == {"ok": True}

    def test_task_run_mark_failed(self):
        task_run = TaskRun(
            run_id="run_1",
            task_id="task_1",
            workflow_id="wf_1",
        )
        task_run.mark_failed("boom")
        assert task_run.status == TaskRunStatus.FAILED
        assert task_run.error == "boom"
        assert task_run.finished_at is not None


class TestAgentAndWorkerModels:
    """Tests for agent and worker models."""

    def test_agent_round_trip(self):
        agent = Agent(
            agent_id="agent_1",
            name="planner",
            capabilities=["plan", "review"],
            status=AgentStatus.BUSY,
            metadata={"team": "core"},
        )

        restored = Agent.from_dict(agent.to_dict())
        assert restored == agent

    def test_worker_round_trip(self):
        worker = Worker(
            worker_id="worker_1",
            agent_id="agent_1",
            status=WorkerStatus.ONLINE,
            capacity=4,
            labels=["cpu", "linux"],
            metadata={"region": "local"},
        )

        restored = Worker.from_dict(worker.to_dict())
        assert restored == worker

    def test_worker_capacity_must_be_positive(self):
        with pytest.raises(ValueError, match="capacity must be >= 1"):
            Worker(worker_id="worker_1", capacity=0)


class TestArtifactCheckpointEventModels:
    """Tests for artifact, checkpoint, and event models."""

    def test_artifact_round_trip(self):
        artifact = Artifact(
            artifact_id="art_1",
            artifact_type=ArtifactType.LOG,
            uri="file:///tmp/log.txt",
            workflow_id="wf_1",
            task_id="task_1",
            size_bytes=120,
            metadata={"format": "text"},
        )

        restored = Artifact.from_dict(artifact.to_dict())
        assert restored == artifact

    def test_checkpoint_round_trip(self):
        checkpoint = Checkpoint(
            checkpoint_id="cp_1",
            workflow_id="wf_1",
            task_id="task_1",
            run_id="run_1",
            sequence=3,
            payload={"state": "ready"},
        )

        restored = Checkpoint.from_dict(checkpoint.to_dict())
        assert restored == checkpoint

    def test_checkpoint_sequence_must_be_non_negative(self):
        with pytest.raises(ValueError, match="sequence must be >= 0"):
            Checkpoint(checkpoint_id="cp_1", workflow_id="wf_1", sequence=-1)

    def test_event_round_trip(self):
        event = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="wf_1",
            task_id="task_1",
            run_id="run_1",
            payload={"success": True},
        )

        restored = Event.from_dict(event.to_dict())
        assert restored == event

    def test_event_accepts_string_event_type(self):
        event = Event(event_type="workflow_started", workflow_id="wf_1")
        assert event.event_type == EventType.WORKFLOW_STARTED
