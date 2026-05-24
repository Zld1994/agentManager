"""
Unit tests for WorkerSandbox - Docker-based execution sandbox.

Tests cover:
- Container creation with security hardening
- Command execution with stdout/stderr separation
- Resource limits enforcement
- Container lifecycle management
"""

import pytest
from unittest.mock import MagicMock, patch
from agentManager.sandbox.worker_sandbox import WorkerSandbox, SandboxConfig


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
        """Test container creation with volumes."""
        volumes = {"/data": {"bind": "/data", "mode": "rw"}}
        sandbox_config.volumes = volumes
        sandbox = WorkerSandbox(sandbox_config)

        mock_container = MagicMock()
        mock_docker_client.containers.create.return_value = mock_container

        sandbox.create_container()

        call_kwargs = mock_docker_client.containers.create.call_args[1]
        assert call_kwargs["volumes"] == volumes

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
