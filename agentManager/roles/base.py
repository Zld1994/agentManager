"""Base role abstractions for agent orchestration."""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List


@dataclass
class BaseRole(ABC):
    """Abstract base class for agent roles."""

    name: str
    description: str
    capabilities: List[str] = field(default_factory=list)

    def can_handle(self, capability: str) -> bool:
        """Return whether this role exposes a capability."""
        return capability in self.capabilities

    @abstractmethod
    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute role-specific behavior for a task."""
