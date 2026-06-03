"""Scheduled task runner for config-driven periodic task dispatch.

Tasks are loaded from <config_dir>/schedules/*.json and dispatched
via a callback. The runner does NOT auto-start; call start() explicitly.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)


@dataclass
class ScheduledTaskConfig:
    """Configuration for a single scheduled task."""

    name: str
    interval_seconds: int
    task_payload: dict[str, Any] = field(default_factory=dict)
    enabled: bool = False
    last_run: float = 0.0
    next_run: float = 0.0

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("Scheduled task name must not be empty")
        if self.interval_seconds < 1:
            raise ValueError(f"interval_seconds must be >= 1, got {self.interval_seconds}")
        if self.next_run <= 0:
            self.next_run = time.time() + self.interval_seconds


class ScheduledTaskRunner:
    """Asyncio-based runner for scheduled tasks.

    Tasks are loaded from JSON configuration files. The runner must be
    explicitly started; it does not auto-start on creation.

    Example::

        runner = ScheduledTaskRunner()
        runner.add_task(ScheduledTaskConfig(
            name="health-check",
            interval_seconds=60,
            task_payload={"type": "health_check"},
            enabled=True,
        ))
        runner.set_callback(my_async_handler)
        runner.start()
    """

    def __init__(self) -> None:
        self._tasks: dict[str, ScheduledTaskConfig] = {}
        self._callback: Callable[[dict[str, Any]], object] | None = None
        self._running = False
        self._task_handle: asyncio.Task[None] | None = None
        self._lock = asyncio.Lock()

    @property
    def tasks(self) -> dict[str, ScheduledTaskConfig]:
        return dict(self._tasks)

    async def add_task(self, config: ScheduledTaskConfig) -> None:
        async with self._lock:
            self._tasks[config.name] = config

    def set_callback(self, callback: Callable[[dict[str, Any]], object]) -> None:
        self._callback = callback

    def load_from_directory(self, config_dir: Path) -> None:
        """Load scheduled task configs from <config_dir>/schedules/*.json."""
        schedules_dir = config_dir / "schedules"
        if not schedules_dir.is_dir():
            logger.debug("No schedules directory at %s", schedules_dir)
            return

        for json_file in sorted(schedules_dir.glob("*.json")):
            try:
                data = json.loads(json_file.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load schedule %s: %s", json_file, exc)
                continue

            if isinstance(data, list):
                for entry in data:
                    self._add_from_dict(entry)
            elif isinstance(data, dict):
                self._add_from_dict(data)

    def _add_from_dict(self, data: dict[str, Any]) -> None:
        try:
            config = ScheduledTaskConfig(**data)
            self._tasks[config.name] = config
            logger.info(
                "Loaded scheduled task: %s (interval=%ss)",
                config.name,
                config.interval_seconds,
            )
        except (TypeError, ValueError) as exc:
            logger.warning("Invalid scheduled task config %s: %s", data, exc)

    def start(self) -> None:
        """Start the background asyncio loop. No-op if already running.

        Raises:
            RuntimeError: If called without a running asyncio event loop.
        """
        if self._running:
            return

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError as exc:
            raise RuntimeError(
                "ScheduledTaskRunner.start() must be called from within "
                "a running asyncio event loop (e.g., inside an async function)."
            ) from exc

        self._running = True
        self._task_handle = loop.create_task(self._run_loop())
        logger.info("ScheduledTaskRunner started with %d tasks", len(self._tasks))

    def stop(self) -> None:
        """Stop the background loop."""
        self._running = False
        if self._task_handle and not self._task_handle.done():
            self._task_handle.cancel()
        logger.info("ScheduledTaskRunner stopped")

    async def _run_loop(self) -> None:
        """Main loop that checks and dispatches enabled scheduled tasks."""
        while self._running:
            now = time.time()
            async with self._lock:
                task_snapshot = list(self._tasks.items())
            for name, config in task_snapshot:
                if not config.enabled:
                    continue
                if now >= config.next_run:
                    config.last_run = now
                    config.next_run = now + config.interval_seconds
                    if self._callback:
                        try:
                            result = self._callback(config.task_payload)
                            if asyncio.iscoroutine(result):
                                await result
                        except Exception:
                            logger.exception("Scheduled task %s callback raised error", name)
            await asyncio.sleep(1)

    @classmethod
    def from_directory(cls, config_dir: Path) -> ScheduledTaskRunner:
        """Convenience: create runner and load configs from a directory."""
        runner = cls()
        runner.load_from_directory(config_dir)
        return runner
