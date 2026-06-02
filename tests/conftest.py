"""Shared pytest fixtures for local and CI test runs."""

import sys
import tempfile
import uuid
from pathlib import Path

import pytest

project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))


@pytest.fixture
def tmp_path(request):
    """Use stable temp paths without relying on pytest's locked base dir."""
    base_path = Path(tempfile.gettempdir()) / "agentmanager-pytest"
    safe_name = "".join(
        character if character.isalnum() or character in ("-", "_") else "_"
        for character in request.node.name
    )
    path = base_path / f"{safe_name}-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=True)
    return path
