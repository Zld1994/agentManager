"""Supervisor role for monitoring and recovery guidance."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from agentManager.roles.base import BaseRole


@dataclass
class SupervisorRole(BaseRole):
    """Monitors task results and recommends recovery actions."""

    name: str = "supervisor"
    description: str = "Monitors execution health and recommends recovery."
    capabilities: List[str] = field(
        default_factory=lambda: ["monitor_task", "recover_task", "escalate_failure"]
    )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Inspect task status and return a monitoring decision."""
        task_id = str(task.get("id", task.get("task_id", "task")))
        status = task.get("status", "unknown")
        failures = task.get("failures", [])

        if status == "failed" or failures:
            action = "recover" if task.get("recoverable", True) else "escalate"
            health = "unhealthy"
        elif status in {"completed", "running", "pending"}:
            action = "continue"
            health = "healthy"
        else:
            action = "inspect"
            health = "unknown"

        return {
            "role": self.name,
            "task_id": task_id,
            "status": "monitored",
            "health": health,
            "recommended_action": action,
        }
