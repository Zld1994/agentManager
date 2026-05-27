"""Resource allocation primitives for scheduled tasks."""

from dataclasses import dataclass, field
from typing import Dict


@dataclass(frozen=True)
class ResourceRequest:
    """CPU, memory, and GPU resources requested by a task."""

    cpu: float = 0.0
    memory: float = 0.0
    gpu: float = 0.0

    def __post_init__(self) -> None:
        for name in ("cpu", "memory", "gpu"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")


@dataclass
class ResourceAllocator:
    """Allocates CPU, memory, and GPU resources to tasks."""

    total_cpu: float
    total_memory: float
    total_gpu: float = 0.0
    allocations: Dict[str, ResourceRequest] = field(default_factory=dict)

    def __post_init__(self) -> None:
        for name in ("total_cpu", "total_memory", "total_gpu"):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be non-negative")

    def allocate(self, task_id: str, request: ResourceRequest) -> bool:
        """Allocate resources to a task if capacity allows."""
        if task_id in self.allocations or not self.can_allocate(request):
            return False

        self.allocations[task_id] = request
        return True

    def release(self, task_id: str) -> None:
        """Release resources for a task if it has an allocation."""
        self.allocations.pop(task_id, None)

    def can_allocate(self, request: ResourceRequest) -> bool:
        """Return whether the requested resources are available."""
        available = self.get_available()
        return (
            available["cpu"] >= request.cpu
            and available["memory"] >= request.memory
            and available["gpu"] >= request.gpu
        )

    def get_available(self) -> Dict[str, float]:
        """Return available resources by type."""
        allocated = self.get_allocated()
        return {
            "cpu": self.total_cpu - allocated["cpu"],
            "memory": self.total_memory - allocated["memory"],
            "gpu": self.total_gpu - allocated["gpu"],
        }

    def get_allocated(self) -> Dict[str, float]:
        """Return allocated resources by type."""
        return {
            "cpu": sum(request.cpu for request in self.allocations.values()),
            "memory": sum(request.memory for request in self.allocations.values()),
            "gpu": sum(request.gpu for request in self.allocations.values()),
        }
