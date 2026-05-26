"""Fixtures for end-to-end tests built from currently implemented modules."""

import pytest
from fastapi.testclient import TestClient

from agentManager.api import app, dag_engine, event_bus, scheduler, state_machine
from agentManager.engine.dag import DAGEngine
from agentManager.engine.event_bus import EventBus
from agentManager.engine.scheduler import SchedulerEngine
from agentManager.engine.state_manager import StateMachine


@pytest.fixture
def api_client():
    """Create an isolated API test client."""
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
    return {
        "dag": DAGEngine(),
        "state": StateMachine(),
        "events": EventBus(max_events=100),
        "scheduler": SchedulerEngine(max_concurrent_tasks=3),
    }
