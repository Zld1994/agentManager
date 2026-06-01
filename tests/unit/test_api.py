"""Unit tests for FastAPI application."""

import importlib
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from agentManager.api import app, dag_engine, state_machine, event_bus, scheduler


@pytest.fixture
def client():
    """Create test client."""
    return TestClient(app)


@pytest.fixture(autouse=True)
def reset_engines():
    """Reset all engines before each test."""
    dag_engine.nodes.clear()
    dag_engine.graph.clear()
    state_machine.states.clear()
    state_machine.history.clear()
    event_bus.clear()
    scheduler.tasks.clear()
    scheduler.execution_queue.clear()
    scheduler.running_tasks.clear()
    scheduler.completed_tasks.clear()
    yield


class TestApplicationStartup:
    """Test application import and package startup paths."""

    def test_api_app_imports_in_subprocess(self):
        """Verify the documented startup import command succeeds."""
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                'from agentManager.api import app; print("OK")',
            ],
            check=False,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout.strip().splitlines()

    @pytest.mark.parametrize(
        "module_name",
        [
            "agentManager.engine",
            "agentManager.engine.event_bus",
            "agentManager.memory",
            "agentManager.recovery",
            "agentManager.runtime",
            "agentManager.sandbox",
            "agentManager.defect_repair",
            "agentManager.roles",
            "agentManager.scheduler",
        ],
    )
    def test_required_subpackages_are_importable(self, module_name):
        """Verify package discovery targets remain importable."""
        assert importlib.import_module(module_name).__name__ == module_name


class TestHealthEndpoint:
    """Test health check endpoint."""

    def test_health_check(self, client, monkeypatch):
        """Test health check returns ok."""
        monkeypatch.delenv("DATABASE_URL", raising=False)
        monkeypatch.delenv("REDIS_URL", raising=False)
        response = client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "0.1.0"
        assert "timestamp" in data
        assert data["dependencies"] == {}

    def test_health_check_reports_degraded_dependency_without_strict(self, client, monkeypatch):
        """Configured dependencies should degrade health without failing default checks."""
        monkeypatch.setenv("DATABASE_URL", "postgresql://localhost/db")

        with patch("agentManager.api._check_postgres_dependency", return_value="degraded"):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["dependencies"] == {"postgres": "degraded"}

    def test_health_check_strict_returns_503_for_degraded_dependency(self, client, monkeypatch):
        """Strict checks should be usable by load balancers."""
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")

        with patch("agentManager.api._check_redis_dependency", return_value="degraded"):
            response = client.get("/health?strict=true")

        assert response.status_code == 503
        data = response.json()
        assert data["status"] == "unhealthy"
        assert data["dependencies"] == {"redis": "degraded"}

    def test_fastapi_instrumentation_is_optional(self):
        """Missing optional instrumentation package should not break API startup."""
        fake_app = MagicMock()

        with patch.dict("sys.modules", {"opentelemetry.instrumentation.fastapi": None}):
            from agentManager.api import _instrument_fastapi_app

            assert _instrument_fastapi_app(fake_app) is False

    def test_status_endpoint(self, client):
        """Test status endpoint."""
        response = client.get("/status")
        assert response.status_code == 200
        data = response.json()
        assert "total_tasks" in data
        assert "running_tasks" in data
        assert "completed_tasks" in data

    def test_request_id_header_is_preserved(self, client):
        """API responses should include the incoming request correlation ID."""
        response = client.get("/health", headers={"X-Request-ID": "req-123"})

        assert response.status_code == 200
        assert response.headers["X-Request-ID"] == "req-123"


