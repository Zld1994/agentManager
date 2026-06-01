"""Docker-based integration tests for WorkerSandbox security hardening.

These tests create real Docker containers and inspect their configuration
to verify that security options (cap_drop, read-only rootfs, network
isolation, no-new-privileges) are applied correctly.

Tests are marked with ``@pytest.mark.integration`` and will be skipped
automatically when Docker is not available.
"""

import json
import subprocess

import pytest

from agentManager.sandbox.worker_sandbox import SandboxConfig, WorkerSandbox


def _docker_available() -> bool:
    try:
        result = subprocess.run(
            ["docker", "info"],
            capture_output=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


skip_no_docker = pytest.mark.skipif(
    not _docker_available(),
    reason="Docker not available",
)


@pytest.fixture
def sandbox_config():
    return SandboxConfig(
        worker_id="security-test-worker",
        image="python:3.10-slim",
        cpu_limit=1.0,
        memory_limit="512m",
        timeout=60,
    )


@pytest.fixture
def sandbox(sandbox_config):
    sb = WorkerSandbox(sandbox_config)
    yield sb
    if sb.container is not None:
        sb.cleanup()


def _inspect_container(container_id: str) -> dict:
    result = subprocess.run(
        ["docker", "inspect", container_id],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode != 0:
        pytest.skip(f"docker inspect failed: {result.stderr}")
    return json.loads(result.stdout)[0]


@skip_no_docker
@pytest.mark.integration
class TestSandboxSecurityAssertions:
    """Verify Docker container security hardening via docker inspect."""

    def test_cap_drop_all(self, sandbox):
        sandbox.create_container()
        assert sandbox.container is not None
        info = _inspect_container(sandbox.container.id)
        cap_drop = info["HostConfig"].get("CapDrop", [])
        assert "ALL" in cap_drop, f"Expected CapDrop=['ALL'], got {cap_drop}"

    def test_readonly_rootfs(self, sandbox):
        sandbox.create_container()
        assert sandbox.container is not None
        info = _inspect_container(sandbox.container.id)
        readonly = info["HostConfig"].get("ReadonlyRootfs", False)
        assert readonly is True, f"Expected ReadonlyRootfs=True, got {readonly}"

    def test_network_disabled(self, sandbox):
        sandbox.create_container()
        assert sandbox.container is not None
        info = _inspect_container(sandbox.container.id)
        network_mode = info["HostConfig"].get("NetworkMode", "")
        networks = info.get("NetworkSettings", {}).get("Networks", {})
        assert network_mode == "none" or not networks, (
            f"Expected network_mode='none' or empty networks, "
            f"got mode={network_mode!r}, networks={list(networks.keys())}"
        )

    def test_no_new_privileges(self, sandbox):
        sandbox.create_container()
        assert sandbox.container is not None
        info = _inspect_container(sandbox.container.id)
        security_opt = info["HostConfig"].get("SecurityOpt", [])
        assert "no-new-privileges:true" in security_opt, (
            f"Expected 'no-new-privileges:true' in SecurityOpt, got {security_opt}"
        )
