"""
Unit tests for WorkerSandbox - Docker-based execution sandbox.

Tests cover:
- Container creation with security hardening
- Command execution with stdout/stderr separation
- Resource limits enforcement
- Container lifecycle management
"""

import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch
from agentManager.sandbox.worker_sandbox import WorkerSandbox, SandboxConfig


TEST_WORKSPACE_ROOT = Path(".test-artifacts") / "worker-sandbox-unit"


@pytest.fixture
def sandbox_config():
    """Create a test SandboxConfig."""
    return SandboxConfig(
        worker_id="test-worker-1",
        image="python:3.10-slim",
        cpu_limit=1.0,
        memory_limit="512m",
        timeout=300,
    )


@pytest.fixture
def mock_docker_client():
    """Create a mock Docker client."""
    with patch("agentManager.sandbox.worker_sandbox.docker.from_env") as mock:
        yield mock.return_value


@pytest.fixture
def sandbox(sandbox_config, mock_docker_client):
    """Create a WorkerSandbox instance with mocked Docker."""
    return WorkerSandbox(sandbox_config)


class TestSandboxConfig:
    """Test SandboxConfig dataclass."""

    def test_config_creation(self, sandbox_config):
        """Test basic config creation."""
        assert sandbox_config.worker_id == "test-worker-1"
        assert sandbox_config.image == "python:3.10-slim"
        assert sandbox_config.cpu_limit == 1.0
        assert sandbox_config.memory_limit == "512m"
        assert sandbox_config.timeout == 300

    def test_config_with_volumes(self):
        """Test config with volumes."""
        volumes = {"/data": {"bind": "/data", "mode": "rw"}}
        config = SandboxConfig(
            worker_id="test-2",
            volumes=volumes,
        )
        assert config.volumes == volumes

    def test_config_with_environment(self):
        """Test config with environment variables."""
        env = {"VAR1": "value1", "VAR2": "value2"}
        config = SandboxConfig(
            worker_id="test-3",
            environment=env,
        )
        assert config.environment == env

    def test_config_creates_per_task_workspace(self):
        """Test each task gets an isolated workspace under the sandbox root."""
        config = SandboxConfig(worker_id="worker-1", task_id="task-42")
        config.workspace_root = TEST_WORKSPACE_ROOT

        workspace = config.task_workspace_path

        assert workspace == (
            TEST_WORKSPACE_ROOT / "worker-1" / "task-42"
        ).resolve()

    def test_config_rejects_task_workspace_escape(self):
        """Test task identifiers cannot escape the workspace root."""
        config = SandboxConfig(worker_id="worker-1", task_id="..\\escape")
        config.workspace_root = TEST_WORKSPACE_ROOT

        with pytest.raises(ValueError, match="task workspace"):
            _ = config.task_workspace_path

    def test_config_rejects_image_outside_allow_list(self):
        """Test production policy rejects images outside the allow list."""
        config = SandboxConfig(
            worker_id="worker-1",
            image="ubuntu:latest",
            allowed_images=("python:3.10-slim",),
        )

        with pytest.raises(ValueError, match="not allowed"):
            config.validate_policy()

    def test_config_rejects_denied_mount_path(self):
        """Test denied host mounts are rejected before container creation."""
        denied = TEST_WORKSPACE_ROOT / "denied"
        config = SandboxConfig(
            worker_id="worker-1",
            volumes={str(denied): {"bind": "/workspace", "mode": "rw"}},
            denied_mounts=(str(denied),),
        )

        with pytest.raises(ValueError, match="denied mount"):
            config.validate_policy()

    def test_config_rejects_writable_mount_outside_task_workspace(self):
        """Test writable mounts must stay inside the per-task workspace."""
        outside = TEST_WORKSPACE_ROOT / "outside"
        config = SandboxConfig(
            worker_id="worker-1",
            task_id="task-42",
            workspace_root=TEST_WORKSPACE_ROOT / "root",
            volumes={str(outside): {"bind": "/outside", "mode": "rw"}},
        )

        with pytest.raises(ValueError, match="outside task workspace"):
            config.validate_policy()


