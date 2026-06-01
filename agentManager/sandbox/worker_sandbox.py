"""
WorkerSandbox - Docker-based execution sandbox for worker tasks.

Provides:
- Secure container creation with hardened security options
- Command execution with stdout/stderr separation
- Resource limits (CPU, memory, processes)
- Network isolation
"""

import logging
from pathlib import Path
from typing import Tuple, Optional, Dict
from dataclasses import dataclass

from agentManager.observability.tracing import create_span

try:
    import docker
    import docker.errors
except ImportError:
    class _DockerAPIError(Exception):
        """Fallback Docker API error when docker SDK is not installed."""

    class _DockerErrors:
        APIError = _DockerAPIError

    class _MissingDockerModule:
        errors = _DockerErrors

        @staticmethod
        def from_env():
            raise RuntimeError(
                "Docker SDK is not installed. Install agentManager with the "
                "'sandbox' extra to use WorkerSandbox."
            )

    docker = _MissingDockerModule()


logger = logging.getLogger(__name__)


@dataclass
class SandboxConfig:
    """Configuration for WorkerSandbox."""

    worker_id: str
    task_id: Optional[str] = None
    image: str = "python:3.10-slim"
    cpu_limit: float = 1.0  # CPU cores
    memory_limit: str = "512m"
    timeout: int = 300  # seconds
    volumes: Optional[Dict[str, Dict[str, str]]] = None
    environment: Optional[Dict[str, str]] = None
    workspace_root: Path | str = Path("test_tmp") / "sandbox"
    container_workspace: str = "/workspace"
    allowed_images: Tuple[str, ...] = ("python:3.10-slim",)
    denied_mounts: Tuple[str, ...] = ("/var/run/docker.sock",)
    network_mode: str = "none"
    pids_limit: int = 256
    read_only_rootfs: bool = True

    @property
    def task_workspace_path(self) -> Path:
        """Return the isolated host workspace for this task."""
        task_id = self.task_id or self.worker_id
        self._validate_path_component(self.worker_id, "worker_id")
        self._validate_path_component(task_id, "task_id")
        root = Path(self.workspace_root).resolve()
        workspace = (root / self.worker_id / task_id).resolve()

        if not workspace.is_relative_to(root):
            raise ValueError("Resolved task workspace escapes workspace root")

        return workspace

    @staticmethod
    def _validate_path_component(value: str, field_name: str) -> None:
        """Reject absolute or multi-part path components."""
        path = Path(value)
        if (
            path.is_absolute()
            or len(path.parts) != 1
            or "/" in value
            or "\\" in value
            or value in {".", ".."}
        ):
            raise ValueError(f"Invalid task workspace {field_name}: {value!r}")

    def validate_policy(self) -> None:
        """Validate sandbox image and mount policy before container creation."""
        if self.allowed_images and self.image not in self.allowed_images:
            raise ValueError(f"Sandbox image {self.image!r} is not allowed")

        workspace = self.task_workspace_path
        denied_paths = [Path(path).resolve() for path in self.denied_mounts]

        for host_path, mount in (self.volumes or {}).items():
            resolved_host = Path(host_path).resolve()

            if any(
                resolved_host == denied or resolved_host.is_relative_to(denied)
                for denied in denied_paths
            ):
                raise ValueError(f"Sandbox denied mount requested: {host_path}")

            mode = mount.get("mode", "rw").lower()
            if "rw" in mode and not (
                resolved_host == workspace or resolved_host.is_relative_to(workspace)
            ):
                raise ValueError(
                    f"Writable mount {host_path!r} is outside task workspace"
                )


@dataclass
class SandboxExecutionResult:
    """Result for sandbox command execution with cleanup observability."""

    exit_code: int
    stdout: str
    stderr: str
    timed_out: bool = False
    cleanup_status: str = "not_needed"
    cleanup_error: str = ""


