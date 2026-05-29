"""Tests for checkpoint security features.

Tests for safe_extract() function and path traversal protection.
"""

import importlib.util
import asyncio
import json
import tarfile
import uuid
from pathlib import Path

import pytest

CHECKPOINT_MODULE_PATH = (
    Path(__file__).resolve().parents[2]
    / "agentManager"
    / "engine"
    / "checkpoint.py"
)
CHECKPOINT_MODULE_SPEC = importlib.util.spec_from_file_location(
    "checkpoint_under_test",
    CHECKPOINT_MODULE_PATH,
)
assert CHECKPOINT_MODULE_SPEC is not None
checkpoint_module = importlib.util.module_from_spec(CHECKPOINT_MODULE_SPEC)
assert CHECKPOINT_MODULE_SPEC.loader is not None
CHECKPOINT_MODULE_SPEC.loader.exec_module(checkpoint_module)

CheckpointManager = checkpoint_module.CheckpointManager
InMemoryCheckpointManager = checkpoint_module.InMemoryCheckpointManager
ObjectStoreCheckpointManager = checkpoint_module.ObjectStoreCheckpointManager
load_checkpoint_with_recovery = checkpoint_module.load_checkpoint_with_recovery
safe_extract = checkpoint_module.safe_extract
LOCAL_TMP_ROOT = Path(__file__).resolve().parents[2] / "test_tmp" / "checkpoint"
LOCAL_TMP_ROOT.mkdir(parents=True, exist_ok=True)


class RecordingObjectStore:
    """Small object-store fake for checkpoint manager tests."""

    def __init__(self):
        self.objects = {}

    def put_bytes(self, key, data, content_type="application/octet-stream"):
        self.objects[key] = (data, content_type)

    def get_bytes(self, key):
        item = self.objects.get(key)
        if item is None:
            return None
        return item[0]

    def delete(self, key):
        self.objects.pop(key, None)


def _new_test_dir(prefix: str) -> Path:
    path = LOCAL_TMP_ROOT / f"{prefix}-{uuid.uuid4().hex}"
    path.mkdir(parents=True, exist_ok=False)
    return path


class TestSafeExtract:
    """Test suite for safe_extract function."""

    def test_safe_extract_normal_paths(self):
        """Test extraction of normal paths within target directory."""
        tmpdir = _new_test_dir("safe-normal")
        # Create a tar file with normal paths
        tar_path = tmpdir / 'test.tar.gz'
        extract_dir = tmpdir / 'extract'
        extract_dir.mkdir()

        with tarfile.open(tar_path, 'w:gz') as tar:
            # Add a normal file
            import io
            info = tarfile.TarInfo(name='normal_file.txt')
            info.size = 5
            tar.addfile(info, fileobj=io.BytesIO(b'hello'))

        # Should not raise
        with tarfile.open(tar_path, 'r:gz') as tar:
            safe_extract(tar, str(extract_dir))

    def test_safe_extract_path_traversal_attack(self):
        """Test that path traversal attempts are blocked."""
        tmpdir = _new_test_dir("safe-traversal")
        tar_path = tmpdir / 'malicious.tar.gz'
        extract_dir = tmpdir / 'extract'
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
        tmpdir = _new_test_dir("safe-absolute")
        tar_path = tmpdir / 'absolute.tar.gz'
        extract_dir = tmpdir / 'extract'
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
        tmpdir = _new_test_dir("safe-nested")
        tar_path = tmpdir / 'nested.tar.gz'
        extract_dir = tmpdir / 'extract'
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


