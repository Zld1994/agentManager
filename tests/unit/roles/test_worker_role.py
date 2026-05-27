"""Tests for WorkerRole."""

from agentManager.roles import WorkerRole


def test_worker_role_executes_callable_action() -> None:
    role = WorkerRole()

    result = role.execute(
        {
            "id": "sum",
            "payload": {"a": 2, "b": 3},
            "action": lambda task: task["payload"]["a"] + task["payload"]["b"],
        }
    )

    assert result == {
        "role": "worker",
        "task_id": "sum",
        "status": "completed",
        "result": 5,
    }


def test_worker_role_reports_action_failure() -> None:
    role = WorkerRole()

    def fail(_task):
        raise RuntimeError("boom")

    result = role.execute({"id": "bad-task", "action": fail})

    assert result["status"] == "failed"
    assert result["task_id"] == "bad-task"
    assert result["error"] == "boom"
