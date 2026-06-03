"""Unit tests for FastAPI application."""

import importlib
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from agentManager.api import app, dag_engine, state_machine, event_bus, scheduler
import agentManager.api as api_module
from agentManager.runtime.hooks import HookConfig, HookRunner


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
    api_module._task_plans.clear()
    api_module.hook_runner = HookRunner()
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

    def test_api_startup_configures_runtime_audit_sinks(self):
        """Importing the API should wire audit sinks from runtime settings."""
        code = (
            "from unittest.mock import patch\n"
            "target = 'agentManager.runtime.factory.configure_runtime_audit_sinks'\n"
            "with patch(target) as configure:\n"
            "    from agentManager.api import app\n"
            "    assert app is not None\n"
            "    configure.assert_called_once()\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
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
        monkeypatch.delenv("REDIS_URL", raising=False)

        with patch("agentManager.api._check_postgres_dependency", return_value="degraded"):
            response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "degraded"
        assert data["dependencies"] == {"postgres": "degraded"}

    def test_health_check_strict_returns_503_for_degraded_dependency(self, client, monkeypatch):
        """Strict checks should be usable by load balancers."""
        monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
        monkeypatch.delenv("DATABASE_URL", raising=False)

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
        with patch.object(event_bus, "publish", wraps=event_bus.publish) as mock_publish:
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
        mock_publish.assert_called_once()
        published_event = mock_publish.call_args[0][0]
        assert published_event.payload["correlation_id"] == "req-abc"

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


class TestSecurityHeaders:

    def test_security_headers_present(self, client):
        response = client.get("/health")
        assert response.status_code == 200
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_security_headers_on_404(self, client):
        response = client.get("/nonexistent")
        assert response.status_code == 404
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"

    def test_security_headers_on_post(self, client):
        response = client.post(
            "/tasks",
            json={"node_id": "t1", "task_type": "type1", "dependencies": []},
        )
        assert response.status_code == 201
        assert response.headers["X-Content-Type-Options"] == "nosniff"
        assert response.headers["X-Frame-Options"] == "DENY"
        assert response.headers["Referrer-Policy"] == "strict-origin-when-cross-origin"


class TestAPIAuthentication:

    def test_auth_disabled_by_default(self, client):
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "data_processing",
                "dependencies": [],
            },
        )
        assert response.status_code == 201

    def test_auth_enabled_requires_token(self, client, monkeypatch):
        monkeypatch.setattr(
            "agentManager.api._auth_settings",
            {"auth_enabled": True, "auth_token": "test-secret"},
        )
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "data_processing",
                "dependencies": [],
            },
        )
        assert response.status_code == 401

    def test_auth_enabled_valid_token(self, client, monkeypatch):
        monkeypatch.setattr(
            "agentManager.api._auth_settings",
            {"auth_enabled": True, "auth_token": "test-secret"},
        )
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "data_processing",
                "dependencies": [],
            },
            headers={"Authorization": "Bearer test-secret"},
        )
        assert response.status_code == 201

    def test_auth_enabled_invalid_token(self, client, monkeypatch):
        monkeypatch.setattr(
            "agentManager.api._auth_settings",
            {"auth_enabled": True, "auth_token": "test-secret"},
        )
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "data_processing",
                "dependencies": [],
            },
            headers={"Authorization": "Bearer wrong-token"},
        )
        assert response.status_code == 401

    def test_health_endpoint_no_auth_required(self, client, monkeypatch):
        monkeypatch.setattr(
            "agentManager.api._auth_settings",
            {"auth_enabled": True, "auth_token": "test-secret"},
        )
        response = client.get("/health")
        assert response.status_code == 200

    def test_auth_enabled_missing_bearer_prefix_rejected(self, client, monkeypatch):
        monkeypatch.setattr(
            "agentManager.api._auth_settings",
            {"auth_enabled": True, "auth_token": "test-secret"},
        )
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "data_processing",
                "dependencies": [],
            },
            headers={"Authorization": "test-secret"},
        )
        assert response.status_code == 401


class TestDocsDisabled:

    def test_docs_enabled_by_default(self, client):
        response = client.get("/docs")
        assert response.status_code == 200

    def test_docs_disabled_via_env(self):
        code = (
            "import os\n"
            "os.environ['DOCS_ENABLED'] = 'false'\n"
            "from fastapi.testclient import TestClient\n"
            "from agentManager.api import app\n"
            "client = TestClient(app)\n"
            "r = client.get('/docs')\n"
            "assert r.status_code == 404, f'Expected 404 for /docs, got {r.status_code}'\n"
            "r = client.get('/redoc')\n"
            "assert r.status_code == 404, f'Expected 404 for /redoc, got {r.status_code}'\n"
            "r = client.get('/openapi.json')\n"
            "assert r.status_code == 404, f'Expected 404 for /openapi.json, got {r.status_code}'\n"
            "print('OK')\n"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            check=False,
            capture_output=True,
            text=True,
        )
        assert result.returncode == 0, result.stderr
        assert "OK" in result.stdout.strip().splitlines()


