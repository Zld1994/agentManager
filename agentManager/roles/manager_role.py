"""Manager role for task decomposition and delegation."""

from dataclasses import dataclass, field
from typing import Any, Dict, List

from agentManager.domain.task_plan import TaskPlan
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

        enriched = [self._enrich_subtask_for_plan(st) for st in subtasks]
        task_plan = TaskPlan.from_subtasks(task_id, enriched)

        return {
            "role": self.name,
            "task_id": task_id,
            "status": "decomposed",
            "subtasks": subtasks,
            "task_plan": task_plan.to_dict(),
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

    def _enrich_subtask_for_plan(self, subtask: Dict[str, Any]) -> Dict[str, Any]:
        """Add task-plan-specific fields with defaults if missing."""
        enriched = subtask.copy()
        enriched.setdefault("title", enriched.get("description", enriched["id"]))
        enriched.setdefault("priority", 0)
        enriched.setdefault("required_skills", [])
        enriched.setdefault("workdir", "")
        title = enriched["title"]
        enriched.setdefault("verification", f"Verify {title} output is correct")
        return enriched
