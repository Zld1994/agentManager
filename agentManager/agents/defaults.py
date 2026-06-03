"""Default agent profiles for built-in roles."""

from __future__ import annotations

from agentManager.domain.agent_config import (
    AgentLayer,
    AgentProfile,
    AgentTemplateRef,
)


def get_default_agent_profiles() -> dict[str, AgentProfile]:
    """Return default agent profiles for manager, supervisor, and worker.

    Returns:
        Dict mapping ``agent_id`` to ``AgentProfile``.
    """
    manager = AgentProfile(
        agent_id="manager",
        name="Manager Agent",
        role="manager",
        layer=AgentLayer.HIGH,
        description="Decomposes tasks and delegates work to supervisors and workers.",
        capabilities=["decompose_task", "delegate_task", "plan_work"],
        skills=[
            AgentTemplateRef(kind="skill", name="task-planning"),
        ],
        prompt=(
            "You are a manager agent responsible for decomposing complex tasks "
            "into actionable subtasks and delegating them to supervisors and workers."
        ),
        metadata={"default": True},
    )

    supervisor = AgentProfile(
        agent_id="supervisor",
        name="Supervisor Agent",
        role="supervisor",
        layer=AgentLayer.HIGH,
        description="Monitors task execution health and recommends recovery actions.",
        capabilities=["monitor_task", "recover_task", "escalate_failure"],
        prompt=(
            "You are a supervisor agent responsible for monitoring task execution "
            "and recommending recovery actions when failures occur."
        ),
        metadata={"default": True},
    )

    worker = AgentProfile(
        agent_id="worker",
        name="Worker Agent",
        role="worker",
        layer=AgentLayer.LOW,
        description="Executes assigned tasks in isolated workspaces.",
        capabilities=["execute_task"],
        skills=[
            AgentTemplateRef(kind="skill", name="sandbox-execution"),
        ],
        mcp_servers=[
            AgentTemplateRef(kind="mcp", name="filesystem", required=False),
        ],
        prompt=(
            "You are a worker agent responsible for executing tasks. "
            "Accept only confirmed tasks and execute them in an isolated environment."
        ),
        metadata={"default": True, "accepts_confirmed_only": True},
    )

    return {
        "manager": manager,
        "supervisor": supervisor,
        "worker": worker,
    }
