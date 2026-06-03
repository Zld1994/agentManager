# Security Best Practices Review - agentManager

**Date:** 2026-06-03
**Scope:** Uncommitted changes (modified + new files)
**Framework:** Python 3.10+ / FastAPI
**Reference:** python-fastapi-web-server-security.md

---

## Executive Summary

The uncommitted code includes significant new features: task plan API, agent configuration system, runtime hooks, scheduled tasks, and sandbox workdir support. The codebase demonstrates several good security practices (consistent auth, security headers, request size limits, sandbox hardening, path traversal protection). However, **3 findings require attention**, with 1 being high severity.

---

## Findings

### SEC-001: Shell injection risk in HookRunner (FASTAPI-INJECT-002)

- **Severity:** High
- **Location:** [hooks.py](file:///h:/AllProject/agentManager/agentManager/runtime/hooks.py#L87-L94)
- **Evidence:**
  ```python
  proc = subprocess.run(
      hook.command,
      shell=True,
      capture_output=True,
      text=True,
      timeout=hook.timeout_seconds,
      env={**os.environ, "AGENTMGR_EVENT": event, **ctx},
  )
  ```
- **Impact:** `hook.command` is a free-form string executed with `shell=True`. If hook configurations are loaded from a config file that an attacker can influence (e.g., project-level config directory), arbitrary shell commands can be executed on the host. Even though hooks are disabled by default (`HOOKS_ENABLED=false`), once enabled, any command string in the config is executed through a shell interpreter.
- **Fix:** Pass the command as a list instead of using `shell=True`. If shell features (pipes, redirects) are needed, document the risk and consider an allowlist of permitted commands.
  ```python
  # Safer: split command into args list
  import shlex
  proc = subprocess.run(
      shlex.split(hook.command),
      shell=False,
      capture_output=True,
      text=True,
      timeout=hook.timeout_seconds,
      env={**os.environ, "AGENTMGR_EVENT": event, **ctx},
  )
  ```
- **Mitigation:** If `shell=True` is required for legitimate reasons, add documentation warning and validate that the command comes from a trusted source (not user-uploaded config).
- **False positive notes:** Hooks are opt-in and disabled by default. The command comes from `HookConfig`, not directly from API request parameters. The risk is real only when hooks are enabled AND the config source is untrusted.

---

### SEC-002: Non-constant-time token comparison (FASTAPI-AUTH-001)

- **Severity:** Medium
- **Location:** [api.py](file:///h:/AllProject/agentManager/agentManager/api.py#L179)
- **Evidence:**
  ```python
  if token != _auth_settings["auth_token"]:
  ```
- **Impact:** The `!=` operator performs short-circuit string comparison, which may leak timing information. An attacker could use timing side-channels to progressively guess the bearer token character-by-character.
- **Fix:** Use `hmac.compare_digest()` for constant-time comparison:
  ```python
  import hmac
  if not hmac.compare_digest(token, _auth_settings["auth_token"]):
  ```
- **Mitigation:** The risk is low in practice for network-based timing attacks, but `compare_digest` is the standard best practice for secret comparison.
- **False positive notes:** Timing attacks over network are noisy and difficult to exploit reliably. However, the fix is trivial and has zero performance cost.

---

### SEC-003: Task plan `workdir` field lacks API-level path traversal validation

- **Severity:** Medium
- **Location:** [api.py](file:///h:/AllProject/agentManager/agentManager/api.py#L312) (`TaskPlanItemRequest.workdir`)
- **Evidence:**
  ```python
  workdir: str = ""  # No validation for ".." or absolute paths
  ```
- **Impact:** The `workdir` field in task plan items accepts any string, including paths with `..` or absolute paths. While `SandboxConfig` validates workdir later (worker_sandbox.py line 80-84), the API layer does not reject obviously malicious values. This violates defense-in-depth: if the workdir value is used elsewhere before reaching the sandbox (e.g., in event payloads, logging, or metadata), it could cause path traversal.
- **Fix:** Add a field validator to `TaskPlanItemRequest`:
  ```python
  @field_validator("workdir")
  @classmethod
  def validate_workdir(cls, value: str) -> str:
      if not value:
          return value
      if os.path.isabs(value):
          raise ValueError("workdir must be relative")
      if ".." in Path(value).parts:
          raise ValueError("workdir must not contain '..'")
      return value
  ```
- **Mitigation:** The existing sandbox validation provides a safety net, but API-level validation catches issues earlier and provides clearer error messages.
- **False positive notes:** The sandbox validation in `SandboxConfig.task_workspace_path` already prevents actual traversal. This is a defense-in-depth recommendation.

---

## Positive Security Observations

The following good practices are already in place:

1. **Security headers middleware** (api.py L72-79): Sets `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`.
2. **Request body size limit** (api.py L82-96): Enforces `MAX_REQUEST_BODY_SIZE` (default 1MB).
3. **TrustedHostMiddleware** (api.py L99-102): Enabled when `ALLOWED_HOSTS` is set.
4. **Consistent auth enforcement** (api.py): All endpoints use `Depends(verify_token)`.
5. **Pydantic request validation** (api.py): Proper use of `BaseModel` with `field_validator` for identifiers.
6. **Sandbox workdir traversal protection** (worker_sandbox.py L78-88): Validates relative paths, rejects `..`, checks `is_relative_to`.
7. **Sandbox security hardening** (worker_sandbox.py): Network disabled, read-only rootfs, `cap_drop=["ALL"]`, `no-new-privileges`, pids limit.
8. **Sandbox image allowlist** (worker_sandbox.py L62): Only `python:3.11-slim` allowed by default.
9. **Denied mount protection** (worker_sandbox.py L63): Docker socket mount is denied.
10. **Docs can be disabled** (api.py L46-47): `DOCS_ENABLED=false` disables OpenAPI endpoints.
11. **AgentWorkdirPolicy path validation** (agent_config.py L66-69): Rejects `..` and `~` in root paths.

---

## Non-Issues (Verified Safe)

- **CORS**: Not configured (no `CORSMiddleware`), which is correct for a non-browser API.
- **Debug mode**: Not enabled in production code.
- **Auto-reload**: Not used in production entrypoint.
- **SQL injection**: No raw SQL in the reviewed code; uses dataclass/dict storage.
- **SSRF**: No outbound HTTP requests from API handlers.
- **File uploads**: No file upload endpoints in the reviewed changes.
