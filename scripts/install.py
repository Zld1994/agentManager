#!/usr/bin/env python3
"""agentManager installer - cross-platform, idempotent.

Usage:
    python scripts/install.py                  # Install base + dev
    python scripts/install.py --dry-run         # Print commands only
    python scripts/install.py --with-sandbox    # Include sandbox extra
    python scripts/install.py --with-otel       # Include OTEL extra
    python scripts/install.py --verify          # Verify after install
    python scripts/install.py --verify-tests    # Run smoke tests after install
"""

import argparse
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def get_python() -> str:
    """Return the Python executable path."""
    return sys.executable


def get_venv_dir() -> str:
    """Return the recommended virtualenv directory name."""
    return ".venv"


def check_python_version() -> tuple[bool, str]:
    """Check Python version meets minimum requirements."""
    major, minor = sys.version_info[:2]
    ok = (major, minor) >= (3, 10)
    return ok, f"{major}.{minor}"


def detect_os() -> str:
    """Detect operating system."""
    if sys.platform.startswith("win"):
        return "windows"
    elif sys.platform.startswith("linux"):
        return "linux"
    elif sys.platform.startswith("darwin"):
        return "macos"
    return sys.platform


def create_venv(dry_run: bool) -> None:
    """Create a virtual environment if it does not exist."""
    venv_dir = get_venv_dir()
    if Path(venv_dir).exists():
        print(f"Virtual environment already exists: {venv_dir}")
        return
    cmd = [get_python(), "-m", "venv", venv_dir]
    if dry_run:
        print(f"[dry-run] {' '.join(cmd)}")
        return
    print(f"Creating virtual environment: {venv_dir}")
    subprocess.run(cmd, check=True)


def pip_install(dry_run: bool, extras: list[str], dev: bool = True) -> None:
    """Run pip install with requested extras."""
    requested_extras = []
    if dev:
        requested_extras.append("dev")
    for extra in extras:
        if extra not in requested_extras:
            requested_extras.append(extra)

    target = f".[{','.join(requested_extras)}]" if requested_extras else "."
    cmd = [get_python(), "-m", "pip", "install", "-e", target]

    if dry_run:
        print(f"[dry-run] {' '.join(cmd)}")
        return
    print("Installing agentManager...")
    subprocess.run(cmd, check=True)


