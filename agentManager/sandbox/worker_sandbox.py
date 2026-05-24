"""
WorkerSandbox - Docker-based execution sandbox for worker tasks.

Provides:
- Secure container creation with hardened security options
- Command execution with stdout/stderr separation
- Resource limits (CPU, memory, processes)
- Network isolation
"""

import docker
import docker.errors
import logging
from typing import Tuple, Optional, Dict
from dataclasses import dataclass


logger = logging.getLogger(__name__)


@dataclass
class SandboxConfig:
    """Configuration for WorkerSandbox."""

    worker_id: str
    image: str = "python:3.10-slim"
    cpu_limit: float = 1.0  # CPU cores
    memory_limit: str = "512m"
    timeout: int = 300  # seconds
    volumes: Optional[Dict[str, Dict[str, str]]] = None
    environment: Optional[Dict[str, str]] = None


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

    def create_container(self) -> None:
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
        volumes = self.config.volumes or {}

        try:
            self.container = self.docker_client.containers.create(
                self.config.image,
                command="/bin/bash",
                stdin_open=True,
                tty=True,
                environment=environment,
                volumes=volumes,
                name=f"worker-{self.config.worker_id}",
                # Resource limits
                cpu_quota=int(self.config.cpu_limit * 100000),
                cpu_period=100000,
                mem_limit=self.config.memory_limit,
                memswap_limit=self.config.memory_limit,
                # Security hardening
                network_disabled=True,
                read_only=True,
                cap_drop=["ALL"],
                security_opt=["no-new-privileges:true"],
                pids_limit=256,
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
        if not self.container:
            raise RuntimeError("Container not created. Call create_container() first.")

        try:
            exit_code, output = self.container.exec_run(
                command,
                stdout=True,
                stderr=True,
                demux=True,
                timeout=timeout,
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

            return exit_code, stdout, stderr

        except docker.errors.APIError as e:
            logger.error(f"Failed to execute command: {e}")
            raise

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
