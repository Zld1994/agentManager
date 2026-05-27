"""Tests for TaskScheduler."""

from agentManager.scheduler import ResourceAllocator, ResourceRequest, TaskScheduler


def test_schedule_returns_scheduled_tasks_by_priority() -> None:
    scheduler = TaskScheduler()

    scheduler.schedule("low", priority=1)
    scheduler.schedule("high", priority=10)
    scheduler.schedule("mid", priority=5)

    assert [task.task_id for task in scheduler.get_scheduled_tasks()] == [
        "high",
        "mid",
        "low",
    ]


def test_execute_scheduled_runs_in_priority_order() -> None:
    scheduler = TaskScheduler()
    scheduler.schedule("low", priority=1)
    scheduler.schedule("high", priority=10)

    results = scheduler.execute_scheduled(lambda task: task.task_id)

    assert [result["task_id"] for result in results] == ["high", "low"]
    assert all(result["status"] == "completed" for result in results)
    assert scheduler.get_scheduled_tasks() == []


def test_execute_scheduled_respects_resource_capacity() -> None:
    allocator = ResourceAllocator(total_cpu=2.0, total_memory=4.0)
    scheduler = TaskScheduler(resource_allocator=allocator)
    scheduler.schedule("too-large", priority=10, resources=ResourceRequest(cpu=3.0))
    scheduler.schedule("fits", priority=1, resources=ResourceRequest(cpu=1.0))

    results = scheduler.execute_scheduled(lambda task: task.task_id)

    assert results == []
    assert [task.task_id for task in scheduler.get_scheduled_tasks()] == ["too-large", "fits"]


def test_execute_scheduled_limit() -> None:
    scheduler = TaskScheduler()
    scheduler.schedule("one", priority=1)
    scheduler.schedule("two", priority=2)

    results = scheduler.execute_scheduled(lambda task: task.task_id, limit=1)

    assert [result["task_id"] for result in results] == ["two"]
    assert [task.task_id for task in scheduler.get_scheduled_tasks()] == ["one"]
