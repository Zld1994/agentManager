"""Tests for install scripts (dry-run mode only)."""

import subprocess
import sys


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
