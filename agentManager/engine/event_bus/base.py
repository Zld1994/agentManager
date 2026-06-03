"""Base abstract class for event bus implementations.

Defines the interface that all event bus implementations must follow.
"""

from abc import ABC, abstractmethod
from typing import Callable, List, Optional

from agentManager.domain.models import Event, EventType

__all__ = ["BaseEventBus", "Event", "EventType"]


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
