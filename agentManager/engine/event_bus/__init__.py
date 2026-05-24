"""Event Bus module for task event publishing and subscription.

Supports both in-memory and Redis Streams backends.
"""

from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType
from agentManager.engine.event_bus.in_memory import InMemoryEventBus
from agentManager.engine.event_bus.redis_stream import RedisStreamEventBus

# Backward compatibility: EventBus is an alias for InMemoryEventBus
EventBus = InMemoryEventBus

__all__ = [
    "BaseEventBus",
    "Event",
    "EventType",
    "EventBus",
    "InMemoryEventBus",
    "RedisStreamEventBus",
]
