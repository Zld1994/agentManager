"""Unit tests for Scheduler Engine."""

import pytest
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from agentManager.engine.scheduler import SchedulerEngine, ScheduledTask, utc_now


class TestScheduledTask:
    """Test ScheduledTask class."""

    def test_create_task(self):
        """Test creating a scheduled task."""
        task = ScheduledTask(
            task_id="task_1",
            priority=5,
            dependencies=["task_0"],
        )
        assert task.task_id == "task_1"
        assert task.priority == 5
        assert task.status == "pending"
        assert task.dependencies == ["task_0"]
        assert task.retry_attempts == 0
        assert task.max_retry_attempts == 3
        assert task.conflict_history == []

    def test_task_comparison(self):
        """Test task priority comparison."""
        task1 = ScheduledTask(task_id="task_1", priority=5)
        task2 = ScheduledTask(task_id="task_2", priority=10)
        # Higher priority should be "less than" (for min heap)
        assert task2 < task1


class TestSchedulerEngine:
    """Test SchedulerEngine class."""

    def test_add_task(self):
        """Test adding task to scheduler."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        assert "task_1" in scheduler.tasks
        assert scheduler.tasks["task_1"].priority == 5

    def test_add_duplicate_task_fails(self):
        """Test that adding duplicate task fails."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        with pytest.raises(ValueError, match="already scheduled"):
            scheduler.add_task("task_1", priority=10)

    def test_detect_conflicts_no_dependencies(self):
        """Test conflict detection with no dependencies."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        conflicts = scheduler.detect_conflicts("task_1")
        assert len(conflicts) == 0

    def test_detect_conflicts_pending_dependency(self):
        """Test conflict detection with pending dependency."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5, dependencies=["task_1"])

        conflicts = scheduler.detect_conflicts("task_2")
        assert "task_1" in conflicts

    def test_detect_conflicts_completed_dependency(self):
        """Test no conflict when dependency is completed."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5, dependencies=["task_1"])

        # Mark task_1 as completed
        scheduler.tasks["task_1"].status = "completed"

        conflicts = scheduler.detect_conflicts("task_2")
        assert len(conflicts) == 0

    def test_detect_conflicts_running_dependency(self):
        """Test conflict when dependency is still running."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5, dependencies=["task_1"])

        # Mark task_1 as running (not completed)
        scheduler.tasks["task_1"].status = "running"

        conflicts = scheduler.detect_conflicts("task_2")
        assert "task_1" in conflicts

    def test_detect_permanent_conflict_failed_dependency(self):
        """Test permanent conflict detection for failed dependencies."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5, dependencies=["task_1"])
        scheduler.mark_failed("task_1")

        conflicts = scheduler.detect_permanent_conflict("task_2")
        assert conflicts == ["task_1"]

    def test_detect_permanent_conflict_missing_dependency(self):
        """Test permanent conflict detection for missing dependencies."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_2", priority=5, dependencies=["missing_task"])

        conflicts = scheduler.detect_permanent_conflict("task_2")
        assert conflicts == ["missing_task"]

    def test_execute_scheduled_tasks_no_conflicts(self):
        """Test executing tasks with no conflicts."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5)

        scheduler.execute_scheduled_tasks()

        # Both should be running
        assert len(scheduler.running_tasks) == 2
        assert scheduler.tasks["task_1"].status == "running"
        assert scheduler.tasks["task_2"].status == "running"

    def test_execute_scheduled_tasks_with_conflicts(self):
        """Test executing tasks with conflicts."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5, dependencies=["task_1"])

        scheduler.execute_scheduled_tasks()

        # Only task_1 should be running
        assert len(scheduler.running_tasks) == 1
        assert "task_1" in scheduler.running_tasks
        assert scheduler.tasks["task_2"].status == "pending"
        assert scheduler.tasks["task_2"].retry_attempts == 1
        assert scheduler.tasks["task_2"].conflict_history[-1]["conflicts"] == ["task_1"]

    def test_task_with_failed_dependency_fails_immediately(self):
        """Test task with failed dependency fails without retry dead loop."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=10)
        scheduler.add_task("task_2", priority=5, dependencies=["task_1"])
        scheduler.mark_failed("task_1")

        scheduler.execute_scheduled_tasks()

        assert scheduler.tasks["task_2"].status == "failed"
        assert scheduler.tasks["task_2"].next_retry_at is None
        assert scheduler.tasks["task_2"].retry_attempts == 1
        assert scheduler.tasks["task_2"].conflict_history[-1]["permanent_conflicts"] == ["task_1"]
        assert all(task_id != "task_2" for _, task_id in scheduler.execution_queue)

    def test_task_exceeding_max_retries_fails(self):
        """Test task is failed after exceeding its conflict retry limit."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task(
            "task_2",
            priority=1,
            dependencies=["task_1"],
            max_retry_attempts=2,
        )

        for _ in range(3):
            scheduler.execute_scheduled_tasks()
            scheduler.tasks["task_2"].next_retry_at = utc_now() - timedelta(seconds=1)

        assert scheduler.tasks["task_2"].status == "failed"
        assert scheduler.tasks["task_2"].retry_attempts == 3
        assert len(scheduler.tasks["task_2"].conflict_history) == 3
        assert all(task_id != "task_2" for _, task_id in scheduler.execution_queue)

    def test_task_with_completed_dependency_runs(self):
        """Test task with completed dependency starts running."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=10)
        scheduler.add_task("task_2", priority=5, dependencies=["task_1"])
        scheduler.tasks["task_1"].status = "completed"
        scheduler.completed_tasks.add("task_1")

        scheduler.execute_scheduled_tasks()

        assert scheduler.tasks["task_2"].status == "running"
        assert "task_2" in scheduler.running_tasks
        assert scheduler.tasks["task_2"].retry_attempts == 0

    def test_multiple_retries_with_eventual_success(self):
        """Test temporary dependency conflicts can resolve before retry limit."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=10)
        scheduler.add_task(
            "task_2",
            priority=5,
            dependencies=["task_1"],
            max_retry_attempts=3,
        )

        scheduler.execute_scheduled_tasks()
        assert scheduler.tasks["task_2"].status == "pending"
        assert scheduler.tasks["task_2"].retry_attempts == 1

        scheduler.tasks["task_2"].next_retry_at = utc_now() - timedelta(seconds=1)
        scheduler.execute_scheduled_tasks()
        assert scheduler.tasks["task_2"].status == "pending"
        assert scheduler.tasks["task_2"].retry_attempts == 2

        scheduler.mark_completed("task_1")
        scheduler.tasks["task_2"].next_retry_at = utc_now() - timedelta(seconds=1)
        scheduler.execute_scheduled_tasks()

        assert scheduler.tasks["task_2"].status == "running"
        assert "task_2" in scheduler.running_tasks
        assert scheduler.tasks["task_2"].retry_attempts == 0
        assert len(scheduler.tasks["task_2"].conflict_history) == 2

    def test_execute_respects_max_concurrent(self):
        """Test that execution respects max concurrent limit."""
        scheduler = SchedulerEngine(max_concurrent_tasks=2)
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5)
        scheduler.add_task("task_3", priority=5)

        scheduler.execute_scheduled_tasks()

        # Only 2 should be running
        assert len(scheduler.running_tasks) == 2

    def test_mark_completed(self):
        """Test marking task as completed."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.tasks["task_1"].status = "running"
        scheduler.running_tasks.add("task_1")

        scheduler.mark_completed("task_1")

        assert scheduler.tasks["task_1"].status == "completed"
        assert "task_1" not in scheduler.running_tasks
        assert "task_1" in scheduler.completed_tasks

    def test_mark_failed(self):
        """Test marking task as failed."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.tasks["task_1"].status = "running"
        scheduler.running_tasks.add("task_1")

        scheduler.mark_failed("task_1")

        assert scheduler.tasks["task_1"].status == "failed"
        assert "task_1" not in scheduler.running_tasks

    def test_get_running_tasks(self):
        """Test getting running tasks."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5)
        scheduler.tasks["task_1"].status = "running"
        scheduler.running_tasks.add("task_1")

        running = scheduler.get_running_tasks()
        assert "task_1" in running
        assert "task_2" not in running

    def test_get_completed_tasks(self):
        """Test getting completed tasks."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5)
        scheduler.mark_completed("task_1")

        completed = scheduler.get_completed_tasks()
        assert "task_1" in completed
        assert "task_2" not in completed

    def test_get_task_status(self):
        """Test getting task status."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)

        status = scheduler.get_task_status("task_1")
        assert status == "pending"

    def test_deferred_tasks_with_backoff(self):
        """Test that conflicted tasks are deferred with backoff."""
        scheduler = SchedulerEngine()
        scheduler.add_task("task_1", priority=5)
        scheduler.add_task("task_2", priority=5, dependencies=["task_1"])

        # First execution: task_2 should be deferred
        scheduler.execute_scheduled_tasks()
        assert scheduler.tasks["task_2"].next_retry_at is not None

        # Immediate retry should not execute task_2
        scheduler.execute_scheduled_tasks()
        assert scheduler.tasks["task_2"].status == "pending"

    def test_concurrent_add_and_execute_is_thread_safe(self):
        """Test concurrent scheduler access does not corrupt shared state."""
        scheduler = SchedulerEngine(max_concurrent_tasks=20)

        def add_task(index):
            scheduler.add_task(f"task_{index}", priority=index % 5)

        with ThreadPoolExecutor(max_workers=8) as executor:
            list(executor.map(add_task, range(50)))

        with ThreadPoolExecutor(max_workers=4) as executor:
            list(executor.map(lambda _: scheduler.execute_scheduled_tasks(), range(8)))

        assert len(scheduler.tasks) == 50
        assert len(scheduler.running_tasks) <= 20
        assert len(set(scheduler.execution_queue)) == len(scheduler.execution_queue)
