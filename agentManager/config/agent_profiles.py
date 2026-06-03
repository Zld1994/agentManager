"""Agent profile loader for Markdown files with JSON front matter.

Supports loading agent profiles from ``.md`` files where the head of the file
contains a JSON front matter block delimited by ``---`` lines, and the body
serves as the runtime prompt.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

from agentManager.domain.agent_config import AgentProfile

logger = logging.getLogger(__name__)

AGENT_CONFIG_DIR_ENV = "AGENTMANAGER_AGENT_CONFIG_DIR"


def _parse_front_matter(content: str) -> tuple[dict[str, Any], str]:
    """Parse JSON front matter from Markdown content.

    Expected format::

        ---
        {"key": "value"}
        ---
        Body text becomes the prompt.

    Returns:
        Tuple of (metadata dict, body string).
    """
    lines = content.split("\n")
    if not lines or lines[0].strip() != "---":
        return {}, content

    end_index = None
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_index = i
            break

    if end_index is None:
        return {}, content

    json_str = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1:]).strip()

    try:
        front_matter = json.loads(json_str)
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in front matter: {exc}") from exc

    if not isinstance(front_matter, dict):
        raise ValueError("Front matter must be a JSON object")

    return front_matter, body


def load_agent_profile(path: Path) -> AgentProfile:
    """Load a single agent profile from a Markdown file.

    Args:
        path: Path to the ``.md`` file.

    Returns:
        AgentProfile instance.

    Raises:
        FileNotFoundError: If *path* does not exist.
        ValueError: If front matter JSON is invalid or missing required fields.
    """
    if not path.exists():
        raise FileNotFoundError(f"Agent profile not found: {path}")

    content = path.read_text(encoding="utf-8")
    front_matter, body = _parse_front_matter(content)

    if "prompt" not in front_matter and body:
        front_matter["prompt"] = body

    if "agent_id" not in front_matter:
        front_matter["agent_id"] = path.stem

    return AgentProfile.from_dict(front_matter)


def load_agent_profiles(config_dir: Path) -> dict[str, AgentProfile]:
    """Load all agent profiles from a directory of ``.md`` files.

    Files are loaded in sorted filename order.  Duplicate ``agent_id`` values
    raise ``ValueError``.

    Args:
        config_dir: Directory containing ``.md`` agent profile files.

    Returns:
        Dict mapping ``agent_id`` to ``AgentProfile``.
    """
    if not config_dir.exists():
        logger.warning("Agent config directory does not exist: %s", config_dir)
        return {}

    profiles: dict[str, AgentProfile] = {}
    for md_file in sorted(config_dir.glob("*.md")):
        profile = load_agent_profile(md_file)
        if profile.agent_id in profiles:
            raise ValueError(
                f"Duplicate agent_id '{profile.agent_id}' in {md_file} "
                f"(already loaded from another file)"
            )
        profiles[profile.agent_id] = profile
        logger.info("Loaded agent profile: %s from %s", profile.agent_id, md_file)

    return profiles


def get_agent_config_dir() -> Path | None:
    """Get agent config directory from environment variable.

    Returns:
        Path to config directory, or ``None`` if not set.
    """
    config_dir_str = os.getenv(AGENT_CONFIG_DIR_ENV)
    if not config_dir_str:
        return None
    return Path(config_dir_str)
