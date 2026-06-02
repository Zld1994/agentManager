# Codex Guide for agentManager

## Project Overview

`agentManager` is a Python 3.10+ prototype for an AI agent orchestration control plane.
It includes task dependency management, task state handling, event buses, scheduling,
runtime execution context, memory components, recovery logic, sandbox guards, defect repair
helpers, a FastAPI API, and benchmark/e2e test coverage.

The project is still a prototype. Prefer small, well-tested changes over broad rewrites.

## Repository Layout

- `agentManager/api.py`: FastAPI application and REST endpoints.
- `agentManager/domain/`: shared dataclass/enums for workflows, tasks, runs, agents, workers,
  artifacts, checkpoints, and events.
- `agentManager/engine/`: DAG, scheduler, state manager, checkpointing, and event bus code.
- `agentManager/engine/event_bus/`: async event bus abstractions and in-memory/Redis implementations.
- `agentManager/memory/`: profile/session, project, engineering memory, and vector-search backend
  components.
- `agentManager/observability/`: structured logging, request correlation, audit event helpers,
  and optional tracing hooks.
- `agentManager/storage/`: durable repository and object-store interfaces for PostgreSQL state
  persistence and S3-compatible checkpoint storage.
- `agentManager/recovery/`: recovery context, error classification, and recovery engine.
- `agentManager/runtime/`: task execution context, task executor, and workflow coordination helpers.
- `agentManager/sandbox/`: worker guard and sandbox execution helpers.
- `agentManager/defect_repair/`: canonical in-package defect repair implementation.
- `scheduler/`: top-level scheduler/resource-manager package.
- `tests/unit/`: focused unit tests.
- `tests/e2e/`: end-to-end and performance tests.
- `tests/benchmarks/`: benchmark runner, report generation, and benchmark tests.
- `docs/api.md`: REST API documentation.
- `docs/reports/`: archived reports plus the CI-backed verification report template.

## Setup

Install the package in editable mode:

```bash
pip install -e .
```

Install development dependencies when running the full test/tooling workflow:

```bash
pip install -e ".[dev]"
```

Optional sandbox dependencies are declared under the `sandbox` extra:

```bash
pip install -e ".[sandbox]"
```

## Common Commands

Run the default test suite configured in `pyproject.toml`:

```bash
pytest
```

Run unit tests only:

```bash
pytest tests/unit/ -v
```

Run a focused test file:

```bash
pytest tests/unit/test_scheduler.py -v
```

Run API locally:

```bash
python -m uvicorn agentManager.api:app --host 127.0.0.1 --port 8000
```

Verify FastAPI startup import:

```bash
python -c 'from agentManager.api import app; print("OK")'
```

Build and inspect a wheel when packaging changes touch package discovery:

```bash
python -m build --wheel
python -m zipfile -l dist/agentmanager-*.whl
```

Run the development Docker stack:

```bash
docker compose up --build
```

Build the production Docker image:

```bash
docker build -f Dockerfile.prod -t agentmanager:prod .
```

Format and import-sort changed Python files before finalizing larger changes:

```bash
black .
isort .
```

Generate a local verification summary artifact when updating report tooling:

```bash
python scripts/collect_ci_status.py --output .test-artifacts/verification-summary.md
```

## Coding Guidelines

- Keep Python compatibility at `>=3.10`.
- Follow the existing style: dataclasses and enums for core domain models, Pydantic v2 models
  for API request/response validation, and explicit exception handling around API boundaries.
- Use timezone-aware UTC timestamps. Existing modules commonly define `utc_now()` with
  `datetime.now(timezone.utc)`.
- Preserve public API behavior unless the task explicitly asks for a breaking change.
- Prefer the in-package modules under `agentManager/` for new work.
- Keep concurrency-sensitive scheduler and event bus changes covered by tests.
- Use structured APIs and project helpers instead of ad hoc parsing where possible.

## Testing Expectations

- Add or update tests for any behavior change.
- For core engine changes, run the relevant `tests/unit/test_*.py` file and consider the full
  unit suite.
