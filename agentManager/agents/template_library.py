"""Built-in skill and MCP template library.

Provides ``TemplateEntry`` and functions to list, get, and merge templates
from built-in definitions and optional project-level overrides.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentManager.config.agent_profiles import _parse_front_matter
from agentManager.domain.models import _model_to_dict, _require_non_empty

logger = logging.getLogger(__name__)


@dataclass
class TemplateEntry:
    """A skill or MCP template entry."""

    kind: str
    name: str
    description: str = ""
    prompt_snippet: str = ""
    config: dict[str, Any] = field(default_factory=dict)
    tags: list[str] = field(default_factory=list)

    def __post_init__(self) -> None:
        _require_non_empty(self.kind, "kind")
        _require_non_empty(self.name, "name")
        if self.kind not in {"skill", "mcp"}:
            raise ValueError(f"kind must be 'skill' or 'mcp', got {self.kind!r}")

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TemplateEntry:
        return cls(**data)


_BUILTIN_TEMPLATES: list[TemplateEntry] = [
    TemplateEntry(
        kind="skill",
        name="task-planning",
        description="Decompose complex tasks into subtasks with dependencies.",
        prompt_snippet=(
            "Analyze the task and break it into smaller subtasks. "
            "For each subtask, specify: id, description, dependencies, and expected output."
        ),
        config={"max_subtasks": 10, "require_dependencies": True},
        tags=["planning", "decomposition"],
    ),
    TemplateEntry(
        kind="skill",
        name="code-review",
        description="Review code for quality, security, and best practices.",
        prompt_snippet=(
            "Review the provided code for: syntax errors, security vulnerabilities, "
            "performance issues, and adherence to best practices."
        ),
        config={"check_security": True, "check_performance": True},
        tags=["review", "quality"],
    ),
    TemplateEntry(
        kind="skill",
        name="sandbox-execution",
        description="Execute code in an isolated sandbox environment.",
        prompt_snippet=(
            "Execute the provided code in a sandboxed environment with restricted "
            "network access and resource limits."
        ),
        config={"timeout_seconds": 60, "memory_limit": "512m"},
        tags=["execution", "sandbox"],
    ),
    TemplateEntry(
        kind="mcp",
        name="filesystem",
        description="Read and write files in the agent's working directory.",
        prompt_snippet="Use the filesystem MCP to read and write files safely.",
        config={"allowed_extensions": [".py", ".md", ".json", ".txt"]},
        tags=["io", "files"],
    ),
    TemplateEntry(
        kind="mcp",
        name="event-bus",
        description="Publish and subscribe to workflow events.",
        prompt_snippet="Use the event bus MCP to coordinate with other agents.",
        config={"supported_events": ["task_created", "task_completed", "task_failed"]},
        tags=["events", "coordination"],
    ),
]


def list_templates(kind: str | None = None) -> list[TemplateEntry]:
    """List available templates, optionally filtered by kind.

    Args:
        kind: Optional filter (``"skill"`` or ``"mcp"``).

    Returns:
        List of ``TemplateEntry`` instances.
    """
    if kind is None:
        return list(_BUILTIN_TEMPLATES)
    return [t for t in _BUILTIN_TEMPLATES if t.kind == kind]


def get_template(kind: str, name: str) -> TemplateEntry:
    """Get a specific template by kind and name.

    Args:
        kind: Template kind (``"skill"`` or ``"mcp"``).
        name: Template name.

    Returns:
        ``TemplateEntry`` instance.

    Raises:
        KeyError: If no matching template exists.
    """
    for template in _BUILTIN_TEMPLATES:
        if template.kind == kind and template.name == name:
            return template
    available = [(t.kind, t.name) for t in _BUILTIN_TEMPLATES]
    raise KeyError(
        f"Template not found: kind={kind!r}, name={name!r}. "
        f"Available: {available}"
    )


# ---------------------------------------------------------------------------
# Project-level template overrides (OPT-2.2)
# ---------------------------------------------------------------------------


def _load_project_templates_from_dir(
    templates_dir: Path, kind: str
) -> dict[str, TemplateEntry]:
    """Load project templates from a single directory.

    Args:
        templates_dir: Directory containing ``.md`` template files.
        kind: Template kind (``"skill"`` or ``"mcp"``).

    Returns:
        Dict mapping template name to ``TemplateEntry``.
    """
    if not templates_dir.exists():
        return {}

    templates: dict[str, TemplateEntry] = {}
    for md_file in sorted(templates_dir.glob("*.md")):
        try:
            content = md_file.read_text(encoding="utf-8")
            front_matter, body = _parse_front_matter(content)

            name = front_matter.get("name", md_file.stem)

            if "prompt_snippet" not in front_matter and body:
                front_matter["prompt_snippet"] = body

            front_matter["kind"] = kind
            front_matter["name"] = name

            template = TemplateEntry.from_dict(front_matter)
            templates[template.name] = template
        except Exception as exc:
            logger.warning("Failed to load project template %s: %s", md_file, exc)

    return templates


def load_project_templates(config_dir: Path) -> dict[tuple[str, str], TemplateEntry]:
    """Load all project templates from a config directory.

    Expected structure::

        config_dir/
            templates/
                skills/*.md
                mcp/*.md

    Args:
        config_dir: Root config directory.

    Returns:
        Dict mapping ``(kind, name)`` to ``TemplateEntry``.
    """
    templates_dir = config_dir / "templates"
    skills = _load_project_templates_from_dir(templates_dir / "skills", "skill")
    mcps = _load_project_templates_from_dir(templates_dir / "mcp", "mcp")

    combined: dict[tuple[str, str], TemplateEntry] = {}
    for name, template in skills.items():
        combined[(template.kind, name)] = template
    for name, template in mcps.items():
        combined[(template.kind, name)] = template
    return combined


def get_merged_templates(
    config_dir: Path | None = None,
) -> dict[tuple[str, str], TemplateEntry]:
    """Get merged built-in and project templates.

    Project templates override built-in templates with the same ``(kind, name)``.

    Args:
        config_dir: Optional config directory for project templates.

    Returns:
        Dict mapping ``(kind, name)`` to ``TemplateEntry``.
    """
    merged: dict[tuple[str, str], TemplateEntry] = {}
    for template in _BUILTIN_TEMPLATES:
        merged[(template.kind, template.name)] = template

    if config_dir is not None:
        project_templates = load_project_templates(config_dir)
        merged.update(project_templates)

    return merged
