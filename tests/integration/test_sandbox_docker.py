"""
Integration tests for WorkerSandbox with real Docker.

These tests require Docker to be running and are marked with @pytest.mark.integration.
They are skipped by default unless Docker is available.
"""

import shutil
import pytest
import tempfile
from pathlib import Path

from agentManager.sandbox.worker_sandbox import WorkerSandbox, SandboxConfig


def docker_available():
    """Check if Docker is available for testing (lightweight check)."""
    if not shutil.which("docker"):
        return False
    try:
        import docker
        client = docker.from_env()
        client.ping()
        return True
    except Exception:
        return False


@pytest.mark.integration
@pytest.mark.skipif(not docker_available(), reason="Docker not available")
class TestWorkerSandboxRealDocker:
    """Real Docker integration tests for WorkerSandbox."""

    @pytest.fixture
    def temp_workspace(self):
        """Create a temporary workspace directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def test_container_create_and_start(self, temp_workspace):
        """Test creating and starting a Docker container."""
        config = SandboxConfig(
            worker_id="test-worker-001",
            workspace_root=temp_workspace,
            timeout=60,
        )

        with WorkerSandbox(config) as sandbox:
            assert sandbox.container is not None
            sandbox.container.reload()
            assert sandbox.container.status == "running"

    def test_command_execution(self, temp_workspace):
        """Test executing a simple command in the container."""
        config = SandboxConfig(
            worker_id="test-worker-002",
            workspace_root=temp_workspace,
            timeout=60,
        )

        with WorkerSandbox(config) as sandbox:
            exit_code, stdout, stderr = sandbox.exec_in("echo 'hello world'")

            assert exit_code == 0
            assert "hello world" in stdout
            assert stderr == ""

    def test_command_with_stderr(self, temp_workspace):
        """Test executing a command that produces stderr."""
        config = SandboxConfig(
            worker_id="test-worker-003",
            workspace_root=temp_workspace,
            timeout=60,
        )

        with WorkerSandbox(config) as sandbox:
            exit_code, stdout, stderr = sandbox.exec_in(">&2 echo 'error message'")

            assert exit_code == 0
            assert "error message" in stderr

    def test_failing_command(self, temp_workspace):
        """Test executing a command that returns non-zero exit code."""
        config = SandboxConfig(
            worker_id="test-worker-004",
            workspace_root=temp_workspace,
            timeout=60,
        )

        with WorkerSandbox(config) as sandbox:
            exit_code, stdout, stderr = sandbox.exec_in("false")

            assert exit_code != 0

    def test_workspace_isolation(self, temp_workspace):
        """Test that workspace isolation works correctly."""
        config = SandboxConfig(
            worker_id="test-worker-005",
            task_id="task-123",
            workspace_root=temp_workspace,
            timeout=60,
        )

        test_file = config.task_workspace_path / "test.txt"
        test_file.write_text("test content")

        with WorkerSandbox(config) as sandbox:
            exit_code, stdout, stderr = sandbox.exec_in("cat /workspace/test.txt")

            assert exit_code == 0
            assert "test content" in stdout

    def test_network_isolation(self, temp_workspace):
        """Test that network is disabled by default using socket."""
        config = SandboxConfig(
            worker_id="test-worker-006",
            workspace_root=temp_workspace,
            timeout=60,
            network_mode="none",
        )

        with WorkerSandbox(config) as sandbox:
            exit_code, stdout, stderr = sandbox.exec_in(
                "python3 -c \"import socket; s=socket.socket(); "
                "s.settimeout(2); s.connect(('8.8.8.8',53))\" 2>&1 || true"
            )

            assert exit_code != 0 or "network" in (stdout + stderr).lower() or "error" in (stdout + stderr).lower()

    def test_resource_limits(self, temp_workspace):
        """Test that resource limits are applied."""
        config = SandboxConfig(
            worker_id="test-worker-007",
            workspace_root=temp_workspace,
            timeout=60,
            cpu_limit=0.5,
            memory_limit="256m",
        )

        with WorkerSandbox(config) as sandbox:
            assert sandbox.container is not None

            inspect = sandbox.container.attrs
            assert inspect["HostConfig"]["Memory"] == 268435456
            assert inspect["HostConfig"]["CpuQuota"] == 50000

    def test_timeout_cleanup(self, temp_workspace):
        """Test timeout handling and cleanup."""
        config = SandboxConfig(
            worker_id="test-worker-008",
            workspace_root=temp_workspace,
            timeout=5,
        )

        with WorkerSandbox(config) as sandbox:
            result = sandbox.exec_for_task("sleep 30", timeout=2)

            assert result.timed_out
            assert result.exit_code == 124
            assert "timed out" in result.stderr

    def test_denied_mount(self, temp_workspace):
        """Test that denied mounts are blocked."""
        config = SandboxConfig(
            worker_id="test-worker-009",
            workspace_root=temp_workspace,
            timeout=60,
            volumes={
                "/var/run/docker.sock": {"bind": "/var/run/docker.sock", "mode": "ro"}
            },
        )

        with pytest.raises(ValueError, match="denied mount"):
            with WorkerSandbox(config) as sandbox:
                pass
