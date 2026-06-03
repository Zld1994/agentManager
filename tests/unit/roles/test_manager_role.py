"""Tests for ManagerRole."""

from agentManager.roles import ManagerRole


def test_manager_role_decomposes_explicit_subtasks() -> None:
    role = ManagerRole()

    result = role.execute(
        {
            "id": "build-api",
            "subtasks": ["define schema", "implement endpoint", "add tests"],
        }
    )

    assert result["status"] == "decomposed"
    assert [task["id"] for task in result["subtasks"]] == [
        "build-api.1",
        "build-api.2",
        "build-api.3",
    ]
    assert result["subtasks"][0]["description"] == "define schema"


def test_manager_role_preserves_subtask_metadata() -> None:
    role = ManagerRole()

    result = role.execute(
        {
            "task_id": "repair",
            "steps": [{"description": "classify error", "assignee": "worker"}],
        }
    )

    subtask = result["subtasks"][0]
    assert subtask["id"] == "repair.1"
    assert subtask["assignee"] == "worker"
    assert subtask["status"] == "pending"


def test_manager_role_returns_task_plan_alongside_subtasks() -> None:
    role = ManagerRole()
    result = role.execute({"id": "feat", "subtasks": ["design", "implement", "test"]})
    assert "task_plan" in result
    assert "subtasks" in result
    plan = result["task_plan"]
    assert plan["plan_id"] == "plan-feat"
    assert plan["source_task_id"] == "feat"
    assert len(plan["items"]) == 3


def test_task_plan_items_have_pending_review_status() -> None:
    role = ManagerRole()
    result = role.execute({"id": "t", "subtasks": ["a", "b"]})
    plan = result["task_plan"]
    for item in plan["items"]:
        assert item["status"] == "pending_review"


def test_task_plan_auto_generates_verification() -> None:
    role = ManagerRole()
    result = role.execute({"id": "t", "subtasks": ["build feature"]})
    plan = result["task_plan"]
    assert "build feature" in plan["items"][0]["verification"]


def test_task_plan_preserves_explicit_verification() -> None:
    role = ManagerRole()
    result = role.execute(
        {
            "id": "t",
            "subtasks": [
                {"description": "build", "verification": "run specific test"},
            ],
        }
    )
    plan = result["task_plan"]
    assert plan["items"][0]["verification"] == "run specific test"