class TestLoadCheckpointWithRecovery:
    """Test suite for load_checkpoint_with_recovery function."""

    def test_load_checkpoint_not_found(self):
        """Test loading non-existent checkpoint."""
        result = asyncio.run(
            load_checkpoint_with_recovery(
                '/nonexistent/checkpoint.tar.gz',
                'task_123',
            )
        )
        assert result is None

    def test_load_checkpoint_with_malicious_paths(self):
        """Test that malicious checkpoints are rejected."""
        tmpdir = _new_test_dir("load-malicious")
        tar_path = tmpdir / 'malicious.tar.gz'

        with tarfile.open(tar_path, 'w:gz') as tar:
            info = tarfile.TarInfo(name='../../evil.py')
            info.size = 0
            tar.addfile(info, fileobj=None)

        with pytest.raises(ValueError, match='Path traversal detected'):
            asyncio.run(load_checkpoint_with_recovery(str(tar_path), 'task_123'))

    def test_load_checkpoint_valid(self):
        """Test loading valid checkpoint."""
        import io
        tmpdir = _new_test_dir("load-valid")
        tar_path = tmpdir / 'valid.tar.gz'
        checkpoint_data = {'state': 'recovered', 'step': 5}

        with tarfile.open(tar_path, 'w:gz') as tar:
            # Add checkpoint.json with proper content
            json_data = json.dumps(checkpoint_data).encode()
            info = tarfile.TarInfo(name='checkpoint.json')
            info.size = len(json_data)
            tar.addfile(info, fileobj=io.BytesIO(json_data))

        result = asyncio.run(load_checkpoint_with_recovery(str(tar_path), 'task_123'))
        assert result == checkpoint_data


class TestCheckpointManagerInterface:
    """Test suite for the engine-side checkpoint manager abstraction."""

    def test_in_memory_checkpoint_manager_round_trip(self):
        manager = InMemoryCheckpointManager()
        payload = {"state": "running", "step": 7}

        assert isinstance(manager, CheckpointManager)

        asyncio.run(manager.save_checkpoint("task_123", payload))
        loaded = asyncio.run(manager.load_checkpoint("task_123"))
        assert loaded == payload
        asyncio.run(manager.delete_checkpoint("task_123"))
        assert asyncio.run(manager.load_checkpoint("task_123")) is None

    def test_manager_delegates_archive_recovery_helper(self):
        manager = InMemoryCheckpointManager()

        tmpdir = _new_test_dir("manager-valid")
        tar_path = tmpdir / "valid.tar.gz"
        checkpoint_data = {"state": "delegated", "step": 11}

        import io

        with tarfile.open(tar_path, "w:gz") as tar:
            json_data = json.dumps(checkpoint_data).encode()
            info = tarfile.TarInfo(name="checkpoint.json")
            info.size = len(json_data)
            tar.addfile(info, fileobj=io.BytesIO(json_data))

        result = asyncio.run(
            manager.load_checkpoint_with_recovery(
                str(tar_path),
                "task_123",
            )
        )
        assert result == checkpoint_data

    def test_manager_archive_recovery_keeps_traversal_protection(self):
        manager = InMemoryCheckpointManager()

        tmpdir = _new_test_dir("manager-malicious")
        tar_path = tmpdir / "malicious.tar.gz"

        with tarfile.open(tar_path, "w:gz") as tar:
            info = tarfile.TarInfo(name="../../evil.py")
            info.size = 0
            tar.addfile(info, fileobj=None)

        with pytest.raises(ValueError, match='Path traversal detected'):
            asyncio.run(
                manager.load_checkpoint_with_recovery(
                    str(tar_path),
                    "task_123",
                )
            )

    def test_object_store_checkpoint_manager_round_trip(self):
        object_store = RecordingObjectStore()
        manager = ObjectStoreCheckpointManager(object_store, prefix="tenant-a")
        payload = {"state": "running", "step": 3}

        asyncio.run(manager.save_checkpoint("task_123", payload))

        assert object_store.objects["tenant-a/task_123.json"][1] == "application/json"
        assert asyncio.run(manager.load_checkpoint("task_123")) == payload

        asyncio.run(manager.delete_checkpoint("task_123"))
        assert asyncio.run(manager.load_checkpoint("task_123")) is None

    def test_object_store_checkpoint_manager_validates_task_id(self):
        manager = ObjectStoreCheckpointManager(RecordingObjectStore())

        with pytest.raises(ValueError, match="Invalid task_id"):
            asyncio.run(manager.save_checkpoint("../escape", {"state": "bad"}))