class TestContainerCreation:
    """Test container creation with security hardening."""

    def test_create_container_basic(self, sandbox, mock_docker_client):
        """Test basic container creation."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()

        assert sandbox.container == mock_container
        mock_docker_client.containers.create.assert_called_once()

    def test_create_container_security_options(self, sandbox, mock_docker_client):
        """Test that security options are applied."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()

        call_kwargs = mock_docker_client.containers.create.call_args[1]

        # Verify security options
        assert call_kwargs["network_disabled"] is True
        assert call_kwargs["read_only"] is True
        assert call_kwargs["cap_drop"] == ["ALL"]
        assert call_kwargs["security_opt"] == ["no-new-privileges:true"]
        assert call_kwargs["pids_limit"] == 256

    def test_create_container_resource_limits(self, sandbox, mock_docker_client):
        """Test that resource limits are applied."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()

        call_kwargs = mock_docker_client.containers.create.call_args[1]

        # Verify resource limits
        assert call_kwargs["cpu_quota"] == 100000  # 1.0 * 100000
        assert call_kwargs["cpu_period"] == 100000
        assert call_kwargs["mem_limit"] == "512m"
        assert call_kwargs["memswap_limit"] == "512m"

    def test_create_container_with_volumes(self, sandbox_config, mock_docker_client):
        """Test container creation with additional read-only volumes."""
        host_data = TEST_WORKSPACE_ROOT / "data"
        volumes = {str(host_data): {"bind": "/data", "mode": "ro"}}
        sandbox_config.volumes = volumes
        sandbox = WorkerSandbox(sandbox_config)

        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()

        call_kwargs = mock_docker_client.containers.create.call_args[1]
        assert call_kwargs["volumes"][str(host_data)] == {
            "bind": "/data",
            "mode": "ro",
        }

    def test_create_container_with_environment(self, sandbox_config, mock_docker_client):
        """Test container creation with environment variables."""
        env = {"VAR1": "value1"}
        sandbox_config.environment = env
        sandbox = WorkerSandbox(sandbox_config)

        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()

        call_kwargs = mock_docker_client.containers.create.call_args[1]
        assert call_kwargs["environment"] == env

    def test_create_container_mounts_task_workspace(self, mock_docker_client):
        """Test container creation mounts only the isolated task workspace writable."""
        config = SandboxConfig(
            worker_id="worker-1",
            task_id="task-42",
            workspace_root=TEST_WORKSPACE_ROOT,
        )
        sandbox = WorkerSandbox(config)
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()

        workspace = str(config.task_workspace_path)
        call_kwargs = mock_docker_client.containers.create.call_args[1]
        assert call_kwargs["working_dir"] == config.container_workspace
        assert call_kwargs["volumes"][workspace] == {
            "bind": config.container_workspace,
            "mode": "rw",
        }

    def test_create_container_applies_container_policy(
        self,
        sandbox_config,
        mock_docker_client,
    ):
        """Test configurable production container policy is passed to Docker."""
        sandbox_config.network_mode = "none"
        sandbox_config.pids_limit = 128
        sandbox_config.read_only_rootfs = True
        sandbox = WorkerSandbox(sandbox_config)
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()

        call_kwargs = mock_docker_client.containers.create.call_args[1]
        assert call_kwargs["network_mode"] == "none"
        assert call_kwargs["pids_limit"] == 128
        assert call_kwargs["read_only"] is True


class TestContainerExecution:
    """Test command execution in container."""

    def test_exec_in_basic(self, sandbox, mock_docker_client):
        """Test basic command execution."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        # Mock exec_run to return (exit_code, (stdout, stderr))
        mock_container.exec_run.return_value = (
            0,
            (b"hello world", b""),
        )

        sandbox.create_container()
        exit_code, stdout, stderr = sandbox.exec_in("echo hello")

        assert exit_code == 0
        assert stdout == "hello world"
        assert stderr == ""

    def test_exec_in_with_stderr(self, sandbox, mock_docker_client):
        """Test command execution with stderr output."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        mock_container.exec_run.return_value = (
            1,
            (b"output", b"error message"),
        )

        sandbox.create_container()
        exit_code, stdout, stderr = sandbox.exec_in("false")

        assert exit_code == 1
        assert stdout == "output"
        assert stderr == "error message"

    def test_exec_in_demux_enabled(self, sandbox, mock_docker_client):
        """Test that demux=True is used for stdout/stderr separation."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_container.exec_run.return_value = (0, (b"", b""))

        sandbox.create_container()
        sandbox.exec_in("test command")

        call_kwargs = mock_container.exec_run.call_args[1]
        assert call_kwargs["demux"] is True
        assert call_kwargs["stdout"] is True
        assert call_kwargs["stderr"] is True

    def test_exec_in_utf8_handling(self, sandbox, mock_docker_client):
        """Test UTF-8 encoding handling."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        # Test with UTF-8 characters
        mock_container.exec_run.return_value = (
            0,
            ("你好世界".encode("utf-8"), "错误".encode("utf-8")),
        )

        sandbox.create_container()
        exit_code, stdout, stderr = sandbox.exec_in("test")

        assert stdout == "你好世界"
        assert stderr == "错误"

    def test_exec_in_invalid_utf8_handling(self, sandbox, mock_docker_client):
        """Test handling of invalid UTF-8 sequences."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        # Invalid UTF-8 sequence
        mock_container.exec_run.return_value = (
            0,
            (b"\xff\xfe", b"\x80\x81"),
        )

        sandbox.create_container()
        exit_code, stdout, stderr = sandbox.exec_in("test")

        # Should not raise, should use replacement character
        assert isinstance(stdout, str)
        assert isinstance(stderr, str)

    def test_exec_in_empty_output(self, sandbox, mock_docker_client):
        """Test handling of empty output."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_container.exec_run.return_value = (0, (b"", b""))

        sandbox.create_container()
        exit_code, stdout, stderr = sandbox.exec_in("test")

        assert exit_code == 0
        assert stdout == ""
        assert stderr == ""

    def test_exec_in_none_output(self, sandbox, mock_docker_client):
        """Test handling of None output from exec_run."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_container.exec_run.return_value = (0, None)

        sandbox.create_container()
        exit_code, stdout, stderr = sandbox.exec_in("test")

        assert exit_code == 0
        assert stdout == ""
        assert stderr == ""

    def test_exec_for_task_reports_timeout_cleanup(self, sandbox, mock_docker_client):
        """Test timeout cleanup returns observable bounded cleanup status."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_container.exec_run.side_effect = TimeoutError("timed out")

        sandbox.create_container()
        result = sandbox.exec_for_task("sleep 30", timeout=1)

        assert result.exit_code == 124
        assert result.timed_out is True
        assert result.cleanup_status == "removed"
        assert "timed out" in result.stderr
        mock_container.kill.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)

    def test_exec_for_task_reports_cleanup_failure(self, sandbox, mock_docker_client):
        """Test timeout cleanup failures are returned instead of swallowed."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container
        mock_container.exec_run.side_effect = TimeoutError("timed out")
        mock_container.remove.side_effect = RuntimeError("remove denied")

        sandbox.create_container()
        result = sandbox.exec_for_task("sleep 30", timeout=1)

        assert result.exit_code == 124
        assert result.timed_out is True
        assert result.cleanup_status == "failed"
        assert "remove denied" in result.cleanup_error


