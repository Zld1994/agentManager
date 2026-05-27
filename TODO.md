# TODO

## Current Maintenance Notes

- Add Docker support, including development and production Dockerfiles plus `docker-compose.yml`.
- Implement the missing `roles` and `agentManager.scheduler` subpackages referenced by older issues, then add e2e coverage for those capabilities.
- Fix the remaining full-suite `pytest tests/` failures in benchmarks and top-level memory tests, then re-enable full-suite validation as a required check.

## Pending Fixes From Obsidian Review

- Reconcile README claims with the real prototype status; remove production-ready wording until the implementation supports it.
- Keep the FastAPI startup path `agentManager.api:app` working and aligned with README/docs.
- Ensure package discovery includes all `agentManager` subpackages in built wheels.
- Rewrite API usage examples so they match current code, especially `DAGNode.task_type`, `DAGEngine.get_ready_nodes()`, `StateMachine`, and `TaskState`.
- Fix DAG cycle detection by using a real acyclic-graph check and rejecting edges that introduce cycles.
- Keep EventBus documentation clear about in-memory versus Redis Streams behavior; complete the interface/implementation split.
- Ensure wildcard EventBus subscriptions are triggered when publishing workflow-specific events.
- Allow non-terminal task states to transition into `BLOCKED_HITL` when human intervention is required.
- Prevent scheduler dead loops when a pending task still has conflicts.
- Require dependencies to be `completed` before downstream scheduler tasks can run.
- Add a real execution loop that connects DAG readiness, scheduler dispatch, sandbox execution, events, state transitions, checkpointing, recovery, and defect repair.
- Replace placeholder recovery strategies with real retry, event replay, snapshot restore, re-execution, and HITL behavior based on a complete recovery context.
- Harden checkpoint archive extraction against path traversal.
- Unify base and enhanced checkpoint manager capabilities so recovery code does not depend on methods that may be missing.
- Redesign memory around explicit profile, project, and engineering memory layers plus a vector-search backend.
- Harden WorkerSandbox defaults with least-privilege Docker settings, restricted networking, isolated workspaces, and timeout cleanup.
- Separate WorkerSandbox stdout and stderr using Docker demuxed output.
- Rename or replace WorkerGuard text similarity logic so it matches the actual Jaccard behavior, then add stronger action/error/output loop detection.
- Split development and production compose/env configuration so weak default secrets are not usable in production.
- Keep Prometheus/Grafana compose references in sync with checked-in `monitoring/` files and API metrics endpoints.
- Replace static test-completion reports with CI-backed test status; remove misleading 100% production-ready claims.
- Move test/tooling dependencies out of runtime dependencies and remove unnecessary built-in dependencies such as `asyncio`.
- Define shared domain models for `Workflow`, `Task`, `TaskRun`, `Agent`, `Worker`, `Artifact`, `Checkpoint`, and `Event`.

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
