# agentManager Maintenance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the remaining high-priority TODO items into a testable, production-oriented maintenance roadmap.

**Architecture:** Start by restoring trustworthy verification in a supported Python and Docker environment. Then harden runtime safety, persistence, execution orchestration, reporting, and production observability in small, independently testable slices.

**Tech Stack:** Python 3.10+, FastAPI, pytest, pytest-asyncio, Docker Compose, Redis Streams, PostgreSQL, object storage, Prometheus, OpenTelemetry, GitHub Actions.

---

## Scope

This plan decomposes the first 8 unfinished items from `TODO.md`:

1. Restore trusted test verification.
2. Complete full e2e validation.
3. Validate Docker and Compose.
4. Implement durable backend roadmap.
5. Harden `WorkerSandbox`.
6. Make completion reports CI-backed.
7. Complete the end-to-end execution loop.
8. Add production security and observability.

## Working Rules

- Keep each task small enough to review independently.
- Prefer new focused tests before implementation changes.
- Preserve unrelated local changes. Check `git status --short` before each task.
- Use Python 3.11 or 3.12 for verification until Python 3.15 dependency wheels are reliable.
- Run `flake8 --jobs=1` if multiprocessing lint runs fail in this Windows environment.
- Update `TODO.md`, `README.md`, `docs/api.md`, or `AGENTS.md` only when the implemented change affects documented behavior or workflow.

---

## Task 1: Restore Trusted Test Verification

**Purpose:** Remove the current local verification blocker by establishing a supported Python test path for API and full-suite runs.

**Status (2026-05-29):** Completed locally on Python 3.12.10. `winget install Python.Python.3.12` installed Python 3.12, `.venv312` was created, `.venv312\Scripts\python.exe -m pip install -e ".[dev]"` completed successfully, `.venv312\Scripts\python.exe -m pytest tests/unit/test_api.py -q --no-cov` passed with 28 tests, and `.venv312\Scripts\python.exe -m pytest` passed with 530 tests and 85% total coverage. The run still needs normal CI confirmation, but the local Python 3.15 dependency blocker is no longer active.

**Files:**
- Modify: `.github/workflows/ci.yml`
- Modify: `pyproject.toml`
- Test: `tests/unit/test_api.py`
- Test: full `tests/` suite
- Document: `TODO.md` after verification status changes

- [x] Step 1: Create or select a Python 3.11/3.12 environment.

  Recommended local commands:

  ```powershell
  py -3.12 -m venv .venv312
  .\.venv312\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  python -m pip install -e ".[dev]"
  ```

  Expected result: `python --version` reports Python 3.11.x or 3.12.x, and editable install completes without building `pydantic-core` from source.

- [x] Step 2: Verify the blocked API tests first.

  ```powershell
  python -m pytest tests/unit/test_api.py -v --no-cov
  ```

  Expected result: all API tests pass. If failures occur, record the exact failing tests and fix only the API behavior or test expectation causing the failure.

- [x] Step 3: Run the default test command from `pyproject.toml`.

  ```powershell
  python -m pytest
  ```

  Expected result: the complete suite runs with coverage. If coverage fails while tests pass, capture the coverage threshold gap separately from functional failures.

- [x] Step 4: Make CI run the same supported verification path.

  In `.github/workflows/ci.yml`, keep the existing Python setup but expand the job to run:

  ```bash
  pytest tests/unit/ -v --cov=agentManager --cov-report=term-missing --cov-report=xml
  pytest tests/e2e/ -v --no-cov
  ```

  Expected result: unit and e2e failures are reported separately, so API regressions do not hide e2e status.

- [x] Step 5: Record verified status.

  Update `TODO.md` only after the commands above have current results. Replace the Python 3.15 blocker note with the verified Python version and command output summary.

---

## Task 2: Complete Full E2E Validation

**Purpose:** Make the full e2e suite reliable enough to run locally and in CI.

**Files:**
- Inspect: `tests/e2e/conftest.py`
- Inspect: `tests/e2e/test_performance.py`
- Inspect: `tests/e2e/test_runtime_workflow_loop.py`
- Modify or add focused tests under: `tests/e2e/`
- Document: `TODO.md` if an environment-only limitation remains

- [x] Step 1: Reproduce the full e2e result in Python 3.11/3.12.

  ```powershell
  python -m pytest tests/e2e/ -v --no-cov
  ```

  Expected result: either all e2e tests pass or failures identify specific temp-directory cleanup, timing, or platform assumptions.

