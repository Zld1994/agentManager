"""Agent configuration and template management."""

from agentManager.agents.defaults import get_default_agent_profiles
from agentManager.agents.prompt_builder import (
    build_agent_prompt,
    build_manager_prompt,
    build_worker_prompt,
)
from agentManager.agents.registry import AgentRegistry, ResolvedAgent
from agentManager.agents.template_library import (
    TemplateEntry,
    get_merged_templates,
    get_template,
    list_templates,
    load_project_templates,
)

__all__ = [
    "AgentRegistry",
    "ResolvedAgent",
    "TemplateEntry",
    "build_agent_prompt",
    "build_manager_prompt",
    "build_worker_prompt",
    "get_default_agent_profiles",
    "get_merged_templates",
    "get_template",
    "list_templates",
    "load_project_templates",
]