class TestTaskCreation:
    """Test task creation endpoints."""

    def test_create_task(self, client):
        """Test creating a task."""
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "data_processing",
                "dependencies": [],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert data["node_id"] == "task_1"
        assert data["task_type"] == "data_processing"
        assert data["status"] == "pending"

    def test_create_task_adds_request_id_to_event_payload(self, client):
        """Task creation events should carry request correlation IDs."""
        response = client.post(
            "/tasks",
            headers={"X-Request-ID": "req-abc"},
            json={
                "node_id": "task_1",
                "task_type": "data_processing",
                "dependencies": [],
            },
        )

        assert response.status_code == 201
        assert event_bus.events[-1].payload["correlation_id"] == "req-abc"

    def test_create_task_with_dependencies(self, client):
        """Test creating task with dependencies."""
        # Create first task
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )

        # Create second task with dependency
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_2",
                "task_type": "type2",
                "dependencies": ["task_1"],
            },
        )
        assert response.status_code == 201
        data = response.json()
        assert "task_1" in data["dependencies"]

    def test_create_task_with_invalid_dependency(self, client):
        """Test creating task with nonexistent dependency."""
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
                "dependencies": ["task_999"],
            },
        )
        assert response.status_code == 400
        assert "not found" in response.json()["detail"]
        assert "task_1" not in dag_engine.nodes

    def test_create_task_rejects_invalid_node_id(self, client):
        """Test node ID validation."""
        response = client.post(
            "/tasks",
            json={
                "node_id": "bad id",
                "task_type": "type1",
            },
        )
        assert response.status_code == 422

    def test_create_task_deduplicates_dependencies(self, client):
        """Test dependency validation removes duplicates."""
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_2",
                "task_type": "type2",
                "dependencies": ["task_1", "task_1"],
            },
        )
        assert response.status_code == 201
        assert response.json()["dependencies"] == ["task_1"]

    def test_create_task_with_cycle(self, client):
        """Test that creating cycle is prevented."""
        # Create task_1
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )

        # Create task_2 depending on task_1
        client.post(
            "/tasks",
            json={
                "node_id": "task_2",
                "task_type": "type2",
                "dependencies": ["task_1"],
            },
        )

        # Try to create cycle: task_1 depends on task_2
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
                "dependencies": ["task_2"],
            },
        )
        # Should fail because task_1 already exists
        assert response.status_code == 400


class TestTaskRetrieval:
    """Test task retrieval endpoints."""

    def test_get_task(self, client):
        """Test getting task information."""
        # Create task
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )

        # Get task
        response = client.get("/tasks/task_1")
        assert response.status_code == 200
        data = response.json()
        assert data["node_id"] == "task_1"
        assert data["task_type"] == "type1"

    def test_get_nonexistent_task(self, client):
        """Test getting nonexistent task."""
        response = client.get("/tasks/task_999")
        assert response.status_code == 404

    def test_get_ready_tasks_empty(self, client):
        """Test getting ready tasks when none exist."""
        response = client.get("/tasks/ready")
        assert response.status_code == 200
        data = response.json()
        assert data["ready_tasks"] == []
        assert data["total_tasks"] == 0

    def test_get_ready_tasks_with_no_dependencies(self, client):
        """Test getting ready tasks with no dependencies."""
        # Create task with no dependencies
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )

        response = client.get("/tasks/ready")
        assert response.status_code == 200
        data = response.json()
        assert "task_1" in data["ready_tasks"]

    def test_get_ready_tasks_with_pending_dependencies(self, client):
        """Test that tasks with pending dependencies are not ready."""
        # Create task_1
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )

        # Create task_2 depending on task_1
        client.post(
            "/tasks",
            json={
                "node_id": "task_2",
                "task_type": "type2",
                "dependencies": ["task_1"],
            },
        )

        response = client.get("/tasks/ready")
        data = response.json()
        assert "task_1" in data["ready_tasks"]
        assert "task_2" not in data["ready_tasks"]

    def test_get_ready_tasks_handles_internal_error(self, client, monkeypatch):
        """Test get ready tasks returns a controlled 500 response."""

        def fail():
            raise RuntimeError("boom")

        monkeypatch.setattr(dag_engine, "get_ready_nodes", fail)

        response = client.get("/tasks/ready")
        assert response.status_code == 500
        assert response.json()["detail"] == "Failed to get ready tasks"


class TestTaskCompletion:
    """Test task completion endpoints."""

    def test_complete_task(self, client):
        """Test completing a task."""
        # Create task
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )

        # Complete task
        response = client.post("/tasks/task_1/complete")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "completed"

    def test_complete_nonexistent_task(self, client):
        """Test completing nonexistent task."""
        response = client.post("/tasks/task_999/complete")
        assert response.status_code == 404

    def test_fail_task(self, client):
        """Test failing a task."""
        # Create task
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )

        # Fail task
        response = client.post("/tasks/task_1/fail?reason=test_failure")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "failed"

    def test_fail_nonexistent_task(self, client):
        """Test failing nonexistent task."""
        response = client.post("/tasks/task_999/fail")
        assert response.status_code == 404
