"""Tests for built-in template library."""

import pytest

from agentManager.agents.template_library import (
    TemplateEntry,
    get_template,
    list_templates,
)


class TestTemplateEntry:
    def test_defaults(self) -> None:
        entry = TemplateEntry(kind="skill", name="test")
        assert entry.description == ""
        assert entry.prompt_snippet == ""
        assert entry.config == {}
        assert entry.tags == []

    def test_round_trip(self) -> None:
        entry = TemplateEntry(
            kind="mcp",
            name="fs",
            description="Filesystem",
            prompt_snippet="Use fs.",
            config={"allowed": [".py"]},
            tags=["io"],
        )
        data = entry.to_dict()
        restored = TemplateEntry.from_dict(data)
        assert restored.kind == entry.kind
        assert restored.name == entry.name
        assert restored.config == entry.config

    def test_requires_kind(self) -> None:
        with pytest.raises(ValueError, match="kind"):
            TemplateEntry(kind="", name="test")

    def test_requires_name(self) -> None:
        with pytest.raises(ValueError, match="name"):
            TemplateEntry(kind="skill", name="")

    def test_rejects_invalid_kind(self) -> None:
        with pytest.raises(ValueError, match="kind must be"):
            TemplateEntry(kind="tool", name="test")


class TestListTemplates:
    def test_list_all(self) -> None:
        templates = list_templates()
        assert len(templates) == 5

    def test_list_skills_only(self) -> None:
        skills = list_templates(kind="skill")
        assert len(skills) == 3
        assert all(s.kind == "skill" for s in skills)

    def test_list_mcp_only(self) -> None:
        mcps = list_templates(kind="mcp")
        assert len(mcps) == 2
        assert all(m.kind == "mcp" for m in mcps)

    def test_list_unknown_kind_returns_empty(self) -> None:
        assert list_templates(kind="unknown") == []


class TestGetTemplate:
    def test_get_existing_skill(self) -> None:
        template = get_template("skill", "task-planning")
        assert template.name == "task-planning"
        assert template.kind == "skill"

    def test_get_existing_mcp(self) -> None:
        template = get_template("mcp", "filesystem")
        assert template.name == "filesystem"

    def test_get_nonexistent_raises_key_error(self) -> None:
        with pytest.raises(KeyError, match="Template not found"):
            get_template("skill", "nonexistent")

    def test_get_wrong_kind_raises(self) -> None:
        with pytest.raises(KeyError):
            get_template("mcp", "task-planning")

    def test_builtin_skill_names(self) -> None:
        skill_names = [t.name for t in list_templates(kind="skill")]
        assert "task-planning" in skill_names
        assert "code-review" in skill_names
        assert "sandbox-execution" in skill_names

    def test_builtin_mcp_names(self) -> None:
        mcp_names = [t.name for t in list_templates(kind="mcp")]
        assert "filesystem" in mcp_names
        assert "event-bus" in mcp_names
