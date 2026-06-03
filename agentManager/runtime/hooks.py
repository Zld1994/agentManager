"""Runtime hooks subsystem for lifecycle event callbacks.

Hooks are disabled by default and require opt-in via HOOKS_ENABLED=true.
"""

from __future__ import annotations

import logging
import os
import re as _re
import shlex
import subprocess
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)

VALID_HOOK_EVENTS = (
    "before_task_plan_confirm",
    "after_task_plan_confirm",
    "before_workflow_run",
    "after_workflow_run",
)

# Pattern for safe environment variable names (POSIX-like)
_SAFE_ENV_KEY_PATTERN = _re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")


@dataclass
class HookConfig:
    """Configuration for a single runtime hook."""

    name: str
    event: str
    command: str
    enabled: bool = False
    timeout_seconds: int = 30
    allow_failure: bool = False

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Hook name must not be empty")
        if self.event not in VALID_HOOK_EVENTS:
            raise ValueError(
                f"Invalid hook event: {self.event!r}, must be one of " f"{VALID_HOOK_EVENTS}"
            )
        if not self.command:
            raise ValueError("Hook command must not be empty")
        if self.timeout_seconds < 1:
            raise ValueError("Hook timeout_seconds must be >= 1")


class HookRunner:
    """Runs configured hooks for lifecycle events via subprocess.

    Hooks are disabled by default. Set HOOKS_ENABLED=true to opt-in.
    """

    def __init__(self, hooks: list[HookConfig] | None = None) -> None:
        self._hooks: list[HookConfig] = list(hooks) if hooks else []
        self._enabled = os.getenv("HOOKS_ENABLED", "false").lower() == "true"

    @property
    def hooks(self) -> list[HookConfig]:
        return list(self._hooks)

    def add_hook(self, hook: HookConfig) -> None:
        self._hooks.append(hook)

    def run_hooks(self, event: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """Run all enabled hooks for the given event.

        Returns:
            Dict mapping hook name to result dict with 'status', 'stdout', 'stderr'.
            Failed hooks raise RuntimeError unless allow_failure=True.
        """
        results: dict[str, Any] = {}
        ctx = context or {}

        # Build safe environment variables from context, filtering unsafe keys/values
        safe_env_extra: dict[str, str] = {"AGENTMGR_EVENT": event}
        for key, value in ctx.items():
            str_key = str(key)
            str_value = str(value)
            if not _SAFE_ENV_KEY_PATTERN.match(str_key):
                logger.warning(
                    "Skipping unsafe env key %r in hook context (invalid chars)", str_key
                )
                continue
            # Reject values containing null bytes or newlines
            if "\x00" in str_value or "\n" in str_value:
                logger.warning(
                    "Skipping unsafe env value for key %r (contains null/newline)", str_key
                )
                continue
            safe_env_extra[str_key] = str_value

        for hook in self._hooks:
            if hook.event != event:
                continue
            if not self._enabled:
                logger.debug("Hook %s skipped: HOOKS_ENABLED is not true", hook.name)
                continue
            if not hook.enabled:
                continue

            logger.info("Running hook %s for event %s", hook.name, event)
            try:
                # Security: use shell=False with shlex.split to avoid shell injection
                proc = subprocess.run(
                    shlex.split(hook.command),
                    shell=False,
                    capture_output=True,
                    text=True,
                    timeout=hook.timeout_seconds,
                    env={**os.environ, **safe_env_extra},
                )
                results[hook.name] = {
                    "status": "ok" if proc.returncode == 0 else "failed",
                    "stdout": proc.stdout.strip(),
                    "stderr": proc.stderr.strip(),
                    "returncode": proc.returncode,
                }
                if proc.returncode != 0 and not hook.allow_failure:
                    raise RuntimeError(
                        f"Hook {hook.name!r} failed with exit code "
                        f"{proc.returncode}: {proc.stderr.strip()}"
                    )
            except subprocess.TimeoutExpired as e:
                results[hook.name] = {
                    "status": "timeout",
                    "stdout": "",
                    "stderr": str(e),
                    "returncode": -1,
                }
                if not hook.allow_failure:
                    raise RuntimeError(
                        f"Hook {hook.name!r} timed out after " f"{hook.timeout_seconds}s"
                    ) from e
            except Exception:
                logger.exception("Hook %s raised unexpected error", hook.name)
                if not hook.allow_failure:
                    raise

        return results


def load_hooks_from_list(configs: list[dict[str, Any]]) -> list[HookConfig]:
    """Create HookConfig instances from a list of dictionaries."""
    return [HookConfig(**c) for c in configs]
