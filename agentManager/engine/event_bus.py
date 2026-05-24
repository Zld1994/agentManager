"""Event Bus for task event publishing and subscription.

This module provides an in-memory event bus for task lifecycle events.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Callable, Optional
from datetime import datetime
import logging

logger = logging.getLogger(__name__)


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
    event_id: str
    event_type: EventType
    workflow_id: str
    payload: Dict = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def __hash__(self):
        return hash(self.event_id)


class EventBus:
    """In-memory event bus for task events."""

    def __init__(self):
        """Initialize event bus."""
        self.subscribers: Dict[str, List[Callable]] = {}
        self.events: List[Event] = []

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
        # Create subscription key: "event_type:workflow_id" or "event_type:*"
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
        self.events.append(event)
        logger.info(f"Published event: {event.event_type.value} for workflow {event.workflow_id}")

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
