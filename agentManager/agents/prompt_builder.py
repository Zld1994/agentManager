"""Runtime prompt builder for agents.

Assembles agent prompts from profile data, resolved templates,
optional project map summaries, and task JSON schema snippets.
"""

from __future__ import annotations

import json
from typing import Any

from agentManager.agents.template_library import TemplateEntry
from agentManager.domain.agent_config import AgentLayer, AgentProfile


def _format_template(template: TemplateEntry) -> str:
    """Format a template entry for inclusion in a prompt."""
    lines = [f"## {template.kind.upper()}: {template.name}"]
    if template.description:
        lines.append(template.description)
    if template.prompt_snippet:
        lines.append("")
        lines.append(template.prompt_snippet)
    if template.config:
        lines.append("")
        lines.append(f"Configuration: {json.dumps(template.config, indent=2)}")
    return "\n".join(lines)


def _format_project_map(project_map: dict[str, Any]) -> str:
    """Format a project map for inclusion in a prompt."""
    lines = ["## Project Context"]

    if "name" in project_map:
        lines.append(f"Project: {project_map['name']}")
    if "description" in project_map:
        lines.append(project_map["description"])

    if "modules" in project_map:
        lines.append("")
        lines.append("### Modules")
        for module in project_map["modules"][:10]:
            if isinstance(module, dict):
                name = module.get("name", "unknown")
                desc = module.get("description", "")
                lines.append(f"- **{name}**: {desc}")
            else:
                lines.append(f"- {module}")

    if "entry_points" in project_map:
        lines.append("")
        lines.append("### Entry Points")
        for ep in project_map["entry_points"][:5]:
            lines.append(f"- {ep}")

    return "\n".join(lines)


def _format_task_schema() -> str:
    """Return a JSON schema snippet for task structure."""
    schema = {
        "task": {
            "task_id": "string (required)",
            "workflow_id": "string (required)",
            "task_type": "string (required)",
            "status": "pending | ready | running | completed | failed",
            "dependencies": ["list of task_id strings"],
            "input_data": {"key": "value"},
            "output_data": {"key": "value"},
        }
    }
    return f"## Task JSON Schema\n```json\n{json.dumps(schema, indent=2)}\n```"


def build_agent_prompt(
    profile: AgentProfile,
    templates: list[TemplateEntry] | None = None,
    project_map: dict[str, Any] | None = None,
    max_chars: int = 12000,
) -> str:
    """Build a complete agent prompt from profile, templates, and project map.

    Args:
        profile: ``AgentProfile`` instance.
        templates: Optional list of resolved ``TemplateEntry`` instances.
        project_map: Optional project map dictionary.
        max_chars: Maximum prompt length in characters.

    Returns:
        Complete prompt string.
    """
    sections: list[str] = []

    # Agent identity
    layer_val = profile.layer.value if isinstance(profile.layer, AgentLayer) else profile.layer
    identity = [
        f"# {profile.name}",
        f"Role: {profile.role}",
        f"Layer: {layer_val}",
    ]
    if profile.description:
        identity.append(profile.description)
    sections.append("\n".join(identity))

    # Capabilities
    if profile.capabilities:
        caps = ["## Capabilities"] + [f"- {cap}" for cap in profile.capabilities]
        sections.append("\n".join(caps))

    # Base prompt from profile
    if profile.prompt:
        sections.append(f"## Instructions\n{profile.prompt}")

    # Templates
    if templates:
        template_sections = [_format_template(t) for t in templates]
        if template_sections:
            sections.append("\n\n".join(template_sections))

    # Project map (high-layer agents only)
    if project_map and profile.layer == AgentLayer.HIGH:
        sections.append(_format_project_map(project_map))

    # Task schema (high-layer agents only)
    if profile.layer == AgentLayer.HIGH:
        sections.append(_format_task_schema())

    # Join all sections
    prompt = "\n\n".join(sections)

    # Truncate if necessary, respecting paragraph boundaries
    if len(prompt) > max_chars:
        truncation_marker = "\n\n[... prompt truncated ...]"
        cutoff = max_chars - len(truncation_marker)
        # Try to truncate at a paragraph boundary (double newline)
        paragraph_break = prompt.rfind("\n\n", 0, cutoff)
        if paragraph_break > cutoff // 2:
            prompt = prompt[:paragraph_break] + truncation_marker
        else:
            prompt = prompt[:cutoff] + truncation_marker

    return prompt


def build_worker_prompt(
    profile: AgentProfile,
    selected_templates: list[TemplateEntry],
) -> str:
    """Build a prompt for a low-layer worker agent.

    Workers get only selected skills, no project map.
    """
    return build_agent_prompt(
        profile=profile,
        templates=selected_templates,
        project_map=None,
    )


def build_manager_prompt(
    profile: AgentProfile,
    all_templates: list[TemplateEntry],
    project_map: dict[str, Any] | None = None,
) -> str:
    """Build a prompt for a high-layer manager agent.

    Managers get project map summary and task JSON schema.
    """
    return build_agent_prompt(
        profile=profile,
        templates=all_templates,
        project_map=project_map,
    )
