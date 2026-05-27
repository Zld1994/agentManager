"""Tests for BaseRole interface."""

from typing import Any, Dict

import pytest

from agentManager.roles import BaseRole


class ConcreteRole(BaseRole):
    """Concrete role for testing the abstract base class."""

    def execute(self, task: Dict[str, Any]) -> Dict[str, Any]:
        return {"task": task, "status": "ok"}


def test_base_role_cannot_be_instantiated() -> None:
    with pytest.raises(TypeError):
        BaseRole(name="base", description="abstract")


def test_concrete_role_interface() -> None:
    role = ConcreteRole(
        name="tester",
        description="Test role",
        capabilities=["execute_task"],
    )

    assert role.name == "tester"
    assert role.description == "Test role"
    assert role.can_handle("execute_task") is True
    assert role.can_handle("recover_task") is False
    assert role.execute({"id": "task-1"})["status"] == "ok"
