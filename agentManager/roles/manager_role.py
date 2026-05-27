"""Manager role for task decomposition and delegation."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from agentManager.roles.base import BaseRole


@dataclass
class ManagerRole(BaseRole):
    """Decomposes tasks into actionable subtasks."""

    name: str = "manager"
    description: str = "Decomposes tasks and prepares delegation plans."
    capabilities: List[str] = field(
        default_factory=lambda: ["decompose_task", "delegate_task", "plan_work"]
    )

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Create a delegation plan from explicit subtasks or steps."""
        task_id = str(task.get("id", task.get("task_id", "task")))
        raw_subtasks = task.get("subtasks") or task.get("steps") or []

        if not raw_subtasks:
            raw_subtasks = [task.get("description") or task.get("title") or "Execute task"]

        subtasks = [
            self._normalize_subtask(task_id=task_id, index=index, subtask=subtask)
            for index, subtask in enumerate(raw_subtasks, start=1)
        ]

        return {
            "role": self.name,
            "task_id": task_id,
            "status": "decomposed",
            "subtasks": subtasks,
        }

    def _normalize_subtask(
        self,
        task_id: str,
        index: int,
        subtask: Any,
    ) -> Dict[str, Any]:
        if isinstance(subtask, dict):
            normalized = subtask.copy()
            normalized.setdefault("id", f"{task_id}.{index}")
            normalized.setdefault("status", "pending")
            return normalized

        return {
            "id": f"{task_id}.{index}",
            "description": str(subtask),
            "status": "pending",
        }
