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
