"""Tests for agent profile Markdown loader."""

import json

import pytest

from agentManager.config.agent_profiles import (
    _parse_front_matter,
    get_agent_config_dir,
    load_agent_profile,
    load_agent_profiles,
)
from agentManager.domain.agent_config import AgentLayer


class TestParseFrontMatter:
    def test_empty_content(self) -> None:
        meta, body = _parse_front_matter("")
        assert meta == {}
        assert body == ""

    def test_no_front_matter(self) -> None:
        content = "Just a plain prompt with no delimiters."
        meta, body = _parse_front_matter(content)
        assert meta == {}
        assert body == content

    def test_valid_front_matter(self) -> None:
        content = '---\n{"agent_id": "w1", "name": "Worker", "role": "worker"}\n---\nDo work.'
        meta, body = _parse_front_matter(content)
        assert meta["agent_id"] == "w1"
        assert meta["name"] == "Worker"
        assert body == "Do work."

    def test_invalid_json_raises(self) -> None:
        content = "---\n{bad json}\n---\nbody"
        with pytest.raises(ValueError, match="Invalid JSON"):
            _parse_front_matter(content)

    def test_missing_closing_marker(self) -> None:
        content = '---\n{"key": "value"}\nno closing marker'
        meta, body = _parse_front_matter(content)
        assert meta == {}
        assert "key" in body

    def test_body_extraction_multiline(self) -> None:
        content = '---\n{"name": "test"}\n---\nLine 1\nLine 2\nLine 3'
        meta, body = _parse_front_matter(content)
        assert meta["name"] == "test"
        assert "Line 1" in body and "Line 3" in body

    def test_non_object_front_matter_raises(self) -> None:
        content = '---\n[1, 2, 3]\n---\nbody'
        with pytest.raises(ValueError, match="JSON object"):
            _parse_front_matter(content)


class TestLoadAgentProfile:
    def test_load_basic(self, tmp_path) -> None:
        md = tmp_path / "worker.md"
        md.write_text(
            '---\n{"agent_id": "w1", "name": "Worker", "role": "worker"}\n---\n'
            "Execute tasks carefully.",
            encoding="utf-8",
        )
        profile = load_agent_profile(md)
        assert profile.agent_id == "w1"
        assert profile.name == "Worker"
        assert profile.prompt == "Execute tasks carefully."

    def test_filename_as_agent_id(self, tmp_path) -> None:
        md = tmp_path / "my-agent.md"
        md.write_text(
            '---\n{"name": "My Agent", "role": "worker"}\n---\nPrompt.',
            encoding="utf-8",
        )
        profile = load_agent_profile(md)
        assert profile.agent_id == "my-agent"

    def test_body_becomes_prompt(self, tmp_path) -> None:
        md = tmp_path / "agent.md"
        md.write_text(
            '---\n{"agent_id": "a1", "name": "A", "role": "worker"}\n---\n'
            "This is the prompt.",
            encoding="utf-8",
        )
        profile = load_agent_profile(md)
        assert profile.prompt == "This is the prompt."

    def test_file_not_found(self, tmp_path) -> None:
        with pytest.raises(FileNotFoundError):
            load_agent_profile(tmp_path / "nonexistent.md")

    def test_with_all_fields(self, tmp_path) -> None:
        data = {
            "agent_id": "mgr",
            "name": "Manager",
            "role": "manager",
            "layer": "high",
            "description": "Task decomposer",
            "capabilities": ["decompose_task"],
            "skills": [{"kind": "skill", "name": "planning"}],
        }
        md = tmp_path / "manager.md"
        md.write_text(f"---\n{json.dumps(data)}\n---\nManage tasks.", encoding="utf-8")
        profile = load_agent_profile(md)
        assert profile.layer == AgentLayer.HIGH
        assert len(profile.skills) == 1
        assert profile.prompt == "Manage tasks."

    def test_no_front_matter_requires_minimal_fields(self, tmp_path) -> None:
        md = tmp_path / "simple.md"
        md.write_text("Just a simple prompt.", encoding="utf-8")
        with pytest.raises(TypeError, match="name"):
            load_agent_profile(md)


class TestLoadAgentProfiles:
    def test_load_multiple(self, tmp_path) -> None:
        for name, role in [("alpha", "worker"), ("beta", "manager")]:
            md = tmp_path / f"{name}.md"
            md.write_text(
                f'---\n{{"agent_id": "{name}", "name": "{name}", '
                f'"role": "{role}"}}\n---\nPrompt for {name}.',
                encoding="utf-8",
            )
        profiles = load_agent_profiles(tmp_path)
        assert len(profiles) == 2
        assert "alpha" in profiles
        assert "beta" in profiles

    def test_duplicate_agent_id_raises(self, tmp_path) -> None:
        for filename in ("a.md", "b.md"):
            md = tmp_path / filename
            md.write_text(
                '---\n{"agent_id": "dup", "name": "Dup", "role": "worker"}\n---\n',
                encoding="utf-8",
            )
        with pytest.raises(ValueError, match="Duplicate"):
            load_agent_profiles(tmp_path)

    def test_empty_directory(self, tmp_path) -> None:
        profiles = load_agent_profiles(tmp_path)
        assert profiles == {}

    def test_nonexistent_directory(self, tmp_path) -> None:
        profiles = load_agent_profiles(tmp_path / "nope")
        assert profiles == {}


class TestGetAgentConfigDir:
    def test_from_env(self, monkeypatch) -> None:
        monkeypatch.setenv("AGENTMANAGER_AGENT_CONFIG_DIR", "/tmp/agents")
        result = get_agent_config_dir()
        assert result is not None
        from pathlib import Path
        assert result == Path("/tmp/agents")

    def test_not_set(self, monkeypatch) -> None:
        monkeypatch.delenv("AGENTMANAGER_AGENT_CONFIG_DIR", raising=False)
        assert get_agent_config_dir() is None