- [x] Step 2: Isolate Windows temp cleanup failures.

  Inspect fixtures in `tests/e2e/conftest.py` and replace fragile cleanup with `tmp_path` or `tmp_path_factory` owned by pytest where possible.

  Verification command:

  ```powershell
  python -m pytest tests/e2e/ -v --no-cov --maxfail=1
  ```

  Expected result: no failure caused only by deleting temp directories after the test body already passed.

- [x] Step 3: Remove hidden runtime dependencies from e2e tests.

  Keep tests pointed at existing modules only:

  - `agentManager.runtime.workflow_coordinator`
  - `agentManager.runtime.task_executor`
  - `agentManager.engine.dag`
  - `agentManager.engine.scheduler`
  - `agentManager.engine.event_bus`
  - `agentManager.memory`

  Expected result: e2e tests do not import missing packages or services unless the test is explicitly integration-scoped.

- [x] Step 4: Add CI e2e execution.

  In `.github/workflows/ci.yml`, run e2e tests after unit tests:

  ```bash
  pytest tests/e2e/ -v --no-cov
  ```

  Expected result: CI clearly reports whether e2e is green, skipped for a declared reason, or failing.

---

## Task 3: Validate Docker and Compose

**Purpose:** Turn static Docker review into executable validation.

**Status (2026-05-29):** Blocked by local tooling/network, not by a confirmed Compose or Dockerfile schema error. Windows PowerShell has no `docker` command. WSL `Ubuntu-24.04` is running with Docker Engine CLI `29.1.3`, but `docker compose` and `docker-compose` are unavailable. `docker build -f Dockerfile.prod -t agentmanager:prod .` reached the WSL Docker daemon and then failed pulling `python:3.11-slim` from Docker Hub with a TLS handshake timeout. Install Docker Compose v2 in WSL or expose Docker Desktop Compose on Windows, then verify Docker Hub registry/proxy access before rerunning this task.

**Files:**
- Inspect: `Dockerfile.dev`
- Inspect: `Dockerfile.prod`
- Inspect: `docker-compose.yml`
- Inspect: `.env.example`
- Inspect: `.env.prod.example`
- Inspect: `monitoring/prometheus.yml`
- Document: `README.md` or `TODO.md` if runtime prerequisites change

- [ ] Step 1: Validate Compose syntax on a Docker-enabled machine.

  ```powershell
  docker compose config
  ```

  Expected result: Compose renders a complete configuration without schema errors.

- [ ] Step 2: Build the development image.

  ```powershell
  docker compose build agentmanager
  ```

  Expected result: the image builds using `Dockerfile.dev` and installs project dependencies successfully.

- [ ] Step 3: Start the development stack.

  ```powershell
  docker compose up -d
  docker compose ps
  ```

  Expected result: `agentmanager`, `postgres`, `redis`, `qdrant`, and `minio` are running or healthy.

- [ ] Step 4: Verify API health from the containerized stack.

  ```powershell
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read().decode())"
  ```

  Expected result: the API returns a healthy response.

- [ ] Step 5: Validate production image build.

  ```powershell
  docker build -f Dockerfile.prod -t agentmanager:prod .
  ```

  Expected result: production image builds without relying on development-only bind mounts.

- [ ] Step 6: Shut down local services cleanly.

  ```powershell
  docker compose down
  ```

  Expected result: no running project containers remain.

---

## Task 4: Implement Durable Backend Roadmap

**Purpose:** Replace prototype-only in-memory state with explicit durable backend interfaces and first production-capable implementations.

**Files:**
- Modify: `agentManager/config/settings.py`
- Modify: `agentManager/engine/state_manager.py`
- Modify: `agentManager/engine/checkpoint.py`
- Modify: `agentManager/engine/event_bus/redis_stream.py`
- Modify: `agentManager/memory/memory_backend.py`
- Modify: `agentManager/memory/vector_backend.py`
- Add: `agentManager/storage/__init__.py`
- Add: `agentManager/storage/postgres.py`
- Add: `agentManager/storage/object_store.py`
- Test: `tests/unit/test_state_manager.py`
- Test: `tests/unit/test_checkpoint.py`
- Test: `tests/unit/test_redis_stream_event_bus.py`
- Test: `tests/unit/memory/test_layered_memory_backends.py`
- Test: `tests/unit/test_storage_backends.py`

- [x] Step 1: Define storage configuration.

  Add settings for:

  - `DATABASE_URL`
  - `REDIS_URL`
  - `OBJECT_STORE_ENDPOINT`
  - `OBJECT_STORE_BUCKET`
  - `OBJECT_STORE_ACCESS_KEY`
  - `OBJECT_STORE_SECRET_KEY`
  - `VECTOR_BACKEND`

  Verification:

  ```powershell
  python -m pytest tests/unit/test_settings.py -v --no-cov
  ```

