"""Task scheduler for ordering and executing scheduled work."""

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional

from agentManager.scheduler.priority_queue import PriorityQueue
from agentManager.scheduler.resource_allocator import ResourceAllocator, ResourceRequest


@dataclass
class ScheduledTask:
    """Task scheduled for later execution."""

    task_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    priority: int = 0
    resources: ResourceRequest = field(default_factory=ResourceRequest)
    status: str = "scheduled"


class TaskScheduler:
    """Schedules tasks by priority and optional resource capacity."""

    def __init__(self, resource_allocator: Optional[ResourceAllocator] = None) -> None:
        self.resource_allocator = resource_allocator
        self._tasks: Dict[str, ScheduledTask] = {}
        self._queue = PriorityQueue()

    def schedule(
        self,
        task_id: str,
        payload: Optional[Dict[str, Any]] = None,
        priority: int = 0,
        resources: Optional[ResourceRequest] = None,
    ) -> ScheduledTask:
        """Schedule a task for execution."""
        if task_id in self._tasks:
            raise ValueError(f"Task {task_id} already scheduled")

        task = ScheduledTask(
            task_id=task_id,
            payload=payload or {},
            priority=priority,
            resources=resources or ResourceRequest(),
        )
        self._tasks[task_id] = task
        self._queue.push(task_id, priority)
        return task

    def get_scheduled_tasks(self) -> List[ScheduledTask]:
        """Return tasks that are still scheduled, ordered by priority."""
        return sorted(
            (task for task in self._tasks.values() if task.status == "scheduled"),
            key=lambda task: task.priority,
            reverse=True,
        )

    def execute_scheduled(
        self,
        executor: Callable[[ScheduledTask], Any],
        limit: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """Execute scheduled tasks in priority order."""
        results: List[Dict[str, Any]] = []

        while len(self._queue) and (limit is None or len(results) < limit):
            task_id = self._queue.pop()
            task = self._tasks[task_id]

            if task.status != "scheduled":
                continue

            if self.resource_allocator and not self.resource_allocator.allocate(
                task.task_id, task.resources
            ):
                self._queue.push(task_id, task.priority)
                break

            task.status = "running"
            try:
                result = executor(task)
            except Exception as exc:
                task.status = "failed"
                if self.resource_allocator:
                    self.resource_allocator.release(task.task_id)
                results.append({"task_id": task.task_id, "status": "failed", "error": str(exc)})
                continue

            task.status = "completed"
            if self.resource_allocator:
                self.resource_allocator.release(task.task_id)
            results.append({"task_id": task.task_id, "status": "completed", "result": result})

        return results