- For FastAPI changes, update `tests/unit/test_api.py` and API docs when endpoint behavior changes.
- For async event bus changes, include async tests and cover workflow filtering where relevant.
- For Redis-backed functionality, make tests resilient when Redis is unavailable unless the test is
  explicitly marked/integration-scoped.
- For benchmark tooling changes, run the focused benchmark test module rather than the entire
  benchmark suite first.
- Completion and verification reports must cite a GitHub Actions run or be clearly marked as
  local-only verification. Use `docs/reports/verification-template.md` for new reports.

## Current Project Notes

- `README.md` appears to contain mojibake in some Chinese text. Do not rewrite it as part of
  unrelated tasks.
- `TODO.md` tracks current follow-up work and local verification blockers.
- Python 3.12 is the current local verification path. A repo-local `.venv312` may exist and can run
  `tests/unit/test_api.py` and the default `pytest` suite. Python 3.15 remains unsuitable for full
  FastAPI verification because dependency wheels may be unavailable.
- Coverage data is configured by `.coveragerc` to use `${TEMP}/agentmanager.coverage`, avoiding
  Windows file-lock issues when pytest-cov writes coverage SQLite files under the repository root.
- Coverage reports intentionally omit legacy defect-repair pipeline/strategy modules and profile/
  project memory prototypes from the CI threshold until those prototype areas get focused tests.
- Core CI mypy uses `--explicit-package-bases --follow-imports=skip` to avoid GitHub checkout path
  ambiguity (`agentManager.agentManager.*` vs `agentManager.*`) while keeping runtime/storage/config
  modules blocking.
- Full-repo flake8 is now expected to pass for `agentManager/ tests/` with `--max-line-length=100`;
  keep benchmark and e2e tests lint-clean when editing them.
- Durable backend client libraries are base dependencies (`psycopg[binary]`, `boto3`,
  `qdrant-client`), but durable services remain opt-in through environment settings; unit tests
  should mock PostgreSQL, object storage, Redis, and Qdrant unless explicitly integration-scoped.
- Observability defaults are local-safe: text logs, `X-Request-ID` request correlation, audit
  helpers under `agentManager.audit`, and tracing disabled unless `OTEL_TRACING_ENABLED=true`.
- Durable audit sinks are injected through RuntimeFactory startup wiring via
  `configure_runtime_audit_sinks(...)`, which delegates to
  `configure_audit_sinks(..., repository=..., object_store=...)`; avoid direct SQL or boto3 calls
  from `agentManager/observability/audit.py`.
- `audit_record` includes a `content_hash` column for a SHA-256 integrity hash of the redacted
  audit payload. This is not an HMAC signature and should not be treated as tamper-proof against a
  malicious writer.
- `/health` checks only dependencies configured through environment variables. Default mode returns
  HTTP 200 with `status="degraded"` on dependency failure; `?strict=true` returns HTTP 503.
- Local Docker Compose verification is still environment-dependent. Windows PowerShell may not have
  `docker`; WSL Docker Engine and Compose v2 can be used with `wsl --cd /mnt/h/AllProject/agentManager ...`
  when available. Keep Docker verification reports explicit about local-only blockers.
- The `sandbox-integration` CI job should skip only when Docker is unavailable or the sandbox image
  cannot be pulled; a successful `docker pull python:3.11-slim` should allow the integration tests to run.
- `agentManager.egg-info/`, `.coverage`, `.pytest_cache/`, `__pycache__/`, and test output folders
  may be generated locally. Avoid editing generated metadata by hand unless packaging behavior is
  the target of the task.
- This repository may have local uncommitted changes. Inspect `git status --short` before editing,
  and do not revert unrelated user changes.

## Pull Request Checklist

- The change is scoped to the requested behavior.
- Relevant tests pass locally, or the reason they were not run is documented.
- API docs are updated for user-visible endpoint changes.
- New dependencies are justified and added to `pyproject.toml`.
- Generated files are not committed unless they are intentional artifacts.
- After every commit, review `AGENTS.md` and update it if the commit changes project structure,
  workflows, commands, dependencies, conventions, or known maintenance notes.
