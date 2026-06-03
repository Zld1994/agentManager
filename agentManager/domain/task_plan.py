"""Task plan domain models for structured, verified task decomposition."""

from __future__ import annotations

import re as _re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any

from agentManager.domain.models import (
    _coerce_datetime,
    _coerce_enum,
    _model_to_dict,
    _require_non_empty,
    utc_now,
)


class TaskPlanItemStatus(str, Enum):
    """Statuses for individual task plan items."""

    PENDING_REVIEW = "pending_review"
    CONFIRMED = "confirmed"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class TaskPlanStatus(str, Enum):
    """Statuses for a task plan as a whole."""

    DRAFT = "draft"
    PENDING_REVIEW = "pending_review"
    CONFIRMED = "confirmed"
    EXECUTING = "executing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class TaskPlanItem:
    """A single verifiable item within a task plan."""

    id: str
    title: str
    description: str = ""
    priority: int = 0
    dependencies: list[str] = field(default_factory=list)
    assignee: str = ""
    required_skills: list[str] = field(default_factory=list)
    workdir: str = ""
    verification: str = ""
    status: TaskPlanItemStatus | str = TaskPlanItemStatus.PENDING_REVIEW
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.id, "id")
        _require_non_empty(self.title, "title")
        if self.priority < 0:
            raise ValueError(f"priority must be >= 0, got {self.priority}")
        self.status = _coerce_enum(self.status, TaskPlanItemStatus, "status")

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskPlanItem:
        return cls(**data)


@dataclass
class TaskPlan:
    """A structured, verified task plan produced by a manager role."""

    plan_id: str
    source_task_id: str = ""
    items: list[TaskPlanItem] = field(default_factory=list)
    created_by: str = "manager"
    status: TaskPlanStatus | str = TaskPlanStatus.DRAFT
    temporary_roles: list[str] = field(default_factory=list)
    selected_templates: list[str] = field(default_factory=list)
    preferred_assignees: list[str] = field(default_factory=list)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.plan_id, "plan_id")
        self.status = _coerce_enum(self.status, TaskPlanStatus, "status")
        self.created_at = _coerce_datetime(self.created_at)
        self.updated_at = _coerce_datetime(self.updated_at)
        self.items = [TaskPlanItem.from_dict(i) if isinstance(i, dict) else i for i in self.items]

    def validate_dependencies(self) -> None:
        """Check that all item dependencies reference existing item IDs.

        Raises:
            ValueError: With details about dangling dependency references.
        """
        valid_ids = {item.id for item in self.items}
        if len(valid_ids) != len(self.items):
            seen: set[str] = set()
            duplicates: list[str] = []
            for item in self.items:
                if item.id in seen and item.id not in duplicates:
                    duplicates.append(item.id)
                seen.add(item.id)
            raise ValueError("Duplicate task plan item id: " + ", ".join(duplicates))
        errors: list[str] = []
        for item in self.items:
            for dep in item.dependencies:
                if dep not in valid_ids:
                    errors.append(
                        f"Item '{item.id}' depends on '{dep}' " f"which does not exist in this plan"
                    )
        if errors:
            raise ValueError("Invalid dependencies: " + "; ".join(errors))

    def validate_verification(self) -> None:
        """Check that all items have non-empty verification criteria.

        Raises:
            ValueError: Listing items without verification.
        """
        missing = [item.id for item in self.items if not item.verification]
        if missing:
            raise ValueError(f"Items missing verification criteria: {missing}")

    _PLAN_ID_SAFE = _re.compile(r"[^A-Za-z0-9_.:-]")

    @classmethod
    def from_subtasks(
        cls,
        task_id: str,
        subtasks: list[dict[str, Any]],
    ) -> TaskPlan:
        """Convert ManagerRole subtask output into a TaskPlan.

        Auto-generates ``verification`` for items that lack one.

        Args:
            task_id: Source task identifier.
            subtasks: List of normalized subtask dicts from ManagerRole.

        Returns:
            A new ``TaskPlan`` instance.
        """
        # Sanitize task_id to produce a valid plan_id
        safe_task_id = cls._PLAN_ID_SAFE.sub("_", task_id)
        items: list[TaskPlanItem] = []
        for st in subtasks:
            item_id = str(st.get("id", ""))
            title = str(st.get("title", st.get("description", item_id)))
            verification = st.get("verification", f"Verify {title} output is correct")
            items.append(
                TaskPlanItem(
                    id=item_id,
                    title=title,
                    description=st.get("description", ""),
                    priority=st.get("priority", 0),
                    dependencies=st.get("dependencies", []),
                    assignee=st.get("assignee", ""),
                    required_skills=st.get("required_skills", []),
                    workdir=st.get("workdir", ""),
                    verification=verification,
                    status=TaskPlanItemStatus.PENDING_REVIEW,
                    metadata={
                        k: v
                        for k, v in st.items()
                        if k
                        not in {
                            "id",
                            "title",
                            "description",
                            "priority",
                            "dependencies",
                            "assignee",
                            "required_skills",
                            "workdir",
                            "verification",
                            "status",
                        }
                    },
                )
            )
        return cls(
            plan_id=f"plan-{safe_task_id}",
            source_task_id=task_id,
            items=items,
            status=TaskPlanStatus.PENDING_REVIEW,
        )

    def to_dict(self) -> dict[str, Any]:
        result = _model_to_dict(self)
        result["items"] = [
            item.to_dict() if hasattr(item, "to_dict") else item for item in self.items
        ]
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskPlan:
        return cls(**data)
