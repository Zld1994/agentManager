"""Event bus module exports with lazy backend loading."""

from importlib import import_module
from typing import Any

__all__ = [
    "BaseEventBus",
    "Event",
    "EventType",
    "EventBus",
    "InMemoryEventBus",
    "RedisStreamEventBus",
]

_SYMBOL_TO_MODULE = {
    "BaseEventBus": "agentManager.engine.event_bus.base",
    "Event": "agentManager.engine.event_bus.base",
    "EventType": "agentManager.engine.event_bus.base",
    "InMemoryEventBus": "agentManager.engine.event_bus.in_memory",
    "RedisStreamEventBus": "agentManager.engine.event_bus.redis_stream",
}


def __getattr__(name: str) -> Any:
    """Resolve event bus exports lazily."""
    if name == "EventBus":
        from agentManager.engine.event_bus.in_memory import InMemoryEventBus

        globals()["EventBus"] = InMemoryEventBus
        return InMemoryEventBus

    module_name = _SYMBOL_TO_MODULE.get(name)
    if module_name is None:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")

    module = import_module(module_name)
    value = getattr(module, name)
    globals()[name] = value
    return value


def __dir__() -> list[str]:
    """Return module attributes for interactive use."""
    return sorted(set(globals()) | set(__all__))
