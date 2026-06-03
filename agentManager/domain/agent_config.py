"""Agent configuration domain models.

Provides dataclasses for agent profiles, template references,
work directory policies, and layer-based capability management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from agentManager.domain.models import (
    _coerce_enum,
    _model_to_dict,
    _require_non_empty,
)


class AgentLayer(str, Enum):
    """Agent execution layer (high-level orchestration vs low-level execution)."""

    HIGH = "high"
    LOW = "low"


@dataclass
class AgentTemplateRef:
    """Reference to a skill or MCP template."""

    kind: str
    name: str
    version: str = "1.0"
    required: bool = True

    def __post_init__(self) -> None:
        _require_non_empty(self.kind, "kind")
        _require_non_empty(self.name, "name")
        if self.kind not in {"skill", "mcp"}:
            raise ValueError(f"kind must be 'skill' or 'mcp', got {self.kind!r}")

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentTemplateRef:
        return cls(**data)


@dataclass
class AgentWorkdirPolicy:
    """Working directory policy for an agent."""

    root: str
    mode: str = "isolated"
    create_if_missing: bool = True

    _VALID_MODES = ("isolated", "shared", "temporary")

    def __post_init__(self) -> None:
        _require_non_empty(self.root, "root")
        if self.mode not in self._VALID_MODES:
            raise ValueError(f"mode must be one of {self._VALID_MODES}, got {self.mode!r}")
        posix_path = PurePosixPath(self.root)
        windows_path = PureWindowsPath(self.root)
        if posix_path.is_absolute() or windows_path.is_absolute() or windows_path.drive:
            raise ValueError(f"root path must be relative: {self.root!r}")
        # Check for path traversal using both POSIX and Windows path parsing
        # to handle mixed separators and edge cases
        if ".." in posix_path.parts or ".." in windows_path.parts:
            raise ValueError(f"root path must not contain '..': {self.root!r}")
        if self.root.startswith("~"):
            raise ValueError(f"root path must not start with '~': {self.root!r}")

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentWorkdirPolicy:
        return cls(**data)


@dataclass
class AgentProfile:
    """Agent configuration profile with layer-based capabilities."""

    agent_id: str
    name: str
    role: str
    layer: AgentLayer | str = AgentLayer.LOW
    description: str = ""
    capabilities: list[str] = field(default_factory=list)
    skills: list[AgentTemplateRef] = field(default_factory=list)
    mcp_servers: list[AgentTemplateRef] = field(default_factory=list)
    prompt: str = ""
    workdir: AgentWorkdirPolicy | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        _require_non_empty(self.agent_id, "agent_id")
        _require_non_empty(self.name, "name")
        _require_non_empty(self.role, "role")
        self.layer = _coerce_enum(self.layer, AgentLayer, "layer")
        self.skills = [
            AgentTemplateRef.from_dict(s) if isinstance(s, dict) else s for s in self.skills
        ]
        self.mcp_servers = [
            AgentTemplateRef.from_dict(m) if isinstance(m, dict) else m for m in self.mcp_servers
        ]
        if isinstance(self.workdir, dict):
            self.workdir = AgentWorkdirPolicy.from_dict(self.workdir)

    def to_dict(self) -> dict[str, Any]:
        return _model_to_dict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentProfile:
        return cls(**data)
