"""Role classes for agent orchestration."""

from agentManager.roles.base import BaseRole
from agentManager.roles.manager_role import ManagerRole
from agentManager.roles.supervisor_role import SupervisorRole
from agentManager.roles.worker_role import WorkerRole

__all__ = [
    "BaseRole",
    "ManagerRole",
    "SupervisorRole",
    "WorkerRole",
]
