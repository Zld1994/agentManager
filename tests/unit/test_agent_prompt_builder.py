"""Tests for runtime prompt builder."""

from agentManager.agents.prompt_builder import (
    _format_project_map,
    _format_template,
    build_agent_prompt,
    build_manager_prompt,
    build_worker_prompt,
)
from agentManager.agents.template_library import TemplateEntry
from agentManager.domain.agent_config import AgentLayer, AgentProfile


def _make_profile(**kwargs) -> AgentProfile:
    defaults = {"agent_id": "test", "name": "Test Agent", "role": "worker"}
    defaults.update(kwargs)
    return AgentProfile(**defaults)


class TestFormatTemplate:
    def test_skill_template(self) -> None:
        t = TemplateEntry(
            kind="skill", name="planning", description="Plan tasks",
            prompt_snippet="Do planning.",
        )
        result = _format_template(t)
        assert "## SKILL: planning" in result
        assert "Plan tasks" in result
        assert "Do planning." in result

    def test_mcp_template(self) -> None:
        t = TemplateEntry(kind="mcp", name="fs", description="Filesystem access")
        result = _format_template(t)
        assert "## MCP: fs" in result

    def test_template_with_config(self) -> None:
        t = TemplateEntry(
            kind="skill", name="exec",
            config={"timeout": 60},
        )
        result = _format_template(t)
        assert "Configuration:" in result
        assert "timeout" in result


class TestFormatProjectMap:
    def test_minimal(self) -> None:
        result = _format_project_map({"name": "myproject"})
        assert "Project: myproject" in result

    def test_with_modules(self) -> None:
        pm = {
            "name": "proj",
            "modules": [
                {"name": "pkg.a", "description": "Module A"},
                {"name": "pkg.b", "description": "Module B"},
            ],
        }
        result = _format_project_map(pm)
        assert "pkg.a" in result
        assert "pkg.b" in result

    def test_limits_modules_to_10(self) -> None:
        pm = {
            "name": "big",
            "modules": [{"name": f"mod_{i}"} for i in range(20)],
        }
        result = _format_project_map(pm)
        assert "mod_0" in result
        assert "mod_9" in result
        assert "mod_10" not in result


class TestBuildAgentPrompt:
    def test_minimal_prompt(self) -> None:
        profile = _make_profile()
        prompt = build_agent_prompt(profile)
        assert "# Test Agent" in prompt
        assert "Role: worker" in prompt

    def test_includes_capabilities(self) -> None:
        profile = _make_profile(capabilities=["execute_task", "verify"])
        prompt = build_agent_prompt(profile)
        assert "execute_task" in prompt
        assert "verify" in prompt

    def test_includes_instructions(self) -> None:
        profile = _make_profile(prompt="Do your job well.")
        prompt = build_agent_prompt(profile)
        assert "Do your job well." in prompt

    def test_includes_templates(self) -> None:
        profile = _make_profile()
        templates = [
            TemplateEntry(kind="skill", name="exec", prompt_snippet="Execute code."),
        ]
        prompt = build_agent_prompt(profile, templates=templates)
        assert "Execute code." in prompt

    def test_high_layer_includes_project_map(self) -> None:
        profile = _make_profile(layer=AgentLayer.HIGH)
        pm = {"name": "myproject", "description": "A cool project"}
        prompt = build_agent_prompt(profile, project_map=pm)
        assert "myproject" in prompt
        assert "A cool project" in prompt

    def test_low_layer_excludes_project_map(self) -> None:
        profile = _make_profile(layer=AgentLayer.LOW)
        pm = {"name": "myproject"}
        prompt = build_agent_prompt(profile, project_map=pm)
        assert "myproject" not in prompt

    def test_high_layer_includes_task_schema(self) -> None:
        profile = _make_profile(layer=AgentLayer.HIGH)
        prompt = build_agent_prompt(profile)
        assert "Task JSON Schema" in prompt

    def test_low_layer_excludes_task_schema(self) -> None:
        profile = _make_profile(layer=AgentLayer.LOW)
        prompt = build_agent_prompt(profile)
        assert "Task JSON Schema" not in prompt

    def test_truncates_at_max_chars(self) -> None:
        profile = _make_profile(prompt="X" * 20000)
        prompt = build_agent_prompt(profile, max_chars=1000)
        assert len(prompt) <= 1000
        assert "truncated" in prompt

    def test_custom_max_chars(self) -> None:
        profile = _make_profile(prompt="Y" * 500)
        prompt = build_agent_prompt(profile, max_chars=200)
        assert len(prompt) <= 200


class TestBuildWorkerPrompt:
    def test_excludes_project_map(self) -> None:
        profile = _make_profile(layer=AgentLayer.LOW)
        templates = [TemplateEntry(kind="skill", name="exec")]
        prompt = build_worker_prompt(profile, templates)
        assert "Project Context" not in prompt

    def test_includes_selected_templates(self) -> None:
        profile = _make_profile(layer=AgentLayer.LOW)
        templates = [TemplateEntry(kind="skill", name="exec", prompt_snippet="Run it.")]
        prompt = build_worker_prompt(profile, templates)
        assert "Run it." in prompt


class TestBuildManagerPrompt:
    def test_includes_project_map(self) -> None:
        profile = _make_profile(
            agent_id="mgr", name="Manager", role="manager", layer=AgentLayer.HIGH
        )
        pm = {"name": "bigproject"}
        prompt = build_manager_prompt(profile, [], project_map=pm)
        assert "bigproject" in prompt

    def test_includes_task_schema(self) -> None:
        profile = _make_profile(
            agent_id="mgr", name="Manager", role="manager", layer=AgentLayer.HIGH
        )
        prompt = build_manager_prompt(profile, [])
        assert "Task JSON Schema" in prompt
