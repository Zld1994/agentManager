"""Tests for agent selection flow in task plan API."""

import pytest
from fastapi.testclient import TestClient

from agentManager.agents.registry import AgentRegistry
from agentManager.api import app, _task_plans, dag_engine, event_bus, scheduler, state_machine
from agentManager.domain.agent_config import AgentTemplateRef


@pytest.fixture
def client():
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_engines():
    dag_engine.nodes.clear()
    dag_engine.graph.clear()
    state_machine.states.clear()
    state_machine.history.clear()
    event_bus.clear()
    scheduler.tasks.clear()
    scheduler.execution_queue.clear()
    scheduler.running_tasks.clear()
    scheduler.completed_tasks.clear()
    _task_plans.clear()
    yield


def _plan_payload(plan_id="plan-1", items=None, **kwargs):
    if items is None:
        items = [{"id": "item-1", "title": "First item", "verification": "run tests"}]
    return {"plan_id": plan_id, "source_task_id": "task-1", "items": items, **kwargs}


class TestAgentSelectionFlow:
    """Agent selection flow: create, edit, confirm with temporary roles and assignees."""

    def test_create_plan_with_temporary_roles(self, client):
        payload = _plan_payload(
            temporary_roles=["data-analyst"],
            selected_templates=["task-planning"],
            preferred_assignees=["worker"],
        )
        resp = client.post("/task-plans", json=payload)
        assert resp.status_code == 201
        data = resp.json()
        assert data["temporary_roles"] == ["data-analyst"]
        assert data["selected_templates"] == ["task-planning"]
        assert data["preferred_assignees"] == ["worker"]

    def test_update_assignee_via_put(self, client):
        client.post("/task-plans", json=_plan_payload())
        new_items = [
            {
                "id": "item-1",
                "title": "Assigned item",
                "assignee": "worker",
                "required_skills": ["sandbox-execution"],
                "verification": "check output",
            }
        ]
        resp = client.put("/task-plans/plan-1", json={"items": new_items})
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"][0]["assignee"] == "worker"
        assert data["items"][0]["required_skills"] == ["sandbox-execution"]

    def test_confirm_freezes_selection(self, client):
        items = [
            {
                "id": "a",
                "title": "Task A",
                "assignee": "worker",
                "verification": "verify A",
            }
        ]
        client.post("/task-plans", json=_plan_payload(items=items))
        resp = client.post("/task-plans/plan-1/confirm")
        assert resp.status_code == 200
        confirmed = resp.json()
        assert confirmed["status"] == "confirmed"
        assert confirmed["items"][0]["assignee"] == "worker"
        # Confirm is idempotent but already confirmed returns 409
        resp2 = client.post("/task-plans/plan-1/confirm")
        assert resp2.status_code == 409

    def test_registry_resolves_default_agent(self):
        registry = AgentRegistry(include_defaults=True)
        resolved = registry.resolve_agent("worker")
        assert resolved is not None
        assert resolved.profile.agent_id == "worker"
        assert len(resolved.resolved_skills) > 0

    def test_registry_resolve_missing_agent_returns_none(self):
        registry = AgentRegistry(include_defaults=True)
        assert registry.resolve_agent("nonexistent") is None

    def test_registry_validate_template_refs(self):
        registry = AgentRegistry(include_defaults=True)
        ok, errors = registry.validate_template_refs(
            [AgentTemplateRef(kind="skill", name="task-planning", required=True)]
        )
        assert ok is True
        assert errors == []

    def test_registry_validate_missing_template_refs(self):
        registry = AgentRegistry(include_defaults=True)
        ok, errors = registry.validate_template_refs(
            [AgentTemplateRef(kind="skill", name="not-found", required=True)]
        )
        assert ok is False
        assert len(errors) == 1
        assert "not-found" in errors[0]
