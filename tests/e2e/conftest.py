"""Fixtures for end-to-end tests built from currently implemented modules."""

import shutil
import time
import uuid
from pathlib import Path

import pytest


@pytest.fixture
def tmp_path(request):
    """Use a repo-local temp path to avoid locked Windows user temp folders."""
    base_path = (
        Path(__file__).resolve().parents[2] / ".test-artifacts" / "pytest-e2e"
    )
    safe_name = "".join(
        character if character.isalnum() or character in ("-", "_") else "_"
        for character in request.node.name
    )
    path = base_path / f"{safe_name}-{uuid.uuid4().hex}"
    path.mkdir(parents=True)

    try:
        yield path
    finally:
        for _ in range(3):
            try:
                shutil.rmtree(path)
                break
            except PermissionError:
                time.sleep(0.1)


@pytest.fixture
def api_client():
    """Create an isolated API test client."""
    try:
        from fastapi.testclient import TestClient
        from agentManager.api import app, dag_engine, event_bus, scheduler, state_machine
    except ModuleNotFoundError as exc:
        pytest.skip(f"FastAPI test dependencies unavailable: {exc}")

    dag_engine.nodes.clear()
    dag_engine.graph.clear()
    state_machine.states.clear()
    state_machine.history.clear()
    event_bus.clear()
    scheduler.tasks.clear()
    scheduler.execution_queue.clear()
    scheduler.running_tasks.clear()
    scheduler.completed_tasks.clear()
    yield TestClient(app)


@pytest.fixture
def workflow_components():
    """Create fresh core workflow components."""
    from agentManager.engine.dag import DAGEngine
    from agentManager.engine.event_bus import EventBus
    from agentManager.engine.scheduler import SchedulerEngine
    from agentManager.engine.state_manager import StateMachine

    return {
        "dag": DAGEngine(),
        "state": StateMachine(),
        "events": EventBus(max_events=100),
        "scheduler": SchedulerEngine(max_concurrent_tasks=3),
    }
