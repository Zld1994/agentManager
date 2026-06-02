"""Base abstract class for event bus implementations.

Defines the interface that all event bus implementations must follow.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Callable, Optional, Any
from datetime import datetime, timezone
import uuid


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class EventType(str, Enum):
    """Task event types."""

    TASK_CREATED = "task_created"
    TASK_STARTED = "task_started"
    TASK_COMPLETED = "task_completed"
    TASK_FAILED = "task_failed"
    TASK_BLOCKED = "task_blocked"
    WORKFLOW_STARTED = "workflow_started"
    WORKFLOW_COMPLETED = "workflow_completed"
    WORKFLOW_FAILED = "workflow_failed"


@dataclass
class Event:
    """Represents a task event."""

    event_type: EventType
    workflow_id: str
    payload: Dict[str, Any] = field(default_factory=dict)
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=utc_now)

    def __hash__(self) -> int:
        return hash(self.event_id)

    def to_dict(self) -> Dict[str, Any]:
        """Convert event to dictionary."""
        return {
            "event_type": self.event_type.value,
            "workflow_id": self.workflow_id,
            "payload": self.payload,
            "event_id": self.event_id,
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Event":
        """Create event from dictionary."""
        return cls(
            event_type=EventType(data["event_type"]),
            workflow_id=data["workflow_id"],
            payload=data.get("payload", {}),
            event_id=data.get("event_id", str(uuid.uuid4())),
            timestamp=(
                datetime.fromisoformat(data["timestamp"])
                if isinstance(data.get("timestamp"), str)
                else data.get("timestamp", utc_now())
            ),
        )


class BaseEventBus(ABC):
    """Abstract base class for event bus implementations."""

    @abstractmethod
    async def subscribe(
        self,
        event_type: EventType,
        callback: Callable,
        workflow_id: Optional[str] = None,
    ) -> None:
        """Subscribe to events.

        Args:
            event_type: Type of event to subscribe to
            callback: Callback function to invoke
            workflow_id: Optional workflow ID for filtering (None = all workflows)
        """
        pass

    @abstractmethod
    async def publish(self, event: Event) -> None:
        """Publish an event.

        Args:
            event: Event to publish
        """
        pass

    @abstractmethod
    async def unsubscribe(
        self,
        event_type: EventType,
        callback: Callable,
        workflow_id: Optional[str] = None,
    ) -> None:
        """Unsubscribe from events.

        Args:
            event_type: Type of event
            callback: Callback to remove
            workflow_id: Optional workflow ID
        """
        pass

    @abstractmethod
    async def get_events(
        self,
        event_type: Optional[EventType] = None,
        workflow_id: Optional[str] = None,
    ) -> List[Event]:
        """Get events matching criteria.

        Args:
            event_type: Optional event type filter
            workflow_id: Optional workflow ID filter

        Returns:
            List of matching events
        """
        pass

    @abstractmethod
    async def clear(self) -> None:
        """Clear all events and subscribers."""
        pass
