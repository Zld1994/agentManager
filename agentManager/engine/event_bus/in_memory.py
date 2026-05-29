"""In-memory event bus implementation (backward compatible).

Provides synchronous interface for compatibility with existing code.
"""

import logging
from typing import Dict, List, Callable, Optional

from agentManager.engine.event_bus.base import Event, EventType
from agentManager.observability.logging import get_correlation_id

logger = logging.getLogger(__name__)


class InMemoryEventBus:
    """In-memory event bus for task events (synchronous)."""

    def __init__(self, max_events: int = 10000):
        """Initialize event bus."""
        self.subscribers: Dict[str, List[Callable]] = {}
        self.events: List[Event] = []
        self.max_events = max_events

    def subscribe(
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
        key = f"{event_type.value}:{workflow_id or '*'}"

        if key not in self.subscribers:
            self.subscribers[key] = []

        self.subscribers[key].append(callback)
        logger.info(f"Subscribed to {key}")

    def publish(self, event: Event) -> None:
        """Publish an event.

        Args:
            event: Event to publish
        """
        correlation_id = get_correlation_id()
        if correlation_id and "correlation_id" not in event.payload:
            event.payload = {**event.payload, "correlation_id": correlation_id}
        self.events.append(event)
        if self.max_events > 0 and len(self.events) > self.max_events:
            del self.events[:len(self.events) - self.max_events]
        logger.info(
            f"Published event: {event.event_type.value} for workflow {event.workflow_id}"
        )

        # Trigger both exact and wildcard subscriptions
        keys = [
            f"{event.event_type.value}:{event.workflow_id}",
            f"{event.event_type.value}:*",
        ]

        for key in keys:
            for callback in self.subscribers.get(key, []):
                try:
                    callback(event)
                except Exception as e:
                    logger.error(f"Error in subscriber callback for {key}: {e}")

    def unsubscribe(
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
        key = f"{event_type.value}:{workflow_id or '*'}"

        if key in self.subscribers and callback in self.subscribers[key]:
            self.subscribers[key].remove(callback)
            logger.info(f"Unsubscribed from {key}")

    def get_events(
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
        result = self.events

        if event_type:
            result = [e for e in result if e.event_type == event_type]

        if workflow_id:
            result = [e for e in result if e.workflow_id == workflow_id]

        return result

    def clear(self) -> None:
        """Clear all events and subscribers."""
        self.events.clear()
        self.subscribers.clear()
        logger.info("Event bus cleared")
