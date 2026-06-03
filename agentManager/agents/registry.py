"""Agent registry combining profiles and template library."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agentManager.agents.defaults import get_default_agent_profiles
from agentManager.agents.template_library import (
    TemplateEntry,
    get_merged_templates,
)
from agentManager.config.agent_profiles import load_agent_profiles
from agentManager.domain.agent_config import AgentProfile, AgentTemplateRef

logger = logging.getLogger(__name__)


@dataclass
class ResolvedAgent:
    """An agent profile with resolved template references."""

    profile: AgentProfile
    resolved_skills: list[TemplateEntry] = field(default_factory=list)
    resolved_mcp_servers: list[TemplateEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "resolved_skills": [s.to_dict() for s in self.resolved_skills],
            "resolved_mcp_servers": [m.to_dict() for m in self.resolved_mcp_servers],
        }


class AgentRegistry:
    """Registry for agent profiles and template resolution."""

    def __init__(
        self,
        config_dir: Path | None = None,
        include_defaults: bool = True,
    ) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        self._templates: dict[tuple[str, str], TemplateEntry] = {}
        self._config_dir = config_dir

        if include_defaults:
            self._profiles.update(get_default_agent_profiles())

        if config_dir is not None:
            project_profiles = load_agent_profiles(config_dir)
            for agent_id, profile in project_profiles.items():
                if agent_id in self._profiles:
                    logger.warning(
                        "Project profile '%s' overrides default profile with same agent_id",
                        agent_id,
                    )
            self._profiles.update(project_profiles)

        self._templates = get_merged_templates(config_dir)

    @property
    def profiles(self) -> dict[str, AgentProfile]:
        return dict(self._profiles)

    @property
    def templates(self) -> dict[tuple[str, str], TemplateEntry]:
        return dict(self._templates)

    def get_profile(self, agent_id: str) -> AgentProfile | None:
        return self._profiles.get(agent_id)

    def get_template(self, kind: str, name: str) -> TemplateEntry | None:
        return self._templates.get((kind, name))

    def resolve_agent(self, agent_id: str) -> ResolvedAgent | None:
        """Resolve an agent profile with its template references.

        Raises:
            ValueError: If a required template reference cannot be resolved.
        """
        profile = self.get_profile(agent_id)
        if profile is None:
            return None

        resolved_skills = []
        for ref in profile.skills:
            template = self.get_template(ref.kind, ref.name)
            if template is None and ref.required:
                available = [
                    f"{k}/{n}" for k, n in self._templates if k == "skill"
                ]
                raise ValueError(
                    f"Required skill template not found: {ref.kind}/{ref.name} "
                    f"for agent {agent_id}. Available skills: {available}"
                )
            if template is not None:
                resolved_skills.append(template)

        resolved_mcp_servers = []
        for ref in profile.mcp_servers:
            template = self.get_template(ref.kind, ref.name)
            if template is None and ref.required:
                available = [
                    f"{k}/{n}" for k, n in self._templates if k == "mcp"
                ]
                raise ValueError(
                    f"Required MCP template not found: {ref.kind}/{ref.name} "
                    f"for agent {agent_id}. Available MCP: {available}"
                )
            if template is not None:
                resolved_mcp_servers.append(template)

        return ResolvedAgent(
            profile=profile,
            resolved_skills=resolved_skills,
            resolved_mcp_servers=resolved_mcp_servers,
        )

    def register_profile(self, profile: AgentProfile) -> None:
        self._profiles[profile.agent_id] = profile
        logger.info("Registered agent profile: %s", profile.agent_id)

    def register_template(self, template: TemplateEntry) -> None:
        self._templates[(template.kind, template.name)] = template
        logger.info("Registered template: %s/%s", template.kind, template.name)

    def validate_template_refs(
        self, refs: list[AgentTemplateRef]
    ) -> tuple[bool, list[str]]:
        """Validate template references against available templates.

        Returns:
            Tuple of (all_valid, list_of_error_messages).
        """
        errors: list[str] = []
        for ref in refs:
            template = self.get_template(ref.kind, ref.name)
            if template is None and ref.required:
                errors.append(f"Required template not found: {ref.kind}/{ref.name}")
        return len(errors) == 0, errors
