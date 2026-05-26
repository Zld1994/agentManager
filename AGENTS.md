# Codex Guide for agentManager

## Project Overview

`agentManager` is a Python 3.10+ prototype for an AI agent orchestration control plane.
It includes task dependency management, task state handling, event buses, scheduling,
runtime execution context, memory components, recovery logic, sandbox guards, defect repair
helpers, a FastAPI API, and benchmark/e2e test coverage.

The project is still a prototype. Prefer small, well-tested changes over broad rewrites.

## Repository Layout

- `agentManager/api.py`: FastAPI application and REST endpoints.
- `agentManager/engine/`: DAG, scheduler, state manager, checkpointing, and event bus code.
- `agentManager/engine/event_bus/`: async event bus abstractions and in-memory/Redis implementations.
- `agentManager/memory/`: task, session, project, and engineering memory components.
- `agentManager/recovery/`: recovery context, error classification, and recovery engine.
- `agentManager/runtime/`: task execution context and runtime helpers.
- `agentManager/sandbox/`: worker guard and sandbox execution helpers.
- `agentManager/defect_repair/`: canonical in-package defect repair implementation.
- `defect_repair/`: legacy top-level defect repair package; avoid expanding it unless migrating.
- `scheduler/`: top-level scheduler/resource-manager package.
- `tests/unit/`: focused unit tests.
- `tests/e2e/`: end-to-end and performance tests.
- `tests/benchmarks/`: benchmark runner, report generation, and benchmark tests.
- `docs/api.md`: REST API documentation.

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

Format and import-sort changed Python files before finalizing larger changes:

```bash
black .
isort .
```

## Coding Guidelines

- Keep Python compatibility at `>=3.10`.
- Follow the existing style: dataclasses and enums for core domain models, Pydantic v2 models
  for API request/response validation, and explicit exception handling around API boundaries.
- Use timezone-aware UTC timestamps. Existing modules commonly define `utc_now()` with
  `datetime.now(timezone.utc)`.
- Preserve public API behavior unless the task explicitly asks for a breaking change.
- Prefer the in-package modules under `agentManager/` for new work.
- Avoid adding new behavior to the legacy top-level `defect_repair/` package unless the task is
  specifically about migration or backwards compatibility.
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

## Current Project Notes

- `README.md` appears to contain mojibake in some Chinese text. Do not rewrite it as part of
  unrelated tasks.
- `TODO.md` lists known follow-up work:
  - merge the top-level `defect_repair/` package with `agentManager/defect_repair/`;
  - add Docker support;
  - implement missing `roles` and `agentManager.scheduler` subpackages referenced by older issues.
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