class WorkerSandbox:
    """
    Docker-based execution sandbox with security hardening.

    Security features:
    - Network disabled by default
    - Read-only root filesystem
    - All capabilities dropped
    - No new privileges
    - Process count limited to 256
    """

    def __init__(self, config: SandboxConfig):
        """
        Initialize WorkerSandbox.

        Args:
            config: SandboxConfig instance
        """
        self.config = config
        self.docker_client = docker.from_env()
        self.container = None

    def _container_volumes(self) -> Dict[str, Dict[str, str]]:
        """Build validated volumes including the isolated task workspace."""
        self.config.validate_policy()
        workspace = self.config.task_workspace_path
        workspace.mkdir(parents=True, exist_ok=True)

        volumes = dict(self.config.volumes or {})
        volumes.setdefault(
            str(workspace),
            {"bind": self.config.container_workspace, "mode": "rw"},
        )
        return volumes

    def create_container(self) -> None:
        with create_span(
            "sandbox.create",
            {
                "sandbox.worker_id": self.config.worker_id,
                "sandbox.image": self.config.image,
            },
        ):
            self._create_container_impl()

    def _create_container_impl(self) -> None:
        """
        Create a Docker container with security hardening.

        Security options applied:
        - network_disabled=True: Disable network access
        - read_only=True: Read-only root filesystem
        - cap_drop=["ALL"]: Drop all capabilities
        - security_opt=["no-new-privileges:true"]: Prevent privilege escalation
        - pids_limit=256: Limit process count
        """
        environment = self.config.environment or {}
        volumes = self._container_volumes()
        network_disabled = self.config.network_mode == "none"

        try:
            self.container = self.docker_client.containers.create(
                self.config.image,
                command="/bin/bash",
                stdin_open=True,
                tty=True,
                environment=environment,
                volumes=volumes,
                name=f"worker-{self.config.worker_id}",
                working_dir=self.config.container_workspace,
                # Resource limits
                cpu_quota=int(self.config.cpu_limit * 100000),
                cpu_period=100000,
                mem_limit=self.config.memory_limit,
                memswap_limit=self.config.memory_limit,
                # Security hardening
                network_disabled=network_disabled,
                network_mode=self.config.network_mode,
                read_only=self.config.read_only_rootfs,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                pids_limit=self.config.pids_limit,
            )
            logger.info(
                f"Container created: {self.container.id[:12]} "
                f"for worker {self.config.worker_id}"
            )
        except docker.errors.APIError as e:
            logger.error(f"Failed to create container: {e}")
            raise

    def start_container(self) -> None:
        """Start the container."""
        if not self.container:
            raise RuntimeError("Container not created. Call create_container() first.")

        try:
            self.container.start()
            logger.info(f"Container started: {self.container.id[:12]}")
        except docker.errors.APIError as e:
            logger.error(f"Failed to start container: {e}")
            raise

    def exec_in(
        self,
        command: str,
        timeout: int = 300
    ) -> Tuple[int, str, str]:
        """
        Execute command in container with stdout/stderr separation.

        Args:
            command: Command to execute
            timeout: Execution timeout in seconds

        Returns:
            Tuple of (exit_code, stdout, stderr)
        """
        result = self.exec_for_task(command, timeout=timeout)
        return result.exit_code, result.stdout, result.stderr

    def exec_for_task(
        self,
        command: str,
        timeout: int = 300,
    ) -> SandboxExecutionResult:
        truncated_cmd = command[:100] if len(command) > 100 else command
        with create_span(
            "sandbox.execute",
            {
                "sandbox.worker_id": self.config.worker_id,
                "sandbox.command": truncated_cmd,
            },
        ):
            return self._exec_for_task_impl(command, timeout)

    def _exec_for_task_impl(
        self,
        command: str,
        timeout: int,
    ) -> SandboxExecutionResult:
        """
        Execute command and return observable timeout cleanup details.

        Args:
            command: Command to execute
            timeout: Execution timeout in seconds

        Returns:
            SandboxExecutionResult with stdout, stderr, timeout, and cleanup state.
        """
        if not self.container:
            raise RuntimeError("Container not created. Call create_container() first.")

        try:
            exit_code, output = self.container.exec_run(
                command,
                stdout=True,
                stderr=True,
                demux=True,
                timeout=timeout,
                workdir=self.config.container_workspace,
            )

            # Demux returns (stdout_bytes, stderr_bytes) tuple
            stdout_bytes, stderr_bytes = output or (b"", b"")

            # Decode with error handling
            stdout = (
                stdout_bytes.decode("utf-8", errors="replace")
                if stdout_bytes
                else ""
            )
            stderr = (
                stderr_bytes.decode("utf-8", errors="replace")
                if stderr_bytes
                else ""
            )

            logger.debug(
                f"Command executed: exit_code={exit_code}, "
                f"stdout_len={len(stdout)}, stderr_len={len(stderr)}"
            )

            return SandboxExecutionResult(exit_code, stdout, stderr)

        except TimeoutError as e:
            cleanup_status, cleanup_error = self._cleanup_after_timeout()
            stderr = f"Command timed out after {timeout} seconds: {e}"
            return SandboxExecutionResult(
                124,
                "",
                stderr,
                timed_out=True,
                cleanup_status=cleanup_status,
                cleanup_error=cleanup_error,
            )

        except docker.errors.APIError as e:
            logger.error(f"Failed to execute command: {e}")
            raise

    def _cleanup_after_timeout(self) -> Tuple[str, str]:
        """Terminate and remove the container after a timeout."""
        if not self.container:
            return "not_needed", ""

        errors = []

        try:
            self.container.kill()
        except Exception as e:
            errors.append(f"kill failed: {e}")

        try:
            self.container.remove(force=True)
        except Exception as e:
            errors.append(f"remove failed: {e}")

        if not errors:
            logger.warning(
                f"Container killed and removed after timeout: "
                f"{self.container.id[:12]}"
            )
            return "removed", ""

        cleanup_error = "; ".join(errors)
        logger.error(f"Timeout cleanup failed: {cleanup_error}")
        return "failed", cleanup_error

    def stop_container(self, timeout: int = 10) -> None:
        """
        Stop the container.

        Args:
            timeout: Timeout for graceful stop in seconds
        """
        if not self.container:
            return

        try:
            self.container.stop(timeout=timeout)
            logger.info(f"Container stopped: {self.container.id[:12]}")
        except docker.errors.APIError as e:
            logger.warning(f"Failed to stop container gracefully: {e}")
            # Force kill if graceful stop fails
            try:
                self.container.kill()
                logger.info(f"Container killed: {self.container.id[:12]}")
            except docker.errors.APIError as kill_error:
                logger.error(f"Failed to kill container: {kill_error}")

    def remove_container(self, force: bool = False) -> None:
        """
        Remove the container.

        Args:
            force: Force remove even if running
        """
        if not self.container:
            return

        try:
            self.container.remove(force=force)
            logger.info(f"Container removed: {self.container.id[:12]}")
        except docker.errors.APIError as e:
            logger.error(f"Failed to remove container: {e}")

    def cleanup(self) -> None:
        """Clean up container resources."""
        try:
            self.stop_container()
            self.remove_container(force=True)
        except Exception as e:
            logger.error(f"Error during cleanup: {e}")

    def __enter__(self):
        """Context manager entry."""
        self.create_container()
        self.start_container()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.cleanup()
