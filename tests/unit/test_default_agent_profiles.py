"""Tests for default agent profiles."""

from agentManager.agents.defaults import get_default_agent_profiles
from agentManager.domain.agent_config import AgentLayer


class TestGetDefaultAgentProfiles:
    def test_returns_three_profiles(self) -> None:
        profiles = get_default_agent_profiles()
        assert len(profiles) == 3
        assert set(profiles.keys()) == {"manager", "supervisor", "worker"}

    def test_manager_properties(self) -> None:
        profiles = get_default_agent_profiles()
        mgr = profiles["manager"]
        assert mgr.agent_id == "manager"
        assert mgr.name == "Manager Agent"
        assert mgr.role == "manager"
        assert mgr.layer == AgentLayer.HIGH
        assert "decompose_task" in mgr.capabilities
        assert "delegate_task" in mgr.capabilities
        assert "plan_work" in mgr.capabilities

    def test_manager_has_task_planning_skill(self) -> None:
        profiles = get_default_agent_profiles()
        mgr = profiles["manager"]
        assert len(mgr.skills) == 1
        assert mgr.skills[0].kind == "skill"
        assert mgr.skills[0].name == "task-planning"

    def test_manager_has_default_metadata(self) -> None:
        profiles = get_default_agent_profiles()
        assert profiles["manager"].metadata.get("default") is True

    def test_supervisor_properties(self) -> None:
        profiles = get_default_agent_profiles()
        sup = profiles["supervisor"]
        assert sup.agent_id == "supervisor"
        assert sup.role == "supervisor"
        assert sup.layer == AgentLayer.HIGH
        assert "monitor_task" in sup.capabilities
        assert "recover_task" in sup.capabilities
        assert "escalate_failure" in sup.capabilities
        assert sup.skills == []

    def test_worker_properties(self) -> None:
        profiles = get_default_agent_profiles()
        wkr = profiles["worker"]
        assert wkr.agent_id == "worker"
        assert wkr.role == "worker"
        assert wkr.layer == AgentLayer.LOW
        assert "execute_task" in wkr.capabilities

    def test_worker_has_sandbox_skill(self) -> None:
        profiles = get_default_agent_profiles()
        wkr = profiles["worker"]
        assert len(wkr.skills) == 1
        assert wkr.skills[0].name == "sandbox-execution"

    def test_worker_has_filesystem_mcp(self) -> None:
        profiles = get_default_agent_profiles()
        wkr = profiles["worker"]
        assert len(wkr.mcp_servers) == 1
        assert wkr.mcp_servers[0].kind == "mcp"
        assert wkr.mcp_servers[0].name == "filesystem"
        assert wkr.mcp_servers[0].required is False

    def test_worker_accepts_confirmed_only(self) -> None:
        profiles = get_default_agent_profiles()
        assert profiles["worker"].metadata.get("accepts_confirmed_only") is True

    def test_all_profiles_have_prompts(self) -> None:
        profiles = get_default_agent_profiles()
        for profile in profiles.values():
            assert profile.prompt, f"{profile.agent_id} has empty prompt"
