"""Worker role for task execution."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from agentManager.roles.base import BaseRole


@dataclass
class WorkerRole(BaseRole):
    """Executes individual task payloads."""

    name: str = "worker"
    description: str = "Executes assigned tasks."
    capabilities: List[str] = field(default_factory=lambda: ["execute_task"])

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute a task action when provided, otherwise echo completion."""
        task_id = str(task.get("id", task.get("task_id", "task")))
        action = task.get("action")

        try:
            result = action(task) if callable(action) else task.get("payload", task)
        except Exception as exc:
            return {
                "role": self.name,
                "task_id": task_id,
                "status": "failed",
                "error": str(exc),
            }

        return {
            "role": self.name,
            "task_id": task_id,
            "status": "completed",
            "result": result,
        }
