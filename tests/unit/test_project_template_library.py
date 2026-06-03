"""Tests for project-level template overrides."""

from agentManager.agents.template_library import (
    get_merged_templates,
    load_project_templates,
    list_templates,
)


class TestLoadProjectTemplatesFromDir:
    def test_empty_directory(self, tmp_path) -> None:
        config_dir = tmp_path
        result = load_project_templates(config_dir)
        assert result == {}

    def test_load_single_skill_template(self, tmp_path) -> None:
        skills_dir = tmp_path / "templates" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "custom.md").write_text(
            '---\n{"description": "Custom skill"}\n---\nDo custom work.',
            encoding="utf-8",
        )
        result = load_project_templates(tmp_path)
        assert ("skill", "custom") in result
        assert result[("skill", "custom")].prompt_snippet == "Do custom work."

    def test_load_single_mcp_template(self, tmp_path) -> None:
        mcp_dir = tmp_path / "templates" / "mcp"
        mcp_dir.mkdir(parents=True)
        (mcp_dir / "custom-connector.md").write_text(
            '---\n{"description": "Custom MCP"}\n---\nConnect to custom service.',
            encoding="utf-8",
        )
        result = load_project_templates(tmp_path)
        assert ("mcp", "custom-connector") in result

    def test_template_uses_filename_as_name(self, tmp_path) -> None:
        skills_dir = tmp_path / "templates" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "my-tool.md").write_text(
            '---\n{"description": "test"}\n---\nbody',
            encoding="utf-8",
        )
        result = load_project_templates(tmp_path)
        assert ("skill", "my-tool") in result

    def test_template_body_becomes_prompt_snippet(self, tmp_path) -> None:
        skills_dir = tmp_path / "templates" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "t.md").write_text(
            '---\n{"description": "d"}\n---\nThis is the snippet.',
            encoding="utf-8",
        )
        result = load_project_templates(tmp_path)
        assert result[("skill", "t")].prompt_snippet == "This is the snippet."

    def test_template_with_explicit_name(self, tmp_path) -> None:
        skills_dir = tmp_path / "templates" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "file.md").write_text(
            '---\n{"name": "override-name", "description": "d"}\n---\nbody',
            encoding="utf-8",
        )
        result = load_project_templates(tmp_path)
        assert ("skill", "override-name") in result
        assert ("skill", "file") not in result


class TestGetMergedTemplates:
    def test_builtin_only_when_no_config_dir(self) -> None:
        merged = get_merged_templates(config_dir=None)
        assert len(merged) == 5
        assert ("skill", "task-planning") in merged

    def test_project_templates_override_builtin(self, tmp_path) -> None:
        skills_dir = tmp_path / "templates" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "task-planning.md").write_text(
            '---\n{"description": "Overridden planning"}\n---\nNew planning.',
            encoding="utf-8",
        )
        merged = get_merged_templates(config_dir=tmp_path)
        assert merged[("skill", "task-planning")].description == "Overridden planning"

    def test_project_templates_add_to_builtin(self, tmp_path) -> None:
        skills_dir = tmp_path / "templates" / "skills"
        skills_dir.mkdir(parents=True)
        (skills_dir / "new-skill.md").write_text(
            '---\n{"description": "Brand new"}\n---\nDo new stuff.',
            encoding="utf-8",
        )
        merged = get_merged_templates(config_dir=tmp_path)
        assert len(merged) == 6
        assert ("skill", "new-skill") in merged
        assert ("skill", "task-planning") in merged

    def test_merge_preserves_builtin_when_no_conflict(self, tmp_path) -> None:
        merged = get_merged_templates(config_dir=tmp_path)
        builtin = list_templates()
        for t in builtin:
            assert (t.kind, t.name) in merged