class TestContainerLifecycle:
    """Test container lifecycle management."""

    def test_start_container(self, sandbox, mock_docker_client):
        """Test starting a container."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()
        sandbox.start_container()

        mock_container.start.assert_called_once()

    def test_stop_container(self, sandbox, mock_docker_client):
        """Test stopping a container."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()
        sandbox.stop_container()

        mock_container.stop.assert_called_once_with(timeout=10)

    def test_stop_container_with_timeout(self, sandbox, mock_docker_client):
        """Test stopping a container with custom timeout."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()
        sandbox.stop_container(timeout=30)

        mock_container.stop.assert_called_once_with(timeout=30)

    def test_remove_container(self, sandbox, mock_docker_client):
        """Test removing a container."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()
        sandbox.remove_container()

        mock_container.remove.assert_called_once_with(force=False)

    def test_remove_container_force(self, sandbox, mock_docker_client):
        """Test force removing a container."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()
        sandbox.remove_container(force=True)

        mock_container.remove.assert_called_once_with(force=True)

    def test_cleanup(self, sandbox, mock_docker_client):
        """Test cleanup sequence."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()
        sandbox.cleanup()

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once_with(force=True)


class TestContextManager:
    """Test context manager functionality."""

    def test_context_manager_enter_exit(self, sandbox, mock_docker_client):
        """Test context manager enter and exit."""
        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        with sandbox:
            mock_container.start.assert_called_once()

        mock_container.stop.assert_called_once()
        mock_container.remove.assert_called_once()
