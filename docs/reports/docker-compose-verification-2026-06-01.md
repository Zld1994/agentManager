# Docker Compose Verification - 2026-06-01

## Scope

This report records verification evidence for the M4 Docker and sandbox tasks
in `taskList.md`.

## Local Results

| Check | Command | Result | Notes |
|---|---|---|---|
| Windows Docker CLI | `docker build -f Dockerfile.prod -t agentmanager:prod .` | blocked | PowerShell cannot find `docker` on PATH. |
| WSL Docker CLI | `wsl docker version` | passed | Client/server Docker Engine `29.1.3`. |
| WSL Docker Compose | `wsl docker compose version` | passed | Docker Compose `v2.24.0`. |
| Compose syntax | `wsl --cd /mnt/h/AllProject/agentManager docker compose config` | passed | Rendered all 7 services successfully. |
| Production image | `wsl --cd /mnt/h/AllProject/agentManager docker build -f Dockerfile.prod -t agentmanager:prod .` | passed | Image `agentmanager:prod` built successfully. |
| Production image size | `wsl docker image inspect agentmanager:prod --format '{{.Size}}'` | passed | `117826839` bytes, about 112.4 MiB, below the 500MB target. |
| Local sandbox integration | `.venv312\Scripts\python.exe -m pytest tests/integration/test_sandbox_docker.py -v --no-cov -m integration` | skipped | 13 skipped because the PowerShell environment does not expose Docker. |

## CI Results

Latest checked run: GitHub Actions `26769717318`
(`docs: record remaining verification work`, 2026-06-01T17:05:33Z).

| Job | Result | Evidence |
|---|---|---|
| `docker-verify` | success | `Verify compose syntax`, `Build production image`, and `Build development image` all succeeded. |
| `sandbox-integration` | success | `Check Docker availability`, `Pull sandbox image`, and `Run Docker sandbox integration tests` all succeeded. |
| `test (3.10)` | failure | Unit tests ran, but `Check coverage threshold` failed. |
| `test (3.11)` | failure | Unit and e2e tests ran, but `Run mypy type checking (core modules)` failed. |
| `test (3.12)` | failure | Unit tests ran, but `Check coverage threshold` failed. |

## Current Status

M4 Docker verification items are complete for the requested scope:

- M4-A.1.2: CI Redis service container was usable by the test jobs.
- M4-A.2.4: Production image builds locally via WSL Docker and in CI.
- M4-D.1.2: Sandbox integration tests run successfully in CI; local PowerShell
  remains skip-only because `docker` is not on PATH.

The overall CI run is still red due to coverage-threshold and mypy-core
failures. Those failures are separate from the Docker, Redis, and sandbox
verification items recorded here.