- [x] Step 2: Add a PostgreSQL state repository interface.

  Create `agentManager/storage/postgres.py` with repository methods for workflow state, task runs, and audit records. Keep implementation behind an interface so unit tests can use fakes without requiring PostgreSQL.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_state_manager.py -v --no-cov
  ```

- [x] Step 3: Add object-store checkpoint abstraction.

  Create `agentManager/storage/object_store.py` and connect it to `agentManager/engine/checkpoint.py` without removing local filesystem checkpoint support.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_checkpoint.py -v --no-cov
  ```

- [x] Step 4: Keep Redis Streams as the durable event transport.

  Ensure `agentManager/engine/event_bus/redis_stream.py` handles stream append, consumer read, ack, retry, and workflow filtering behavior covered by tests.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_redis_stream_event_bus.py -v --no-cov
  ```

- [x] Step 5: Persist memory through pluggable backends.

  Extend `agentManager/memory/memory_backend.py` and `agentManager/memory/vector_backend.py` so profile/session/engineering memory can use SQLite locally and a durable backend in production.

  Verification:

  ```powershell
  python -m pytest tests/unit/memory/ -v --no-cov
  ```

---

## Task 5: Harden WorkerSandbox

**Purpose:** Reduce sandbox escape and cleanup risk before production use.

**Files:**
- Modify: `agentManager/sandbox/worker_sandbox.py`
- Modify: `agentManager/sandbox/worker_guard.py`
- Modify: `agentManager/config/settings.py`
- Test: `tests/unit/test_worker_sandbox.py`
- Test: `tests/unit/test_worker_guard.py`
- Document: `README.md` or `docs/api.md` if user-visible sandbox behavior changes

- [x] Step 1: Add isolated per-task workspace behavior.

  Tests should assert each task receives a unique workspace path and cannot write outside it.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_worker_sandbox.py -v --no-cov
  ```

- [x] Step 2: Enforce timeout cleanup.

  Add tests for command timeout, process termination, and workspace cleanup. On Windows, make cleanup retry bounded and observable instead of silently failing.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_worker_sandbox.py -v --no-cov
  ```

- [x] Step 3: Add production container policy settings.

  Add configuration for:

  - allowed images
  - denied mounts
  - network mode
  - CPU and memory limits
  - read-only root filesystem where supported

  Verification:

  ```powershell
  python -m pytest tests/unit/test_settings.py tests/unit/test_worker_sandbox.py -v --no-cov
  ```

- [x] Step 4: Keep WorkerGuard loop detection covered.

  Ensure hardening does not regress action/error/output loop detection.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_worker_guard.py -v --no-cov
  ```

---

## Task 6: Make Completion Reports CI-Backed

**Purpose:** Prevent future static reports from claiming unverified status.

**Files:**
- Modify: `.github/workflows/ci.yml`
- Add: `scripts/collect_ci_status.py`
- Add: `docs/reports/verification-template.md`
- Modify: `docs/reports/README.md`
- Inspect historical reports under: `docs/reports/`

- [x] Step 1: Define a verification report template.

  Add `docs/reports/verification-template.md` with required sections:

  - commit SHA
  - branch
  - Python version
  - command list
  - pass/fail/skipped status
  - CI run URL
  - known blockers

- [x] Step 2: Add a CI status collection script.

  Create `scripts/collect_ci_status.py` that reads environment variables such as `GITHUB_SHA`, `GITHUB_REF_NAME`, and `GITHUB_RUN_ID`, then writes a concise Markdown verification summary.

  Verification:

  ```powershell
  python scripts/collect_ci_status.py --output test_tmp/verification-summary.md
  ```

  Expected result: a Markdown file is created with explicit unknown values when not running inside GitHub Actions.

- [x] Step 3: Wire the script into CI.

  In `.github/workflows/ci.yml`, run the script after tests and upload the summary as an artifact.

  Expected result: every CI run produces a machine-generated verification summary.

- [x] Step 4: Update report policy.

  In `docs/reports/README.md`, state that new completion reports must cite CI run status or explicitly mark local-only verification.

---

## Task 7: Complete End-to-End Execution Loop

**Purpose:** Make workflow creation through execution, recovery, defect repair, and memory write-back observable and tested as one loop.

**Files:**
- Modify: `agentManager/runtime/workflow_coordinator.py`
- Modify: `agentManager/runtime/task_executor.py`
- Modify: `agentManager/recovery/recovery_engine.py`
- Modify: `agentManager/defect_repair/repair_pipeline.py`
- Modify: `agentManager/memory/engineering_memory.py`
- Modify: `agentManager/engine/event_bus.py`
- Test: `tests/e2e/test_runtime_workflow_loop.py`
- Add or modify: `tests/e2e/test_execution_recovery_memory_loop.py`

