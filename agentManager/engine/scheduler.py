"""Scheduler for task execution management.

This module manages task scheduling, conflict detection, and retry limits so
pending tasks cannot be deferred forever when dependencies are unsatisfiable.
"""

import heapq
import logging
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from threading import RLock
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@dataclass
class ScheduledTask:
    """Represents a scheduled task.

    retry_attempts and conflict_history are used to prevent scheduler dead
    loops when a pending task repeatedly encounters dependency conflicts.
    """

    task_id: str
    priority: int = 0
    status: str = "pending"
    dependencies: List[str] = field(default_factory=list)
    next_retry_at: Optional[datetime] = None
    retry_attempts: int = 0
    max_retry_attempts: int = 3
    conflict_history: List[Dict[str, object]] = field(default_factory=list)

    def __lt__(self, other):
        """Compare by priority (higher priority first)."""
        return -self.priority < -other.priority


class SchedulerEngine:
    """Manages task scheduling and execution."""

    def __init__(self, max_concurrent_tasks: int = 10):
        """Initialize scheduler.

        Args:
            max_concurrent_tasks: Maximum concurrent tasks
        """
        self.max_concurrent_tasks = max_concurrent_tasks
        self.tasks: Dict[str, ScheduledTask] = {}
        self.execution_queue: List = []
        self.running_tasks: Set[str] = set()
        self.completed_tasks: Set[str] = set()
        self._lock = RLock()

    def add_task(
        self,
        task_id: str,
        priority: int = 0,
        dependencies: Optional[List[str]] = None,
        max_retry_attempts: int = 3,
    ) -> None:
        """Add task to scheduler.

        Args:
            task_id: Task ID
            priority: Task priority (higher = more urgent)
            dependencies: List of dependency task IDs
            max_retry_attempts: Maximum conflict deferrals before failure
        """
        with self._lock:
            if task_id in self.tasks:
                raise ValueError(f"Task {task_id} already scheduled")

            task = ScheduledTask(
                task_id=task_id,
                priority=priority,
                dependencies=dependencies or [],
                max_retry_attempts=max_retry_attempts,
            )
            self.tasks[task_id] = task
            heapq.heappush(self.execution_queue, (-priority, task_id))
        logger.info(f"Added task {task_id} with priority {priority}")

    def detect_conflicts(self, task_id: str) -> List[str]:
        """Detect if task has unmet dependencies.

        Args:
            task_id: Task ID to check

        Returns:
            List of unmet dependency task IDs
        """
        with self._lock:
            if task_id not in self.tasks:
                return []

            task = self.tasks[task_id]
            conflicts = []

            for dep_id in task.dependencies:
                if dep_id not in self.tasks:
                    conflicts.append(dep_id)
                    continue

                dep_task = self.tasks[dep_id]
                # Dependency must be COMPLETED, not just running
                if dep_task.status != "completed":
                    conflicts.append(dep_id)

            return conflicts

    def detect_permanent_conflict(self, task_id: str) -> List[str]:
        """Detect dependency conflicts that cannot resolve by retrying.

        A dependency is permanently conflicted when it is missing from the
        scheduler or already failed. In either case, the dependent task cannot
        become runnable through backoff retries alone.

        Args:
            task_id: Task ID to check

        Returns:
            List of dependency IDs that are permanently unavailable
        """
        with self._lock:
            if task_id not in self.tasks:
                return []

            task = self.tasks[task_id]
            permanent_conflicts = []

            for dep_id in task.dependencies:
                dep_task = self.tasks.get(dep_id)
                if dep_task is None or dep_task.status == "failed":
                    permanent_conflicts.append(dep_id)

            return permanent_conflicts

    def execute_scheduled_tasks(self) -> None:
        """Execute ready tasks from queue.

        This method processes the execution queue, respecting:
        - Max concurrent task limit
        - Dependency constraints
        - Retry backoff for conflicted tasks
        - Permanent dependency failure detection
        - Per-task retry limits to prevent dead loops
        """
        with self._lock:
            deferred = []

            while self.execution_queue and len(self.running_tasks) < self.max_concurrent_tasks:
                _, task_id = heapq.heappop(self.execution_queue)

                # Skip if task not found or already processed
                if task_id not in self.tasks:
                    continue

                task = self.tasks[task_id]

                # Skip if not pending
                if task.status != "pending":
                    continue

                # Check if retry backoff is active
                if task.next_retry_at and utc_now() < task.next_retry_at:
                    deferred.append((-task.priority, task_id))
                    continue

                # Check for conflicts
                conflicts = self.detect_conflicts(task_id)

                if not conflicts:
                    # No conflicts, task can run
                    task.retry_attempts = 0
                    task.next_retry_at = None
                    task.status = "running"
                    self.running_tasks.add(task_id)
                    logger.info(f"Started task {task_id}")
                else:
                    permanent_conflicts = self.detect_permanent_conflict(task_id)
                    task.retry_attempts += 1
                    conflict_record = {
                        "attempt": task.retry_attempts,
                        "conflicts": list(conflicts),
                        "permanent_conflicts": list(permanent_conflicts),
                        "timestamp": utc_now(),
                    }
                    task.conflict_history.append(conflict_record)

                    if permanent_conflicts:
                        task.status = "failed"
                        task.next_retry_at = None
                        logger.error(
                            "Failed task %s due to permanent dependency conflicts: %s; "
                            "all conflicts: %s; attempt: %s",
                            task_id,
                            permanent_conflicts,
                            conflicts,
                            task.retry_attempts,
                        )
                        continue

                    if task.retry_attempts > task.max_retry_attempts:
                        task.status = "failed"
                        task.next_retry_at = None
                        logger.error(
                            "Failed task %s after exceeding max retry attempts "
                            "(attempts=%s, max=%s, conflicts=%s)",
                            task_id,
                            task.retry_attempts,
                            task.max_retry_attempts,
                            conflicts,
                        )
                        continue

                    # Has temporary conflicts, defer with backoff
                    backoff_seconds = 5
                    task.next_retry_at = utc_now() + timedelta(seconds=backoff_seconds)
                    deferred.append((-task.priority, task_id))
                    logger.debug(
                        "Deferred task %s, attempt %s/%s, conflicts: %s",
                        task_id,
                        task.retry_attempts,
                        task.max_retry_attempts,
                        conflicts,
                    )

            # Re-queue deferred tasks
            for item in deferred:
                heapq.heappush(self.execution_queue, item)

    def mark_completed(self, task_id: str) -> None:
        """Mark task as completed.

        Args:
            task_id: Task ID
        """
        with self._lock:
            if task_id not in self.tasks:
                raise ValueError(f"Task {task_id} not found")

            task = self.tasks[task_id]
            task.status = "completed"
            self.running_tasks.discard(task_id)
            self.completed_tasks.add(task_id)
        logger.info(f"Completed task {task_id}")

    def mark_failed(self, task_id: str) -> None:
        """Mark task as failed.

        Args:
            task_id: Task ID
        """
        with self._lock:
            if task_id not in self.tasks:
                raise ValueError(f"Task {task_id} not found")

            task = self.tasks[task_id]
            task.status = "failed"
            self.running_tasks.discard(task_id)
        logger.error(f"Failed task {task_id}")

    def get_running_tasks(self) -> List[str]:
        """Get list of running tasks.

        Returns:
            List of running task IDs
        """
        with self._lock:
            return list(self.running_tasks)

    def get_completed_tasks(self) -> List[str]:
        """Get list of completed tasks.

        Returns:
            List of completed task IDs
        """
        with self._lock:
            return list(self.completed_tasks)

    def get_task_status(self, task_id: str) -> Optional[str]:
        """Get task status.

        Args:
            task_id: Task ID

        Returns:
            Task status or None if not found
        """
        with self._lock:
            if task_id not in self.tasks:
                return None
            return self.tasks[task_id].status
