"""Checkpoint management with security features.

This module implements secure checkpoint loading and saving with path traversal
protection and recovery capabilities.
"""

import logging
import tarfile
import tempfile
from pathlib import Path
from typing import Optional
import sys

logger = logging.getLogger(__name__)


def safe_extract(tar: tarfile.TarFile, path: str) -> None:
    """Safely extract tar archive with path traversal protection.

    Validates that all extracted paths remain within the target directory,
    preventing directory traversal attacks like ../../evil.py.

    Args:
        tar: TarFile object to extract from
        path: Target directory for extraction

    Raises:
        ValueError: If any path in the archive attempts to escape target directory
    """
    target_path = Path(path).resolve()

    # Python 3.12+ has built-in filter parameter
    if sys.version_info >= (3, 12):
        tar.extractall(path=path, filter='data')
        return

    # For older Python versions, manually validate paths
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

    # If all paths are safe, extract
    tar.extractall(path=path)


async def load_checkpoint_with_recovery(
    checkpoint_path: str,
    task_id: str,
) -> Optional[dict]:
    """Load checkpoint with path traversal protection.

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
        with tempfile.TemporaryDirectory() as tmpdir:
            with tarfile.open(checkpoint_file, 'r:gz') as tar:
                # Use safe extraction
                safe_extract(tar, tmpdir)

            # Load checkpoint data from extracted files
            checkpoint_data_path = Path(tmpdir) / 'checkpoint.json'
            if checkpoint_data_path.exists():
                import json
                with open(checkpoint_data_path, 'r') as f:
                    return json.load(f)

            logger.warning(f"No checkpoint data found in {checkpoint_file}")
            return None

    except ValueError as e:
        logger.error(f"Security error loading checkpoint: {e}")
        raise
    except Exception as e:
        logger.error(f"Error loading checkpoint for task {task_id}: {e}")
        raise