class TestRequestBodySizeLimit:

    def test_normal_request_body_accepted(self, client):
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "data_processing",
                "dependencies": [],
            },
        )
        assert response.status_code == 201

    def test_oversized_request_body_rejected(self, client, monkeypatch):
        monkeypatch.setenv("MAX_REQUEST_BODY_SIZE", "10")
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_with_a_very_long_name_to_exceed_limit",
                "task_type": "data_processing",
                "dependencies": [],
            },
        )
        assert response.status_code == 413

    def test_get_request_not_blocked_by_small_limit(self, client, monkeypatch):
        monkeypatch.setenv("MAX_REQUEST_BODY_SIZE", "1")
        response = client.get("/health")
        assert response.status_code == 200

    def test_content_length_at_limit_passes(self, client, monkeypatch):
        monkeypatch.setenv("MAX_REQUEST_BODY_SIZE", "1048576")
        response = client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
                "dependencies": [],
            },
        )
        assert response.status_code == 201


class TestInternalErrorNoLeak:

    def test_create_task_internal_error_generic_message(self, client):
        with patch.object(
            dag_engine, "add_node", side_effect=RuntimeError("database connection lost")
        ):
            response = client.post(
                "/tasks",
                json={
                    "node_id": "task_1",
                    "task_type": "data_processing",
                    "dependencies": [],
                },
            )
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"

    def test_complete_task_internal_error_generic_message(self, client):
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )
        with patch.object(dag_engine, "update_node_status", side_effect=RuntimeError("disk full")):
            response = client.post("/tasks/task_1/complete")
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"

    def test_fail_task_internal_error_generic_message(self, client):
        client.post(
            "/tasks",
            json={
                "node_id": "task_1",
                "task_type": "type1",
            },
        )
        with patch.object(dag_engine, "update_node_status", side_effect=RuntimeError("disk full")):
            response = client.post("/tasks/task_1/fail?reason=test")
        assert response.status_code == 500
        assert response.json()["detail"] == "Internal server error"


class TestMetricsEndpoint:

    def test_metrics_endpoint_exists(self, client):
        response = client.get("/metrics")
        assert response.status_code == 200

    def test_metrics_endpoint_with_auth(self, client, monkeypatch):
        monkeypatch.setattr(
            "agentManager.api._auth_settings",
            {"auth_enabled": True, "auth_token": "test-secret"},
        )
        response = client.get("/metrics")
        assert response.status_code == 401


class TestRedisURLMasking:

    def test_mask_url_with_credentials(self):
        from agentManager.engine.event_bus.redis_stream import _mask_url

        assert _mask_url("redis://user:password@localhost:6379/0") == "redis://***@localhost:6379/0"

    def test_mask_url_without_credentials(self):
        from agentManager.engine.event_bus.redis_stream import _mask_url

        assert _mask_url("redis://localhost:6379/0") == "redis://localhost:6379/0"

    def test_mask_url_without_scheme(self):
        from agentManager.engine.event_bus.redis_stream import _mask_url

        assert _mask_url("localhost:6379") == "localhost:6379"

    def test_mask_url_with_at_in_password(self):
        from agentManager.engine.event_bus.redis_stream import _mask_url

        assert (
            _mask_url("redis://admin:p@ss@redis.example.com:6379")
            == "redis://***@redis.example.com:6379"
        )

    def test_mask_url_rediss_scheme(self):
        from agentManager.engine.event_bus.redis_stream import _mask_url

        assert _mask_url("rediss://user:secret@host:6379") == "rediss://***@host:6379"

    def test_mask_url_empty_string(self):
        from agentManager.engine.event_bus.redis_stream import _mask_url

        assert _mask_url("") == ""


