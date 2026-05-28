# TODO

## Current Maintenance Notes

✅ **COMPLETED (2026-05-27)**:
- Task 1: Merged top-level `defect_repair/` with `agentManager/defect_repair/` - canonical implementation complete
- Task 2: Added Docker support (Dockerfile.dev, Dockerfile.prod, docker-compose.yml)
- Task 3: Implemented `agentManager/roles/` and `agentManager/scheduler/` subpackages with unit tests
- Task 4: Fixed all pytest failures - 457 tests passing ✓
- Task 5: Improved DAG cycle detection with DFS and cycle path reporting - 19 tests passing ✓
- Task 6: Prevented scheduler dead loops with retry limits and conflict detection - 24 tests passing ✓
- Task 8: Ensured FastAPI startup path `agentManager.api:app` working - 10 tests passing ✓
- Task 9: Completed package discovery in wheels - all 9 subpackages importable ✓

**Remaining High-Priority Tasks**:

✅ **COMPLETED (2026-05-28)**:
- Reconciled README/API examples with prototype status and current API behavior.
- Split development/production configuration guidance so weak local defaults are not presented as production-safe.
- Replaced misleading production-ready claims in static completion reports with historical milestone wording.
- Added `WorkflowCoordinator` to connect DAG readiness, scheduler dispatch, task execution, events, state transitions, checkpoints, and completion/failure sync.
- Replaced placeholder recovery behavior with observable retry, event replay, snapshot restore, re-execution, HITL, and escalation behavior.
- Added a consistent async checkpoint manager surface while preserving archive path traversal protection.
- Redesigned memory layers around explicit profile/session and engineering memory plus pluggable vector-search backends with SQLite fallback.
- Clarified WorkerGuard word-level Jaccard similarity behavior and added configurable action/error/output loop detection.
- Added shared domain models for `Workflow`, `Task`, `TaskRun`, `Agent`, `Worker`, `Artifact`, `Checkpoint`, and `Event`.
- Pinned `mypy<2.0` in dev dependencies to avoid the mypy 2.x native dependency issue in the current Python 3.15 environment.

**Verification completed (2026-05-28)**:
- `python -m pytest tests/unit -q --no-cov --ignore=tests/unit/test_api.py` - 377 passed.
- `python -m pytest tests/e2e/test_runtime_workflow_loop.py tests/unit/test_task_executor.py -q --no-cov` - 26 passed.
- `python -m pytest tests/unit/test_domain_models.py tests/unit/test_dag_engine.py -q --no-cov` - 35 passed.
- `git diff --check` - passed, with only CRLF warnings.

**Verification completed (2026-05-29)**:
- `python -m pytest tests/e2e/ -q --no-cov` - 7 passed, 1 skipped after moving e2e temp files to a repo-local ignored test artifact directory.
- Installed Python 3.12.10 with `winget install Python.Python.3.12` and created `.venv312`.
- `.venv312\Scripts\python.exe -m pip install -e ".[dev]"` - completed successfully with Python 3.12 wheels for `pydantic-core`.
- `.venv312\Scripts\python.exe -m pytest tests/unit/test_api.py -q --no-cov` - 28 passed, 1 warning.
- `.venv312\Scripts\python.exe -m pytest` - 530 passed, 1 warning, 85% total coverage.

**Remaining blockers (2026-05-28)**:
- `tests/unit/test_api.py` is not verified locally because this machine only has Python 3.15. Installing FastAPI pulls `pydantic-core`, which has no usable wheel here and fails to compile without MSVC `link.exe`.
- Full `pytest` is not verified locally until the API dependency blocker is resolved. Recommended fix: run tests in a Python 3.11/3.12 virtual environment or CI image.
- Docker/Compose validation was static only because Docker is unavailable in this shell.

- Docker/Compose validation is still blocked locally. Windows PowerShell has no `docker` command. WSL `Ubuntu-24.04` is running and has Docker Engine CLI `29.1.3`, but neither `docker compose` nor `docker-compose` is installed. A direct production image build reached the Docker daemon, then failed while pulling `python:3.11-slim` from Docker Hub with a TLS handshake timeout. Required follow-up: install Docker Compose v2 in WSL or expose Docker Desktop Compose on Windows, and ensure Docker Hub registry access/proxy settings work.

## Pending Fixes From Obsidian Review

- Validate Docker Compose configuration with `docker compose config` after Docker Compose v2 is available in Windows or WSL and Docker Hub image pulls work.
- Ensure future static completion reports are generated from CI-backed test status rather than hand-written point-in-time claims.
- Continue hardening WorkerSandbox beyond current defaults: isolated per-task workspaces, stricter timeout cleanup, and production container policy review.
- Complete durable backend roadmap: PostgreSQL workflow/task-run state, object-store checkpoints, persistent memory, audit logs, OpenTelemetry traces, and deployment docs.

## Suggested Refactor Roadmap

1. Fix P0 runtime issues first: API startup, package discovery, DAG cycle detection, scheduler loop behavior, HITL transitions, EventBus wildcard handling, and monitoring config.
2. Replace in-memory prototypes with durable backends: Redis Streams, PostgreSQL state/workflow/task-run storage, object-store checkpoints, and persistent memory.
3. Connect the execution loop end to end from workflow creation through sandbox execution, recovery, defect repair, and memory write-back.
4. Add production security and observability: sandbox hardening, secret management, audit logs, Prometheus metrics, OpenTelemetry traces, structured logs, CI/CD, and deployment docs.

## Pending Optimization Questions

- Provide a one-command installer and estimate the work required to support Linux, Windows, and macOS.
- Decide how agents are configured: project-level per-agent `.md` files versus runtime prompt injection.
- Define how skills are reused across agents and profiles.
- Decide whether subcomponents need communication and choose the communication mechanism.
- Support profile-based skill configuration for different agent types.
- Determine whether scheduled tasks and hooks should be supported.
- Build a project map and decide what prompts or skills should reduce agent context usage.
- Support default agents with high-level and low-level tiers, with manager agents defaulting to the high-level tier.
- Let users configure a manager role that can split work into validated task JSON.
- Design prompts, schemas, and UI flows that let users inspect and edit generated task JSON.
- Support temporary role/template selection, user confirmation, and assignment to specific agents.
- Configure per-agent working directories after the user confirms the selected agents.
- Define the built-in skills and MCP template library available during role creation.
- Allow users to add new skills or MCP entries to the template library.
- Let both users and manager-created roles choose from the current skills/MCP template list.
