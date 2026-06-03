"""Tests for task plan domain models."""

import pytest

from agentManager.domain.task_plan import (
    TaskPlan,
    TaskPlanItem,
    TaskPlanItemStatus,
    TaskPlanStatus,
)


class TestTaskPlanItemStatus:
    def test_values(self) -> None:
        assert TaskPlanItemStatus.PENDING_REVIEW.value == "pending_review"
        assert TaskPlanItemStatus.CONFIRMED.value == "confirmed"

    def test_from_string(self) -> None:
        assert TaskPlanItemStatus("pending_review") == TaskPlanItemStatus.PENDING_REVIEW


class TestTaskPlanItem:
    def test_minimal(self) -> None:
        item = TaskPlanItem(id="1", title="Do something")
        assert item.status == TaskPlanItemStatus.PENDING_REVIEW
        assert item.dependencies == []
        assert item.required_skills == []
        assert item.verification == ""

    def test_requires_id(self) -> None:
        with pytest.raises(ValueError, match="id"):
            TaskPlanItem(id="", title="Test")

    def test_requires_title(self) -> None:
        with pytest.raises(ValueError, match="title"):
            TaskPlanItem(id="1", title="")

    def test_rejects_negative_priority(self) -> None:
        with pytest.raises(ValueError, match="priority"):
            TaskPlanItem(id="1", title="Test", priority=-1)

    def test_coerces_status_from_string(self) -> None:
        item = TaskPlanItem(id="1", title="Test", status="confirmed")
        assert item.status == TaskPlanItemStatus.CONFIRMED

    def test_round_trip(self) -> None:
        item = TaskPlanItem(
            id="t.1",
            title="Build API",
            description="Implement REST endpoint",
            priority=2,
            dependencies=["t.0"],
            assignee="worker",
            required_skills=["python"],
            workdir="/workspace",
            verification="pytest tests/unit/test_api.py -q",
            status=TaskPlanItemStatus.CONFIRMED,
        )
        data = item.to_dict()
        restored = TaskPlanItem.from_dict(data)
        assert restored.id == item.id
        assert restored.title == item.title
        assert restored.priority == item.priority
        assert restored.dependencies == item.dependencies


class TestTaskPlanStatus:
    def test_values(self) -> None:
        assert TaskPlanStatus.DRAFT.value == "draft"
        assert TaskPlanStatus.CONFIRMED.value == "confirmed"


class TestTaskPlan:
    def test_minimal(self) -> None:
        plan = TaskPlan(plan_id="p1")
        assert plan.status == TaskPlanStatus.DRAFT
        assert plan.items == []
        assert plan.created_by == "manager"

    def test_requires_plan_id(self) -> None:
        with pytest.raises(ValueError, match="plan_id"):
            TaskPlan(plan_id="")

    def test_coerces_status_from_string(self) -> None:
        plan = TaskPlan(plan_id="p1", status="confirmed")
        assert plan.status == TaskPlanStatus.CONFIRMED

    def test_coerces_items_from_dicts(self) -> None:
        plan = TaskPlan(
            plan_id="p1",
            items=[{"id": "1", "title": "First"}, {"id": "2", "title": "Second"}],
        )
        assert len(plan.items) == 2
        assert isinstance(plan.items[0], TaskPlanItem)
        assert plan.items[0].id == "1"

    def test_validate_dependencies_valid(self) -> None:
        plan = TaskPlan(
            plan_id="p1",
            items=[
                TaskPlanItem(id="a", title="A"),
                TaskPlanItem(id="b", title="B", dependencies=["a"]),
            ],
        )
        plan.validate_dependencies()  # should not raise

    def test_validate_dependencies_invalid(self) -> None:
        plan = TaskPlan(
            plan_id="p1",
            items=[
                TaskPlanItem(id="a", title="A"),
                TaskPlanItem(id="b", title="B", dependencies=["nonexistent"]),
            ],
        )
        with pytest.raises(ValueError, match="Invalid dependencies"):
            plan.validate_dependencies()

    def test_validate_dependencies_rejects_duplicate_item_ids(self) -> None:
        plan = TaskPlan(
            plan_id="p1",
            items=[
                TaskPlanItem(id="a", title="A"),
                TaskPlanItem(id="a", title="Duplicate A"),
            ],
        )
        with pytest.raises(ValueError, match="Duplicate task plan item id"):
            plan.validate_dependencies()

    def test_validate_verification_all_present(self) -> None:
        plan = TaskPlan(
            plan_id="p1",
            items=[
                TaskPlanItem(id="a", title="A", verification="run tests"),
                TaskPlanItem(id="b", title="B", verification="check output"),
            ],
        )
        plan.validate_verification()  # should not raise

    def test_validate_verification_missing(self) -> None:
        plan = TaskPlan(
            plan_id="p1",
            items=[
                TaskPlanItem(id="a", title="A", verification="run tests"),
                TaskPlanItem(id="b", title="B"),  # no verification
            ],
        )
        with pytest.raises(ValueError, match="Items missing verification"):
            plan.validate_verification()

    def test_from_subtasks(self) -> None:
        subtasks = [
            {"id": "t.1", "description": "define schema", "status": "pending"},
            {"id": "t.2", "description": "implement endpoint", "status": "pending"},
        ]
        plan = TaskPlan.from_subtasks("build-api", subtasks)
        assert plan.plan_id == "plan-build-api"
        assert plan.source_task_id == "build-api"
        assert len(plan.items) == 2
        assert plan.items[0].title == "define schema"
        assert plan.items[0].status == TaskPlanItemStatus.PENDING_REVIEW

    def test_from_subtasks_auto_generates_verification(self) -> None:
        subtasks = [{"id": "t.1", "description": "build feature"}]
        plan = TaskPlan.from_subtasks("task1", subtasks)
        assert "build feature" in plan.items[0].verification

    def test_from_subtasks_preserves_explicit_verification(self) -> None:
        subtasks = [
            {
                "id": "t.1",
                "description": "build feature",
                "verification": "run specific test",
            }
        ]
        plan = TaskPlan.from_subtasks("task1", subtasks)
        assert plan.items[0].verification == "run specific test"

    def test_round_trip(self) -> None:
        plan = TaskPlan(
            plan_id="p1",
            source_task_id="t1",
            items=[
                TaskPlanItem(id="a", title="A", verification="check A"),
                TaskPlanItem(id="b", title="B", verification="check B"),
            ],
            status=TaskPlanStatus.PENDING_REVIEW,
        )
        data = plan.to_dict()
        restored = TaskPlan.from_dict(data)
        assert restored.plan_id == plan.plan_id
        assert restored.source_task_id == plan.source_task_id
        assert len(restored.items) == 2
