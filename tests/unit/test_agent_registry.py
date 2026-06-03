"""Tests for agent registry."""

import pytest

from agentManager.agents.registry import AgentRegistry
from agentManager.domain.agent_config import AgentProfile, AgentTemplateRef


class TestAgentRegistry:
    def test_includes_defaults(self) -> None:
        registry = AgentRegistry()
        assert "manager" in registry.profiles
        assert "supervisor" in registry.profiles
        assert "worker" in registry.profiles

    def test_builtin_templates_available(self) -> None:
        registry = AgentRegistry()
        assert registry.get_template("skill", "task-planning") is not None
        assert registry.get_template("mcp", "filesystem") is not None

    def test_no_defaults_when_excluded(self) -> None:
        registry = AgentRegistry(include_defaults=False)
        assert len(registry.profiles) == 0

    def test_loads_project_profiles(self, tmp_path) -> None:
        md = tmp_path / "custom.md"
        md.write_text(
            '---\n{"agent_id": "custom", "name": "Custom", "role": "worker"}\n---\n'
            "Custom prompt.",
            encoding="utf-8",
        )
        registry = AgentRegistry(config_dir=tmp_path)
        assert registry.get_profile("custom") is not None

    def test_project_profile_overrides_default(self, tmp_path) -> None:
        md = tmp_path / "manager.md"
        md.write_text(
            '---\n{"agent_id": "manager", "name": "Override Manager", '
            '"role": "manager", "layer": "high"}\n---\nOverride prompt.',
            encoding="utf-8",
        )
        registry = AgentRegistry(config_dir=tmp_path)
        assert registry.get_profile("manager").name == "Override Manager"

    def test_project_template_overrides_builtin(self, tmp_path) -> None:
        skills_dir = tmp_path / "templates" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "task-planning.md").write_text(
            '---\n{"description": "Custom planning"}\n---\nCustom snippet.',
            encoding="utf-8",
        )
        registry = AgentRegistry(config_dir=tmp_path)
        t = registry.get_template("skill", "task-planning")
        assert t is not None
        assert t.description == "Custom planning"


class TestGetProfile:
    def test_get_existing(self) -> None:
        registry = AgentRegistry()
        assert registry.get_profile("manager") is not None

    def test_get_nonexistent(self) -> None:
        registry = AgentRegistry()
        assert registry.get_profile("nonexistent") is None


class TestResolveAgent:
    def test_resolve_manager_with_skills(self) -> None:
        registry = AgentRegistry()
        resolved = registry.resolve_agent("manager")
        assert resolved is not None
        assert resolved.profile.agent_id == "manager"
        assert len(resolved.resolved_skills) == 1
        assert resolved.resolved_skills[0].name == "task-planning"

    def test_resolve_worker_with_mcp(self) -> None:
        registry = AgentRegistry()
        resolved = registry.resolve_agent("worker")
        assert resolved is not None
        assert len(resolved.resolved_mcp_servers) == 1
        assert resolved.resolved_mcp_servers[0].name == "filesystem"

    def test_resolve_nonexistent_returns_none(self) -> None:
        registry = AgentRegistry()
        assert registry.resolve_agent("nonexistent") is None

    def test_resolve_missing_required_skill_raises(self) -> None:
        registry = AgentRegistry()
        profile = AgentProfile(
            agent_id="broken",
            name="Broken",
            role="worker",
            skills=[AgentTemplateRef(kind="skill", name="nonexistent", required=True)],
        )
        registry.register_profile(profile)
        with pytest.raises(ValueError, match="Required skill template not found"):
            registry.resolve_agent("broken")

    def test_resolve_missing_optional_skill_succeeds(self) -> None:
        registry = AgentRegistry()
        profile = AgentProfile(
            agent_id="flexible",
            name="Flexible",
            role="worker",
            skills=[
                AgentTemplateRef(kind="skill", name="nonexistent", required=False)
            ],
        )
        registry.register_profile(profile)
        resolved = registry.resolve_agent("flexible")
        assert resolved is not None
        assert resolved.resolved_skills == []


class TestRegisterProfile:
    def test_register_new(self) -> None:
        registry = AgentRegistry()
        profile = AgentProfile(agent_id="new", name="New", role="worker")
        registry.register_profile(profile)
        assert registry.get_profile("new") is not None

    def test_register_overwrites(self) -> None:
        registry = AgentRegistry()
        profile = AgentProfile(
            agent_id="manager", name="New Manager", role="manager", layer="high"
        )
        registry.register_profile(profile)
        assert registry.get_profile("manager").name == "New Manager"


class TestValidateTemplateRefs:
    def test_all_present(self) -> None:
        registry = AgentRegistry()
        refs = [AgentTemplateRef(kind="skill", name="task-planning")]
        valid, errors = registry.validate_template_refs(refs)
        assert valid is True
        assert errors == []

    def test_missing_required(self) -> None:
        registry = AgentRegistry()
        refs = [AgentTemplateRef(kind="skill", name="nonexistent", required=True)]
        valid, errors = registry.validate_template_refs(refs)
        assert valid is False
        assert len(errors) == 1

    def test_missing_optional_succeeds(self) -> None:
        registry = AgentRegistry()
        refs = [AgentTemplateRef(kind="skill", name="nonexistent", required=False)]
        valid, errors = registry.validate_template_refs(refs)
        assert valid is True
