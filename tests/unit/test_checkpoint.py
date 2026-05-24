"""Tests for checkpoint security features.

Tests for safe_extract() function and path traversal protection.
"""

import pytest
import tarfile
import tempfile
import json
from pathlib import Path

from agentManager.engine.checkpoint import safe_extract, load_checkpoint_with_recovery


class TestSafeExtract:
    """Test suite for safe_extract function."""

    def test_safe_extract_normal_paths(self):
        """Test extraction of normal paths within target directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a tar file with normal paths
            tar_path = Path(tmpdir) / 'test.tar.gz'
            extract_dir = Path(tmpdir) / 'extract'
            extract_dir.mkdir()

            with tarfile.open(tar_path, 'w:gz') as tar:
                # Add a normal file
                info = tarfile.TarInfo(name='normal_file.txt')
                info.size = 5
                tar.addfile(info, fileobj=None)

            # Should not raise
            with tarfile.open(tar_path, 'r:gz') as tar:
                safe_extract(tar, str(extract_dir))

    def test_safe_extract_path_traversal_attack(self):
        """Test that path traversal attempts are blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tar_path = Path(tmpdir) / 'malicious.tar.gz'
            extract_dir = Path(tmpdir) / 'extract'
            extract_dir.mkdir()

            with tarfile.open(tar_path, 'w:gz') as tar:
                # Add a file with path traversal
                info = tarfile.TarInfo(name='../../evil.py')
                info.size = 0
                tar.addfile(info, fileobj=None)

            # Should raise ValueError
            with tarfile.open(tar_path, 'r:gz') as tar:
                with pytest.raises(ValueError, match='Path traversal detected'):
                    safe_extract(tar, str(extract_dir))

    def test_safe_extract_absolute_path_attack(self):
        """Test that absolute paths are blocked."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tar_path = Path(tmpdir) / 'absolute.tar.gz'
            extract_dir = Path(tmpdir) / 'extract'
            extract_dir.mkdir()

            with tarfile.open(tar_path, 'w:gz') as tar:
                # Add a file with absolute path
                info = tarfile.TarInfo(name='/etc/passwd')
                info.size = 0
                tar.addfile(info, fileobj=None)

            # Should raise ValueError
            with tarfile.open(tar_path, 'r:gz') as tar:
                with pytest.raises(ValueError, match='Absolute path detected'):
                    safe_extract(tar, str(extract_dir))

    def test_safe_extract_nested_traversal(self):
        """Test nested directory traversal attempts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tar_path = Path(tmpdir) / 'nested.tar.gz'
            extract_dir = Path(tmpdir) / 'extract'
            extract_dir.mkdir()

            with tarfile.open(tar_path, 'w:gz') as tar:
                # Add a file with nested traversal
                info = tarfile.TarInfo(name='subdir/../../../../etc/passwd')
                info.size = 0
                tar.addfile(info, fileobj=None)

            # Should raise ValueError
            with tarfile.open(tar_path, 'r:gz') as tar:
                with pytest.raises(ValueError, match='Path traversal detected'):
                    safe_extract(tar, str(extract_dir))


@pytest.mark.asyncio
class TestLoadCheckpointWithRecovery:
    """Test suite for load_checkpoint_with_recovery function."""

    async def test_load_checkpoint_not_found(self):
        """Test loading non-existent checkpoint."""
        result = await load_checkpoint_with_recovery(
            '/nonexistent/checkpoint.tar.gz',
            'task_123'
        )
        assert result is None

    async def test_load_checkpoint_with_malicious_paths(self):
        """Test that malicious checkpoints are rejected."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tar_path = Path(tmpdir) / 'malicious.tar.gz'

            with tarfile.open(tar_path, 'w:gz') as tar:
                info = tarfile.TarInfo(name='../../evil.py')
                info.size = 0
                tar.addfile(info, fileobj=None)

            with pytest.raises(ValueError, match='Path traversal detected'):
                await load_checkpoint_with_recovery(str(tar_path), 'task_123')

    async def test_load_checkpoint_valid(self):
        """Test loading valid checkpoint."""
        import io
        with tempfile.TemporaryDirectory() as tmpdir:
            tar_path = Path(tmpdir) / 'valid.tar.gz'
            checkpoint_data = {'state': 'recovered', 'step': 5}

            with tarfile.open(tar_path, 'w:gz') as tar:
                # Add checkpoint.json with proper content
                json_data = json.dumps(checkpoint_data).encode()
                info = tarfile.TarInfo(name='checkpoint.json')
                info.size = len(json_data)
                tar.addfile(info, fileobj=io.BytesIO(json_data))

            result = await load_checkpoint_with_recovery(str(tar_path), 'task_123')
            assert result == checkpoint_data
