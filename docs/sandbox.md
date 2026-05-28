# WorkerSandbox Production Hardening

`WorkerSandbox` runs worker commands in Docker containers with a per-task
workspace and a restrictive default container policy.

## Workspace Isolation

Each sandbox config resolves one host workspace:

```text
<workspace_root>/<worker_id>/<task_id>
```

The resolved directory is mounted writable at `/workspace`, and commands run
with `/workspace` as the container working directory. `worker_id` and `task_id`
must be single path components; absolute paths, `..`, `/`, and `\` are rejected.

Additional host mounts are allowed only when read-only. Writable mounts must be
inside the resolved task workspace, so task code cannot write outside its own
directory through Docker volume configuration.

## Container Policy

Default policy:

- `allowed_images`: `python:3.10-slim`
- `denied_mounts`: `/var/run/docker.sock`
- `network_mode`: `none`
- `cpu_limit`: `1.0`
- `memory_limit`: `512m`
- `read_only_rootfs`: `true`
- `pids_limit`: `256`
- capabilities: all dropped
- security option: `no-new-privileges:true`

Policy can be supplied directly through `SandboxConfig`. Environment parsing is
available through `agentManager.config.settings.get_sandbox_policy_settings()`
with these variables:

- `SANDBOX_ALLOWED_IMAGES`
- `SANDBOX_DENIED_MOUNTS`
- `SANDBOX_NETWORK_MODE`
- `SANDBOX_CPU_LIMIT`
- `SANDBOX_MEMORY_LIMIT`
- `SANDBOX_READ_ONLY_ROOTFS`

## Timeout Cleanup

Use `exec_for_task()` when callers need timeout observability. On timeout it
returns `SandboxExecutionResult` with:

- `exit_code=124`
- `timed_out=True`
- `cleanup_status` set to `removed`, `failed`, or `not_needed`
- `cleanup_error` populated when kill or remove fails

The older `exec_in()` API remains available and returns `(exit_code, stdout,
stderr)` for compatibility.
