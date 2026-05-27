"""Checkpoint management with security features.

This module implements secure checkpoint loading and saving with path traversal
protection and recovery capabilities.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional
import logging
import tarfile
from pathlib import Path

logger = logging.getLogger(__name__)


class CheckpointManager(ABC):
    """Abstract checkpoint manager with a recovery-friendly surface.

    The runtime layer already consumes a checkpoint manager abstraction with
    save/load/delete methods. This engine-side base keeps the same async
    contract and also exposes the archive recovery helper so callers can depend
    on one consistent surface.
    """

    @abstractmethod
    async def save_checkpoint(self, task_id: str, context: Any) -> None:
        """Persist checkpoint data for a task."""

    @abstractmethod
    async def load_checkpoint(self, task_id: str) -> Optional[Any]:
        """Load checkpoint data for a task."""

    @abstractmethod
    async def delete_checkpoint(self, task_id: str) -> None:
        """Delete checkpoint data for a task."""

    async def load_checkpoint_with_recovery(
        self,
        checkpoint_path: str,
        task_id: str,
    ) -> Optional[dict]:
        """Delegate archive loading to the module-level recovery helper."""
        return await load_checkpoint_with_recovery(checkpoint_path, task_id)


class InMemoryCheckpointManager(CheckpointManager):
    """Lightweight checkpoint manager for tests and local recovery flows."""

    def __init__(self, initial_checkpoints: Optional[Dict[str, Any]] = None):
        self._checkpoints: Dict[str, Any] = dict(initial_checkpoints or {})

    async def save_checkpoint(self, task_id: str, context: Any) -> None:
        self._checkpoints[task_id] = context

    async def load_checkpoint(self, task_id: str) -> Optional[Any]:
        checkpoint = self._checkpoints.get(task_id)
        return checkpoint

    async def delete_checkpoint(self, task_id: str) -> None:
        self._checkpoints.pop(task_id, None)


def safe_extract(tar: tarfile.TarFile, path: str) -> None:
    """Safely validate tar archive paths with traversal protection.

    Validates that all extracted paths remain within the target directory,
    preventing directory traversal attacks like ../../evil.py.

    Args:
        tar: TarFile object to extract from
        path: Target directory for extraction

    Raises:
        ValueError: If any path in the archive attempts to escape target directory
    """
    target_path = Path(path).resolve()

    for member in tar.getmembers():
        # Check for absolute paths first
        if member.name.startswith('/'):
            raise ValueError(
                f"Absolute path detected in archive: {member.name}"
            )

        # Check for path traversal
        if '..' in member.name:
            raise ValueError(
                f"Path traversal detected: {member.name} attempts to escape "
                f"target directory {target_path}"
            )

        member_path = (target_path / member.name).resolve()

        # Check if resolved path is within target directory
        try:
            member_path.relative_to(target_path)
        except ValueError:
            raise ValueError(
                f"Path traversal detected: {member.name} attempts to escape "
                f"target directory {target_path}"
            )

    # Validation is complete; actual checkpoint reads are handled by the
    # recovery loader to avoid unnecessary filesystem writes.


async def load_checkpoint_with_recovery(
    checkpoint_path: str,
    task_id: str,
) -> Optional[dict]:
    """Load checkpoint JSON with path traversal protection.

    Args:
        checkpoint_path: Path to checkpoint tar file
        task_id: Task identifier for logging

    Returns:
        Checkpoint data or None if not found

    Raises:
        ValueError: If checkpoint contains malicious paths
        FileNotFoundError: If checkpoint file not found
    """
    checkpoint_file = Path(checkpoint_path)

    if not checkpoint_file.exists():
        logger.warning(f"Checkpoint not found for task {task_id}")
        return None

    try:
        with tarfile.open(checkpoint_file, 'r:gz') as tar:
            # Use safe validation before reading any member payloads.
            safe_extract(tar, str(checkpoint_file.parent))

            checkpoint_member = next(
                (
                    member
                    for member in tar.getmembers()
                    if member.name == 'checkpoint.json'
                ),
                None,
            )
            if checkpoint_member is None:
                logger.warning(f"No checkpoint data found in {checkpoint_file}")
                return None

            extracted = tar.extractfile(checkpoint_member)
            if extracted is None:
                logger.warning(
                    f"Unable to read checkpoint data from {checkpoint_file}"
                )
                return None

            import json
            with extracted:
                return json.load(extracted)

    except ValueError as e:
        logger.error(f"Security error loading checkpoint: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading checkpoint for task {task_id}: {e}")
        raise