def verify_import() -> bool:
    """Verify package import after install."""
    cmd = [get_python(), "-c", "from agentManager.api import app; print('OK')"]
    print("Verifying import...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode == 0:
        print("Import verification: OK")
        return True
    print(f"Import verification FAILED: {result.stderr}")
    return False


def verify_tests() -> bool:
    """Run smoke tests."""
    cmd = [get_python(), "-m", "pytest", "tests/unit/test_api.py", "-q", "--no-cov"]
    print("Running smoke tests...")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode == 0


@dataclass(frozen=True)
class DockerEnvironment:
    """Detected Docker execution mode for local verification."""

    mode: str
    available: bool
    docker_command: tuple[str, ...]
    compose_command: tuple[str, ...]
    wsl_project_path: Optional[str] = None
    reason: str = ""


def _run_probe(cmd: list[str]) -> bool:
    """Return whether a lightweight availability probe succeeds."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode == 0


def windows_path_to_wsl(path: Path) -> Optional[str]:
    """Convert a Windows drive-qualified path to a WSL /mnt path."""
    resolved = path.resolve()
    drive = resolved.drive.rstrip(":").lower()
    if not drive:
        return None
    remainder = resolved.as_posix().split(":", 1)[1].lstrip("/")
    return f"/mnt/{drive}/{remainder}"


def detect_docker_environment(project_root: Optional[Path] = None) -> DockerEnvironment:
    """Detect native Docker first, then WSL Docker on Windows."""
    if shutil.which("docker") and _run_probe(["docker", "info"]):
        return DockerEnvironment(
            mode="native",
            available=True,
            docker_command=("docker",),
            compose_command=("docker", "compose"),
        )

    if sys.platform.startswith("win") and shutil.which("wsl"):
        root = project_root or Path.cwd()
        wsl_project_path = windows_path_to_wsl(root)
        if (
            wsl_project_path
            and _run_probe(["wsl", "docker", "info"])
            and _run_probe(["wsl", "docker", "compose", "version"])
        ):
            return DockerEnvironment(
                mode="wsl",
                available=True,
                docker_command=("wsl", "docker"),
                compose_command=("wsl", "docker", "compose"),
                wsl_project_path=wsl_project_path,
            )

    return DockerEnvironment(
        mode="unavailable",
        available=False,
        docker_command=(),
        compose_command=(),
        reason="Docker is not available from this shell or WSL.",
    )


def _docker_verify_commands(docker_env: DockerEnvironment) -> list[list[str]]:
    """Build local Docker verification commands for the detected environment."""
    if docker_env.mode == "wsl":
        if not docker_env.wsl_project_path:
            raise ValueError("WSL Docker verification requires a WSL project path")
        return [
            ["wsl", "--cd", docker_env.wsl_project_path, "docker", "compose", "config"],
            [
                "wsl",
                "--cd",
                docker_env.wsl_project_path,
                "docker",
                "build",
                "-f",
                "Dockerfile.prod",
                "-t",
                "agentmanager:prod",
                ".",
            ],
        ]
    return [
        ["docker", "compose", "config"],
        ["docker", "build", "-f", "Dockerfile.prod", "-t", "agentmanager:prod", "."],
    ]


def verify_docker(
    dry_run: bool,
    docker_env: Optional[DockerEnvironment] = None,
    project_root: Optional[Path] = None,
) -> bool:
    """Verify local Docker/Compose using native Docker or Windows WSL fallback."""
    env = docker_env or detect_docker_environment(project_root)
    if not env.available:
        print(f"WARNING: {env.reason}")
        return False

    print(f"Docker verification mode: {env.mode}")
    for cmd in _docker_verify_commands(env):
        if dry_run:
            print(f"[dry-run] {' '.join(cmd)}")
            continue
        subprocess.run(cmd, check=True)
    return True


def check_docker() -> Optional[str]:
    """Check if Docker is available through native Docker or WSL."""
    docker_env = detect_docker_environment()
    if not docker_env.available:
        return None
    if docker_env.mode == "wsl":
        return "WSL Docker"
    return shutil.which("docker")


def main() -> None:
    parser = argparse.ArgumentParser(description="agentManager installer")
    parser.add_argument("--dry-run", action="store_true", help="Print commands without executing")
    parser.add_argument("--with-sandbox", action="store_true", help="Include sandbox extra")
    parser.add_argument("--with-otel", action="store_true", help="Include OTEL extra")
    parser.add_argument("--with-dev", action="store_true", default=True, help="Include dev extra")
    parser.add_argument("--verify", action="store_true", help="Verify import after install")
    parser.add_argument("--verify-tests", action="store_true", help="Run smoke tests after install")
    parser.add_argument(
        "--verify-docker",
        action="store_true",
        help="Verify Docker/Compose locally",
    )
    parser.add_argument("--no-dev", action="store_true", help="Skip dev extra")
    args = parser.parse_args()

    os_type = detect_os()
    print(f"agentManager installer - OS: {os_type}")

    ok, version = check_python_version()
    if not ok:
        print(f"ERROR: Python 3.10+ required, found {version}")
        sys.exit(1)
    print(f"Python version: {version} (OK)")

    if args.dry_run:
        print("DRY RUN - no commands will be executed\n")

    create_venv(args.dry_run)

    extras: list[str] = []
    if args.with_sandbox:
        extras.append("sandbox")
    if args.with_otel:
        extras.append("otel")

    dev = not args.no_dev
    pip_install(args.dry_run, extras, dev=dev)

    if args.with_sandbox:
        docker_env = detect_docker_environment()
        if docker_env.available:
            if docker_env.mode == "wsl":
                print(f"Docker found via WSL: {docker_env.wsl_project_path}")
            else:
                print(f"Docker found: {shutil.which('docker')}")
        else:
            print("WARNING: Docker not found - sandbox execution requires Docker")

    if args.verify_docker:
        if not verify_docker(args.dry_run, project_root=Path.cwd()):
            print("WARNING: Docker verification did not run successfully")

    if args.verify:
        if not args.dry_run:
            verify_import()

    if args.verify_tests:
        if not args.dry_run:
            verify_tests()

    if not args.dry_run:
        print("\nInstallation complete.")
    else:
        print("\nDry-run complete. Run without --dry-run to install.")


if __name__ == "__main__":
    main()