class TestTaskPlanReviewFlow:
    def test_list_task_plans_returns_review_summaries(self, client):
        for plan_id, source_task_id in [
            ("plan-alpha", "task-alpha"),
            ("plan-beta", "task-beta"),
        ]:
            response = client.post(
                "/task-plans",
                json={
                    "plan_id": plan_id,
                    "source_task_id": source_task_id,
                    "items": [
                        {
                            "id": f"{plan_id}-item",
                            "title": f"Review {plan_id}",
                            "verification": "Run focused verification",
                        },
                    ],
                },
            )
            assert response.status_code == 201

        response = client.get("/task-plans")

        assert response.status_code == 200
        data = response.json()
        assert data["total"] == 2
        summaries = {plan["plan_id"]: plan for plan in data["task_plans"]}
        assert summaries["plan-alpha"]["source_task_id"] == "task-alpha"
        assert summaries["plan-alpha"]["status"] == "draft"
        assert summaries["plan-alpha"]["items_count"] == 1
        assert "updated_at" in summaries["plan-alpha"]

    def test_list_task_plans_uses_api_auth(self, client, monkeypatch):
        monkeypatch.setattr(
            "agentManager.api._auth_settings",
            {"auth_enabled": True, "auth_token": "test-secret"},
        )

        response = client.get("/task-plans")

        assert response.status_code == 401

    def test_create_task_plan_rejects_duplicate_item_ids(self, client):
        response = client.post(
            "/task-plans",
            json={
                "plan_id": "plan-dup",
                "items": [
                    {"id": "item-1", "title": "First", "verification": "check first"},
                    {"id": "item-1", "title": "Second", "verification": "check second"},
                ],
            },
        )

        assert response.status_code == 400
        assert "Duplicate task plan item id" in response.json()["detail"]

    def test_confirm_task_plan_runs_before_and_after_hooks(self, client, monkeypatch):
        calls = []

        class RecordingHookRunner:
            def run_hooks(self, event, context=None):
                calls.append((event, context))
                return {}

        monkeypatch.setattr(api_module, "hook_runner", RecordingHookRunner())
        client.post(
            "/task-plans",
            json={
                "plan_id": "plan-hook",
                "source_task_id": "task-1",
                "items": [
                    {"id": "item-1", "title": "First", "verification": "check first"},
                ],
            },
        )

        response = client.post("/task-plans/plan-hook/confirm")

        assert response.status_code == 200
        assert [call[0] for call in calls] == [
            "before_task_plan_confirm",
            "after_task_plan_confirm",
        ]
        assert calls[0][1]["plan_id"] == "plan-hook"
        assert calls[0][1]["source_task_id"] == "task-1"

    def test_confirm_task_plan_blocks_when_before_hook_fails(self, client, monkeypatch):
        failing_hook = HookConfig(
            name="reject",
            event="before_task_plan_confirm",
            command="false",
            enabled=True,
        )
        monkeypatch.setenv("HOOKS_ENABLED", "true")
        monkeypatch.setattr(api_module, "hook_runner", HookRunner([failing_hook]))
        client.post(
            "/task-plans",
            json={
                "plan_id": "plan-fail-hook",
                "items": [
                    {"id": "item-1", "title": "First", "verification": "check first"},
                ],
            },
        )

        response = client.post("/task-plans/plan-fail-hook/confirm")

        assert response.status_code == 500
        assert response.json()["detail"] == "Task plan confirmation hook failed"
        assert api_module._task_plans["plan-fail-hook"].status.value == "draft"
        events = event_bus.get_events(event_type=api_module.EventType.TASK_PLAN_CONFIRM_FAILED)
        assert len(events) == 1
        assert events[0].payload["plan_id"] == "plan-fail-hook"

    def test_create_task_plan_publishes_after_releasing_plan_lock(self, client):
        def callback(_event):
            assert api_module._task_plans_lock.acquire(blocking=False)
            api_module._task_plans_lock.release()

        event_bus.subscribe(api_module.EventType.TASK_PLAN_CREATED, callback)

        response = client.post(
            "/task-plans",
            json={
                "plan_id": "plan-lock",
                "items": [
                    {"id": "item-1", "title": "First", "verification": "check first"},
                ],
            },
        )

        assert response.status_code == 201


class TestUIStaticMount:
    def test_mount_ui_serves_index_and_spa_routes(self, tmp_path):
        dist_dir = tmp_path / "dist"
        dist_dir.mkdir()
        (dist_dir / "index.html").write_text(
            "<!doctype html><title>agentManager Workbench</title>",
            encoding="utf-8",
        )

        ui_app = FastAPI()
        mounted = api_module._mount_ui_app(ui_app, dist_dir=dist_dir, enabled=True)
        client = TestClient(ui_app)

        assert mounted is True
        root_response = client.get("/ui/")
        assert root_response.status_code == 200
        assert "agentManager Workbench" in root_response.text
        route_response = client.get("/ui/task-plans/plan-alpha")
        assert route_response.status_code == 200
        assert "agentManager Workbench" in route_response.text

    def test_mount_ui_skips_missing_dist_without_breaking_api(self, tmp_path):
        ui_app = FastAPI()

        mounted = api_module._mount_ui_app(
            ui_app,
            dist_dir=tmp_path / "missing-dist",
            enabled=True,
        )
        response = TestClient(ui_app).get("/ui/")

        assert mounted is False
        assert response.status_code == 404
