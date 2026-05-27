"""agentManager engine module with lazy symbol loading."""

from importlib import import_module
from typing import Any

__all__ = [
    "DAGEngine",
    "DAGNode",
    "TaskStatus",
    "StateMachine",
    "TaskState",
    "StateTransition",
    "EventBus",
    "Event",
    "EventType",
    "SchedulerEngine",
    "ScheduledTask",
]

_SYMBOL_TO_MODULE = {
    "DAGEngine": "agentManager.engine.dag",
    "DAGNode": "agentManager.engine.dag",
    "TaskStatus": "agentManager.engine.dag",
    "StateMachine": "agentManager.engine.state_manager",
    "TaskState": "agentManager.engine.state_manager",
    "StateTransition": "agentManager.engine.state_manager",
    "EventBus": "agentManager.engine.event_bus",
    "Event": "agentManager.engine.event_bus",
    "EventType": "agentManager.engine.event_bus",
    "SchedulerEngine": "agentManager.engine.scheduler",
    "ScheduledTask": "agentManager.engine.scheduler",
}


def __getattr__(name: str) -> Any:
    """Lazily resolve engine symbols on first access."""
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