- [ ] Step 1: Write an e2e test for successful workflow execution.

  The test should create a small DAG, dispatch ready tasks, execute them through `TaskExecutor`, publish events, update state, checkpoint outputs, and write a memory record.

  Verification:

  ```powershell
  python -m pytest tests/e2e/test_runtime_workflow_loop.py -v --no-cov
  ```

- [ ] Step 2: Write an e2e test for recovery path execution.

  Add `tests/e2e/test_execution_recovery_memory_loop.py` covering a failing task that triggers recovery, records the recovery event, and writes a durable engineering memory entry.

  Verification:

  ```powershell
  python -m pytest tests/e2e/test_execution_recovery_memory_loop.py -v --no-cov
  ```

- [ ] Step 3: Connect defect repair as an optional recovery strategy.

  Ensure `RecoveryEngine` can call `repair_pipeline` only when classification indicates a repairable defect and the workflow policy allows it.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_recovery_engine.py tests/test_defect_repair.py -v --no-cov
  ```

- [ ] Step 4: Verify the combined runtime path.

  ```powershell
  python -m pytest tests/e2e/ -v --no-cov
  ```

  Expected result: successful and recovery loops both pass without requiring external services.

---

## Task 8: Add Production Security and Observability

**Purpose:** Add the minimum production controls needed to operate and diagnose the system safely.

**Files:**
- Modify: `agentManager/config/settings.py`
- Modify: `agentManager/api.py`
- Modify: `agentManager/runtime/workflow_coordinator.py`
- Modify: `agentManager/engine/event_bus.py`
- Add: `agentManager/observability/__init__.py`
- Add: `agentManager/observability/logging.py`
- Add: `agentManager/observability/tracing.py`
- Add: `agentManager/observability/audit.py`
- Modify: `monitoring/prometheus.yml`
- Modify: `.env.prod.example`
- Modify: `README.md`
- Test: `tests/unit/test_settings.py`
- Add: `tests/unit/test_observability.py`

- [ ] Step 1: Add structured logging configuration.

  Add settings for log level, JSON log output, and request/workflow correlation IDs.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_settings.py -v --no-cov
  ```

- [ ] Step 2: Add audit event helpers.

  Create `agentManager/observability/audit.py` with helpers for security-sensitive events: workflow creation, task execution, sandbox denial, recovery escalation, and configuration validation failure.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_observability.py -v --no-cov
  ```

- [ ] Step 3: Add OpenTelemetry trace hooks behind configuration.

  Create `agentManager/observability/tracing.py` and keep tracing disabled by default for local development. When enabled, trace workflow coordination, task execution, recovery, checkpoint, and memory write operations.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_observability.py tests/unit/test_task_executor.py tests/unit/test_recovery_engine.py -v --no-cov
  ```

- [ ] Step 4: Review Prometheus configuration.

  Update `monitoring/prometheus.yml` only if scrape targets or metrics paths changed.

  Verification:

  ```powershell
  python -m pytest tests/unit/test_api.py -v --no-cov
  ```

- [ ] Step 5: Update production environment example.

  Add required security and observability variables to `.env.prod.example` without putting real secrets in the file.

  Verification:

  ```powershell
  git diff --check
  ```

---

## Final Verification Matrix

Run these commands before marking the full plan complete:

```powershell
python -m pytest tests/unit/test_api.py -v --no-cov
python -m pytest tests/unit/ -v --no-cov
python -m pytest tests/e2e/ -v --no-cov
python -m pytest
python -m flake8 agentManager tests --max-line-length=100 --jobs=1
git diff --check
docker compose config
docker compose build agentmanager
docker build -f Dockerfile.prod -t agentmanager:prod .
```

Expected final state:

- API tests pass in Python 3.11/3.12.
- Full unit and e2e suites are either passing or have explicitly documented external-service skips.
- Docker Compose and production image build are validated.
- Durable backend interfaces exist with unit coverage.
- Sandbox hardening has direct tests.
- New completion reports are tied to CI evidence.
- Runtime execution loop covers success and recovery paths.
- Security and observability settings are documented and tested.

## Suggested Commit Sequence

1. `test: restore supported api and full-suite verification`
2. `test: stabilize full e2e validation`
3. `chore: validate docker compose workflow`
4. `feat: add durable backend interfaces`
5. `feat: harden worker sandbox execution`
6. `chore: generate ci-backed verification reports`
7. `feat: complete runtime recovery memory loop`
8. `feat: add production observability controls`
