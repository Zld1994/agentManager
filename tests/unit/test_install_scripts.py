"""Tests for install scripts (dry-run mode only)."""

import importlib.util
from pathlib import Path
import subprocess
import sys

import pytest


INSTALL_SCRIPT = Path("scripts/install.py")


@pytest.fixture
def install_module():
    """Load install.py as a module so Docker probing can be tested with mocks."""
    spec = importlib.util.spec_from_file_location("agentmanager_install", INSTALL_SCRIPT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_install_py_dry_run():
    """Verify install.py --dry-run produces expected output."""
    result = subprocess.run(
        [sys.executable, "scripts/install.py", "--dry-run", "--with-otel"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "."},
        cwd=".",
    )
    assert result.returncode == 0
    assert "[dry-run]" in result.stdout

    # Should mention editable install
    assert "pip install -e" in result.stdout or "pip install" in result.stdout


def test_install_py_dry_run_with_verify():
    """Verify --dry-run --verify --verify-tests works."""
    result = subprocess.run(
        [sys.executable, "scripts/install.py", "--dry-run", "--verify", "--verify-tests"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": "."},
        cwd=".",
    )
    assert result.returncode == 0
    assert "[dry-run]" in result.stdout


def test_install_py_keeps_dev_extra_with_optional_extras():
    """Default install should keep dev extra when optional extras are requested."""
    result = subprocess.run(
        [
            sys.executable,
            "scripts/install.py",
            "--dry-run",
            "--with-sandbox",
            "--with-otel",
        ],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert result.returncode == 0
    assert ".[dev,sandbox,otel]" in result.stdout


def test_install_py_version_check():
    """Verify version check succeeds."""
    result = subprocess.run(
        [sys.executable, "scripts/install.py", "--dry-run"],
        capture_output=True,
        text=True,
        cwd=".",
    )
    assert result.returncode == 0
    assert "Python version" in result.stdout
    assert "OK" in result.stdout


def test_detect_docker_environment_prefers_native_docker(install_module, monkeypatch):
    """Native Docker should be used before any Windows WSL fallback."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(install_module.shutil, "which", lambda name: "docker.exe")
    monkeypatch.setattr(install_module.subprocess, "run", fake_run)

    docker_env = install_module.detect_docker_environment()

    assert docker_env.mode == "native"
    assert docker_env.available is True
    assert docker_env.docker_command == ("docker",)
    assert calls == [["docker", "info"]]


def test_detect_docker_environment_uses_wsl_on_windows(install_module, monkeypatch):
    """Windows should use WSL Docker when native Docker is absent."""
    calls = []

    def fake_run(cmd, **kwargs):
        calls.append(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="ok", stderr="")

    monkeypatch.setattr(
        install_module.shutil,
        "which",
        lambda name: "wsl.exe" if name == "wsl" else None,
    )
    monkeypatch.setattr(install_module.subprocess, "run", fake_run)
    monkeypatch.setattr(install_module.sys, "platform", "win32")

    docker_env = install_module.detect_docker_environment(
        Path("H:/AllProject/agentManager")
    )

    assert docker_env.mode == "wsl"
    assert docker_env.available is True
    assert docker_env.docker_command == ("wsl", "docker")
    assert docker_env.compose_command == ("wsl", "docker", "compose")
    assert docker_env.wsl_project_path == "/mnt/h/AllProject/agentManager"
    assert calls == [["wsl", "docker", "info"], ["wsl", "docker", "compose", "version"]]


def test_verify_docker_dry_run_reports_wsl_commands(install_module, capsys):
    """Docker verification dry-run should show the WSL commands it would run."""
    docker_env = install_module.DockerEnvironment(
        mode="wsl",
        available=True,
        docker_command=("wsl", "docker"),
        compose_command=("wsl", "docker", "compose"),
        wsl_project_path="/mnt/h/AllProject/agentManager",
    )

    assert install_module.verify_docker(dry_run=True, docker_env=docker_env) is True

    output = capsys.readouterr().out
    assert "[dry-run] wsl --cd /mnt/h/AllProject/agentManager docker compose config" in output
    assert (
        "[dry-run] wsl --cd /mnt/h/AllProject/agentManager docker build "
        "-f Dockerfile.prod -t agentmanager:prod ."
    ) in output
