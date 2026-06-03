"""Tests for scheduled task runner."""

import json
from unittest.mock import MagicMock

import pytest

from agentManager.runtime.scheduled_tasks import (
    ScheduledTaskConfig,
    ScheduledTaskRunner,
)


class TestScheduledTaskConfig:
    """Tests for ScheduledTaskConfig dataclass."""

    def test_valid_config(self):
        config = ScheduledTaskConfig(
            name="test-task",
            interval_seconds=60,
            task_payload={"type": "health_check"},
            enabled=True,
        )
        assert config.name == "test-task"
        assert config.interval_seconds == 60
        assert config.task_payload == {"type": "health_check"}
        assert config.enabled is True
        assert config.last_run == 0.0
        assert config.next_run > 0

    def test_defaults(self):
        config = ScheduledTaskConfig(name="h", interval_seconds=10)
        assert config.enabled is False
        assert config.task_payload == {}

    def test_rejects_empty_name(self):
        with pytest.raises(ValueError, match="name must not be empty"):
            ScheduledTaskConfig(name="", interval_seconds=10)

    def test_rejects_invalid_interval(self):
        with pytest.raises(ValueError, match="interval_seconds must be >= 1"):
            ScheduledTaskConfig(name="h", interval_seconds=0)

        with pytest.raises(ValueError, match="interval_seconds must be >= 1"):
            ScheduledTaskConfig(name="h", interval_seconds=-1)


class TestScheduledTaskRunner:
    """Tests for ScheduledTaskRunner."""

    @pytest.mark.asyncio
    async def test_add_task(self):
        runner = ScheduledTaskRunner()
        config = ScheduledTaskConfig(name="task-1", interval_seconds=30, enabled=True)
        await runner.add_task(config)
        assert "task-1" in runner.tasks
        assert runner.tasks["task-1"].interval_seconds == 30

    @pytest.mark.asyncio
    async def test_tasks_is_copy(self):
        runner = ScheduledTaskRunner()
        config = ScheduledTaskConfig(name="t", interval_seconds=10)
        await runner.add_task(config)
        tasks = runner.tasks
        tasks.clear()
        assert "t" in runner.tasks  # Original unaffected

    def test_set_callback(self):
        runner = ScheduledTaskRunner()
        callback = MagicMock()
        runner.set_callback(callback)
        assert runner._callback is callback

    def test_start_stop(self):
        import asyncio

        async def _test():
            runner = ScheduledTaskRunner()
            runner.start()
            assert runner._running is True
            runner.stop()
            assert runner._running is False

        asyncio.run(_test())

    def test_start_idempotent(self):
        import asyncio

        async def _test():
            runner = ScheduledTaskRunner()
            runner.start()
            runner.start()
            assert runner._running is True
            runner.stop()

        asyncio.run(_test())

    def test_start_without_event_loop_raises(self):
        runner = ScheduledTaskRunner()
        with pytest.raises(RuntimeError, match="event loop"):
            runner.start()

    def test_load_from_directory(self, tmp_path):
        schedules_dir = tmp_path / "schedules"
        schedules_dir.mkdir()
        task_json = schedules_dir / "task1.json"
        task_json.write_text(
            json.dumps(
                {
                    "name": "health-check",
                    "interval_seconds": 60,
                    "task_payload": {"type": "health"},
                    "enabled": True,
                }
            )
        )
        runner = ScheduledTaskRunner.from_directory(tmp_path)
        assert "health-check" in runner.tasks
        assert runner.tasks["health-check"].enabled is True

    def test_load_list_format(self, tmp_path):
        schedules_dir = tmp_path / "schedules"
        schedules_dir.mkdir()
        task_json = schedules_dir / "tasks.json"
        task_json.write_text(
            json.dumps(
                [
                    {"name": "a", "interval_seconds": 10},
                    {"name": "b", "interval_seconds": 20},
                ]
            )
        )
        runner = ScheduledTaskRunner.from_directory(tmp_path)
        assert "a" in runner.tasks
        assert "b" in runner.tasks

    def test_load_skips_invalid_json(self, tmp_path):
        schedules_dir = tmp_path / "schedules"
        schedules_dir.mkdir()
        (schedules_dir / "bad.json").write_text("not json")
        runner = ScheduledTaskRunner.from_directory(tmp_path)
        assert len(runner.tasks) == 0  # No crash, just skip

    def test_load_missing_directory(self, tmp_path):
        runner = ScheduledTaskRunner.from_directory(tmp_path)
        assert len(runner.tasks) == 0

    def test_callback_dispatches(self):
        import asyncio

        results = []

        def callback(payload):
            results.append(payload)
            return "ok"

        async def _test():
            runner = ScheduledTaskRunner()
            runner.set_callback(callback)
            config = ScheduledTaskConfig(
                name="fast",
                interval_seconds=1,
                task_payload={"test": True},
                enabled=True,
                last_run=0,
                next_run=0,  # Trigger immediately
            )
            await runner.add_task(config)
            runner.start()

            # Wait for the loop to execute the callback
            await asyncio.sleep(1.5)
            runner.stop()

        asyncio.run(_test())

        assert len(results) >= 1
        assert results[0] == {"test": True}
