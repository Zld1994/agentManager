"""Tests for agent configuration domain models."""

import pytest

from agentManager.domain.agent_config import (
    AgentLayer,
    AgentProfile,
    AgentTemplateRef,
    AgentWorkdirPolicy,
)


class TestAgentLayerEnum:
    def test_layer_values(self) -> None:
        assert AgentLayer.HIGH.value == "high"
        assert AgentLayer.LOW.value == "low"

    def test_layer_from_string(self) -> None:
        assert AgentLayer("high") == AgentLayer.HIGH
        assert AgentLayer("low") == AgentLayer.LOW


class TestAgentTemplateRef:
    def test_defaults(self) -> None:
        ref = AgentTemplateRef(kind="skill", name="task-planning")
        assert ref.version == "1.0"
        assert ref.required is True

    def test_round_trip(self) -> None:
        ref = AgentTemplateRef(kind="mcp", name="filesystem", version="2.0", required=False)
        data = ref.to_dict()
        restored = AgentTemplateRef.from_dict(data)
        assert restored.kind == ref.kind
        assert restored.name == ref.name
        assert restored.version == ref.version
        assert restored.required == ref.required

    def test_requires_kind(self) -> None:
        with pytest.raises(ValueError, match="kind"):
            AgentTemplateRef(kind="", name="test")

    def test_requires_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            AgentTemplateRef(kind="skill", name="")

    def test_rejects_invalid_kind(self) -> None:
        with pytest.raises(ValueError, match="kind must be"):
            AgentTemplateRef(kind="tool", name="test")

    def test_skill_order_preserved(self) -> None:
        refs = [
            AgentTemplateRef(kind="skill", name="a"),
            AgentTemplateRef(kind="skill", name="b"),
            AgentTemplateRef(kind="skill", name="c"),
        ]
        assert [r.name for r in refs] == ["a", "b", "c"]


class TestAgentWorkdirPolicy:
    def test_defaults(self) -> None:
        policy = AgentWorkdirPolicy(root="workspace")
        assert policy.mode == "isolated"
        assert policy.create_if_missing is True

    def test_round_trip(self) -> None:
        policy = AgentWorkdirPolicy(root="data", mode="shared", create_if_missing=False)
        data = policy.to_dict()
        restored = AgentWorkdirPolicy.from_dict(data)
        assert restored.root == policy.root
        assert restored.mode == policy.mode
        assert restored.create_if_missing == policy.create_if_missing

    def test_requires_root(self) -> None:
        with pytest.raises(ValueError, match="root"):
            AgentWorkdirPolicy(root="")

    def test_rejects_invalid_mode(self) -> None:
        with pytest.raises(ValueError, match="mode must be"):
            AgentWorkdirPolicy(root="/workspace", mode="invalid")

    def test_rejects_dotdot_in_unix_path(self) -> None:
        with pytest.raises(ValueError, match="must not contain"):
            AgentWorkdirPolicy(root="workspace/../escape")

    def test_rejects_tilde_path(self) -> None:
        with pytest.raises(ValueError, match="must not start"):
            AgentWorkdirPolicy(root="~/workspace")

    def test_rejects_absolute_posix_path(self) -> None:
        with pytest.raises(ValueError, match="must be relative"):
            AgentWorkdirPolicy(root="/etc")

    def test_rejects_absolute_windows_path(self) -> None:
        with pytest.raises(ValueError, match="must be relative"):
            AgentWorkdirPolicy(root="C:/Windows")

    def test_valid_modes(self) -> None:
        for mode in ("isolated", "shared", "temporary"):
            policy = AgentWorkdirPolicy(root="workspace", mode=mode)
            assert policy.mode == mode


class TestAgentProfile:
    def test_minimal(self) -> None:
        profile = AgentProfile(agent_id="w1", name="Worker", role="worker")
        assert profile.layer == AgentLayer.LOW
        assert profile.capabilities == []
        assert profile.skills == []
        assert profile.mcp_servers == []
        assert profile.prompt == ""
        assert profile.workdir is None
        assert profile.metadata == {}

    def test_requires_agent_id(self) -> None:
        with pytest.raises(ValueError, match="agent_id"):
            AgentProfile(agent_id="", name="Test", role="worker")

    def test_requires_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            AgentProfile(agent_id="w1", name="", role="worker")

    def test_requires_role(self) -> None:
        with pytest.raises(ValueError, match="role"):
            AgentProfile(agent_id="w1", name="Test", role="")

    def test_coerces_layer_from_string(self) -> None:
        profile = AgentProfile(agent_id="m1", name="Manager", role="manager", layer="high")
        assert profile.layer == AgentLayer.HIGH

    def test_coerces_nested_template_refs(self) -> None:
        profile = AgentProfile(
            agent_id="w1",
            name="Worker",
            role="worker",
            skills=[{"kind": "skill", "name": "exec"}],
            mcp_servers=[{"kind": "mcp", "name": "fs"}],
        )
        assert isinstance(profile.skills[0], AgentTemplateRef)
        assert profile.skills[0].name == "exec"
        assert isinstance(profile.mcp_servers[0], AgentTemplateRef)
        assert profile.mcp_servers[0].name == "fs"

    def test_coerces_workdir_from_dict(self) -> None:
        profile = AgentProfile(
            agent_id="w1",
            name="Worker",
            role="worker",
            workdir={"root": "workspace", "mode": "isolated"},
        )
        assert isinstance(profile.workdir, AgentWorkdirPolicy)
        assert profile.workdir.root == "workspace"

    def test_round_trip(self) -> None:
        profile = AgentProfile(
            agent_id="m1",
            name="Manager",
            role="manager",
            layer=AgentLayer.HIGH,
            description="Task decomposer",
            capabilities=["decompose_task", "delegate_task"],
            skills=[AgentTemplateRef(kind="skill", name="planning")],
            mcp_servers=[],
            prompt="You are a manager.",
            workdir=AgentWorkdirPolicy(root="workspace"),
            metadata={"default": True},
        )
        data = profile.to_dict()
        restored = AgentProfile.from_dict(data)
        assert restored.agent_id == profile.agent_id
        assert restored.layer == profile.layer
        assert restored.capabilities == profile.capabilities
        assert len(restored.skills) == 1
        assert restored.skills[0].name == "planning"

    def test_high_layer_example(self) -> None:
        profile = AgentProfile(
            agent_id="manager",
            name="Manager Agent",
            role="manager",
            layer=AgentLayer.HIGH,
            capabilities=["decompose_task", "delegate_task", "plan_work"],
        )
        assert profile.layer == AgentLayer.HIGH
        assert "decompose_task" in profile.capabilities

    def test_low_layer_example(self) -> None:
        profile = AgentProfile(
            agent_id="worker",
            name="Worker Agent",
            role="worker",
            layer=AgentLayer.LOW,
            capabilities=["execute_task"],
        )
        assert profile.layer == AgentLayer.LOW
        assert "execute_task" in profile.capabilities
