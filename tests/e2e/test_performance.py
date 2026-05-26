"""End-to-end tests for implemented agentManager capabilities."""

import io
import json
import tarfile
import time

import pytest

from agentManager.engine.checkpoint import load_checkpoint_with_recovery, safe_extract
from agentManager.engine.dag import DAGNode, TaskStatus
from agentManager.engine.event_bus import Event, EventType
from agentManager.engine.state_manager import TaskState


def test_core_workflow_from_schedule_to_completion(workflow_components):
    """Run a small workflow across DAG, state, event bus, and scheduler."""
    dag = workflow_components["dag"]
    state = workflow_components["state"]
    events = workflow_components["events"]
    scheduler = workflow_components["scheduler"]
    received = []

    events.subscribe(EventType.TASK_COMPLETED, received.append)

    dag.add_node(DAGNode(node_id="extract", task_type="io"))
    dag.add_node(DAGNode(node_id="transform", task_type="compute"))
    dag.add_edge("extract", "transform")

    state.initialize("extract", TaskState.PENDING)
    state.initialize("transform", TaskState.PENDING)
    scheduler.add_task("extract", priority=10)
    scheduler.add_task("transform", priority=5, dependencies=["extract"])

    scheduler.execute_scheduled_tasks()
    assert scheduler.get_running_tasks() == ["extract"]

    dag.update_node_status("extract", TaskStatus.COMPLETED)
    state.transition("extract", TaskState.COMPLETED, reason="e2e")
    scheduler.mark_completed("extract")
    events.publish(
        Event(EventType.TASK_COMPLETED, workflow_id="wf", payload={"task_id": "extract"})
    )

    scheduler.tasks["transform"].next_retry_at = None
    scheduler.execute_scheduled_tasks()

    assert "transform" in scheduler.get_running_tasks()
    assert received[0].payload["task_id"] == "extract"
    assert dag.get_ready_nodes() == ["transform"]


def test_api_task_lifecycle(api_client):
    """Create and complete tasks through the public API."""
    first = api_client.post("/tasks", json={"node_id": "task_1", "task_type": "type1"})
    assert first.status_code == 201

    second = api_client.post(
        "/tasks",
        json={"node_id": "task_2", "task_type": "type2", "dependencies": ["task_1"]},
    )
    assert second.status_code == 201

    ready_before = api_client.get("/tasks/ready").json()["ready_tasks"]
    assert "task_1" in ready_before
    assert "task_2" not in ready_before

    completed = api_client.post("/tasks/task_1/complete")
    assert completed.status_code == 200

    ready_after = api_client.get("/tasks/ready").json()["ready_tasks"]
    assert "task_2" in ready_after


@pytest.mark.asyncio
async def test_checkpoint_restore_and_malicious_archive_rejection(tmp_path):
    """Load a valid checkpoint and reject an archive escaping the target path."""
    valid_tar = tmp_path / "valid.tar.gz"
    checkpoint_data = {"state": "ready", "step": 2}

    with tarfile.open(valid_tar, "w:gz") as tar:
        payload = json.dumps(checkpoint_data).encode()
        info = tarfile.TarInfo(name="checkpoint.json")
        info.size = len(payload)
        tar.addfile(info, fileobj=io.BytesIO(payload))

    loaded = await load_checkpoint_with_recovery(str(valid_tar), "task_1")
    assert loaded == checkpoint_data

    malicious_tar = tmp_path / "malicious.tar.gz"
    extract_dir = tmp_path / "extract"
    extract_dir.mkdir()
    with tarfile.open(malicious_tar, "w:gz") as tar:
        info = tarfile.TarInfo(name="../../evil.py")
        info.size = 0
        tar.addfile(info, fileobj=io.BytesIO())

    with tarfile.open(malicious_tar, "r:gz") as tar:
        with pytest.raises(ValueError):
            safe_extract(tar, str(extract_dir))


def test_lightweight_scheduler_throughput(workflow_components):
    """Verify the implemented scheduler can process a small task batch quickly."""
    scheduler = workflow_components["scheduler"]

    for index in range(25):
        scheduler.add_task(f"task_{index}", priority=index % 5)

    start = time.perf_counter()
    while scheduler.execution_queue:
        scheduler.execute_scheduled_tasks()
        for task_id in list(scheduler.get_running_tasks()):
            scheduler.mark_completed(task_id)
    duration = time.perf_counter() - start

    assert len(scheduler.get_completed_tasks()) == 25
    assert duration < 1.0
