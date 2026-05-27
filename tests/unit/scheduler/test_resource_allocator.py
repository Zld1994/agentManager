"""Tests for ResourceAllocator."""

import pytest

from agentManager.scheduler import ResourceAllocator, ResourceRequest


def test_allocate_and_release_resources() -> None:
    allocator = ResourceAllocator(total_cpu=4.0, total_memory=8.0, total_gpu=1.0)
    request = ResourceRequest(cpu=2.0, memory=4.0, gpu=0.5)

    assert allocator.allocate("task-1", request) is True
    assert allocator.get_allocated() == {"cpu": 2.0, "memory": 4.0, "gpu": 0.5}
    assert allocator.get_available() == {"cpu": 2.0, "memory": 4.0, "gpu": 0.5}

    allocator.release("task-1")

    assert allocator.get_allocated() == {"cpu": 0, "memory": 0, "gpu": 0}
    assert allocator.get_available() == {"cpu": 4.0, "memory": 8.0, "gpu": 1.0}


def test_allocate_fails_when_capacity_is_insufficient() -> None:
    allocator = ResourceAllocator(total_cpu=1.0, total_memory=2.0)

    assert allocator.allocate("task-1", ResourceRequest(cpu=2.0)) is False
    assert allocator.allocations == {}


def test_allocate_fails_for_duplicate_task_id() -> None:
    allocator = ResourceAllocator(total_cpu=4.0, total_memory=8.0)

    assert allocator.allocate("task-1", ResourceRequest(cpu=1.0)) is True
    assert allocator.allocate("task-1", ResourceRequest(cpu=1.0)) is False


def test_negative_resource_request_is_rejected() -> None:
    with pytest.raises(ValueError, match="cpu must be non-negative"):
        ResourceRequest(cpu=-1.0)
