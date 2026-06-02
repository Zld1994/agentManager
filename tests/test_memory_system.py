"""Unit tests for the three-layer memory system.

Tests cover SessionMemory, ProjectMemory, EngineeringMemory, and integration.
"""

import asyncio
import pytest
import tempfile
import uuid
from pathlib import Path

from agentManager.memory import (
    SessionMemory,
    ProjectMemory,
    EngineeringMemory,
)


def _memory_temp_dir() -> Path:
    """Create a memory test directory without cleanup side effects."""
    path = Path(tempfile.gettempdir()) / "agentmanager-memory-system" / uuid.uuid4().hex
    path.mkdir(parents=True, exist_ok=True)
    return path


class TestSessionMemory:
    """Tests for SessionMemory (short-term memory with TTL)."""

    @pytest.fixture
    def session_memory(self):
        """Create a SessionMemory instance."""
        return SessionMemory(default_ttl=3600)

    @pytest.mark.asyncio
    async def test_put_and_get(self, session_memory):
        """Test basic put and get operations."""
        await session_memory.put("test_ns", "key1", "value1")
        result = await session_memory.get("test_ns", "key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_put_complex_value(self, session_memory):
        """Test storing complex objects."""
        data = {"name": "test", "count": 42, "nested": {"key": "value"}}
        await session_memory.put("test_ns", "complex", data)
        result = await session_memory.get("test_ns", "complex")
        assert result == data

    @pytest.mark.asyncio
    async def test_get_nonexistent_key(self, session_memory):
        """Test getting a key that doesn't exist."""
        result = await session_memory.get("test_ns", "nonexistent")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete(self, session_memory):
        """Test delete operation."""
        await session_memory.put("test_ns", "key1", "value1")
        deleted = await session_memory.delete("test_ns", "key1")
        assert deleted is True
        result = await session_memory.get("test_ns", "key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_delete_nonexistent(self, session_memory):
        """Test deleting a key that doesn't exist."""
        deleted = await session_memory.delete("test_ns", "nonexistent")
        assert deleted is False

    @pytest.mark.asyncio
    async def test_exists(self, session_memory):
        """Test exists check."""
        await session_memory.put("test_ns", "key1", "value1")
        exists = await session_memory.exists("test_ns", "key1")
        assert exists is True
        exists = await session_memory.exists("test_ns", "nonexistent")
        assert exists is False

    @pytest.mark.asyncio
    async def test_clear(self, session_memory):
        """Test clearing a namespace."""
        await session_memory.put("test_ns", "key1", "value1")
        await session_memory.put("test_ns", "key2", "value2")
        count = await session_memory.clear("test_ns")
        assert count == 2
        result = await session_memory.get("test_ns", "key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_search(self, session_memory):
        """Test search functionality."""
        await session_memory.put("test_ns", "error_key1", "error value")
        await session_memory.put("test_ns", "error_key2", "another error")
        await session_memory.put("test_ns", "info_key", "info value")

        results = await session_memory.search("test_ns", "error", limit=10)
        assert len(results) == 2
        assert all("error" in r["key"] for r in results)

    @pytest.mark.asyncio
    async def test_get_all(self, session_memory):
        """Test get_all operation."""
        await session_memory.put("test_ns", "key1", "value1")
        await session_memory.put("test_ns", "key2", "value2")
        all_data = await session_memory.get_all("test_ns")
        assert len(all_data) == 2
        assert all_data["key1"] == "value1"
        assert all_data["key2"] == "value2"

    @pytest.mark.asyncio
    async def test_namespace_isolation(self, session_memory):
        """Test that namespaces are isolated."""
        await session_memory.put("ns1", "key", "value1")
        await session_memory.put("ns2", "key", "value2")
        result1 = await session_memory.get("ns1", "key")
        result2 = await session_memory.get("ns2", "key")
        assert result1 == "value1"
        assert result2 == "value2"

    @pytest.mark.asyncio
    async def test_invalid_namespace(self, session_memory):
        """Test that empty namespace raises error."""
        with pytest.raises(ValueError):
            await session_memory.put("", "key", "value")

    @pytest.mark.asyncio
    async def test_invalid_key(self, session_memory):
        """Test that empty key raises error."""
        with pytest.raises(ValueError):
            await session_memory.put("ns", "", "value")


class TestProjectMemory:
    """Tests for ProjectMemory (medium-term persistent memory)."""

    @pytest.fixture
    def project_memory(self):
        """Create a ProjectMemory instance with temp database."""
        db_path = _memory_temp_dir() / "test_project.db"
        yield ProjectMemory(str(db_path))

    @pytest.mark.asyncio
    async def test_put_and_get(self, project_memory):
        """Test basic put and get operations."""
        await project_memory.put("project_ns", "config", {"version": "1.0"})
        result = await project_memory.get("project_ns", "config")
        assert result == {"version": "1.0"}

    @pytest.mark.asyncio
    async def test_persistence(self):
        """Test that data persists across instances."""
        tmpdir = _memory_temp_dir()
        db_path = tmpdir / "test_persist.db"

        # First instance
        pm1 = ProjectMemory(str(db_path))
        await pm1.put("project_ns", "key1", "value1")

        # Second instance with same database
        pm2 = ProjectMemory(str(db_path))
        result = await pm2.get("project_ns", "key1")
        assert result == "value1"

    @pytest.mark.asyncio
    async def test_delete(self, project_memory):
        """Test delete operation."""
        await project_memory.put("project_ns", "key1", "value1")
        deleted = await project_memory.delete("project_ns", "key1")
        assert deleted is True
        result = await project_memory.get("project_ns", "key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear(self, project_memory):
        """Test clearing a namespace."""
        await project_memory.put("project_ns", "key1", "value1")
        await project_memory.put("project_ns", "key2", "value2")
        count = await project_memory.clear("project_ns")
        assert count == 2

    @pytest.mark.asyncio
    async def test_search(self, project_memory):
        """Test search functionality."""
        await project_memory.put("project_ns", "config_db", {"type": "postgres"})
        await project_memory.put("project_ns", "config_cache", {"type": "redis"})
        await project_memory.put("project_ns", "version", "1.0")

        results = await project_memory.search("project_ns", "config", limit=10)
        assert len(results) == 2

    @pytest.mark.asyncio
    async def test_exists(self, project_memory):
        """Test exists check."""
        await project_memory.put("project_ns", "key1", "value1")
        exists = await project_memory.exists("project_ns", "key1")
        assert exists is True

    @pytest.mark.asyncio
    async def test_get_all(self, project_memory):
        """Test get_all operation."""
        await project_memory.put("project_ns", "key1", "value1")
        await project_memory.put("project_ns", "key2", "value2")
        all_data = await project_memory.get_all("project_ns")
        assert len(all_data) == 2

    @pytest.mark.asyncio
    async def test_get_namespace_stats(self, project_memory):
        """Test namespace statistics."""
        await project_memory.put("project_ns", "key1", "value1")
        await project_memory.put("project_ns", "key2", "value2")
        stats = await project_memory.get_namespace_stats("project_ns")
        assert stats["entry_count"] == 2
        assert stats["namespace"] == "project_ns"
        assert stats["total_size_bytes"] > 0


class TestEngineeringMemory:
    """Tests for EngineeringMemory (long-term memory with vector search)."""

    @pytest.fixture
    def engineering_memory(self):
        """Create an EngineeringMemory instance with temp database."""
        db_path = _memory_temp_dir() / "test_engineering.db"
        yield EngineeringMemory(str(db_path))

    @pytest.mark.asyncio
    async def test_put_and_get(self, engineering_memory):
        """Test basic put and get operations."""
        error_data = {
            "content": "Database connection timeout error",
            "type": "error",
            "tags": ["database", "timeout"],
        }
        await engineering_memory.put("eng_ns", "error_001", error_data)
        result = await engineering_memory.get("eng_ns", "error_001")
        assert result == error_data

    @pytest.mark.asyncio
    async def test_vector_search(self, engineering_memory):
        """Test vector similarity search."""
        await engineering_memory.put(
            "eng_ns", "error_1", {"content": "Database connection timeout error", "type": "error"}
        )
        await engineering_memory.put(
            "eng_ns", "error_2", {"content": "Network timeout during API call", "type": "error"}
        )
        await engineering_memory.put(
            "eng_ns", "fix_1", {"content": "Increase retry count for resilience", "type": "fix"}
        )

        results = await engineering_memory.search("eng_ns", "timeout", limit=10)
        assert len(results) >= 2
        assert all(r["similarity"] > 0 for r in results)
        # Results should be sorted by similarity
        assert results[0]["similarity"] >= results[-1]["similarity"]

    @pytest.mark.asyncio
    async def test_get_by_type(self, engineering_memory):
        """Test filtering by content type."""
        await engineering_memory.put(
            "eng_ns", "error_1", {"content": "Error message", "type": "error"}
        )
        await engineering_memory.put("eng_ns", "fix_1", {"content": "Fix message", "type": "fix"})

        errors = await engineering_memory.get_by_type("eng_ns", "error", limit=10)
        assert len(errors) == 1
        assert errors[0]["key"] == "error_1"

    @pytest.mark.asyncio
    async def test_delete(self, engineering_memory):
        """Test delete operation."""
        await engineering_memory.put("eng_ns", "key1", {"content": "test"})
        deleted = await engineering_memory.delete("eng_ns", "key1")
        assert deleted is True
        result = await engineering_memory.get("eng_ns", "key1")
        assert result is None

    @pytest.mark.asyncio
    async def test_clear(self, engineering_memory):
        """Test clearing a namespace."""
        await engineering_memory.put("eng_ns", "key1", {"content": "test1"})
        await engineering_memory.put("eng_ns", "key2", {"content": "test2"})
        count = await engineering_memory.clear("eng_ns")
        assert count == 2

    @pytest.mark.asyncio
    async def test_exists(self, engineering_memory):
        """Test exists check."""
        await engineering_memory.put("eng_ns", "key1", {"content": "test"})
        exists = await engineering_memory.exists("eng_ns", "key1")
        assert exists is True

    @pytest.mark.asyncio
    async def test_get_all(self, engineering_memory):
        """Test get_all operation."""
        await engineering_memory.put("eng_ns", "key1", {"content": "test1"})
        await engineering_memory.put("eng_ns", "key2", {"content": "test2"})
        all_data = await engineering_memory.get_all("eng_ns")
        assert len(all_data) == 2

    @pytest.mark.asyncio
    async def test_get_namespace_stats(self, engineering_memory):
        """Test namespace statistics with type distribution."""
        await engineering_memory.put("eng_ns", "error_1", {"content": "Error", "type": "error"})
        await engineering_memory.put("eng_ns", "fix_1", {"content": "Fix", "type": "fix"})
        stats = await engineering_memory.get_namespace_stats("eng_ns")
        assert stats["entry_count"] == 2
        assert "error" in stats["type_distribution"]
        assert "fix" in stats["type_distribution"]


class TestMemoryIntegration:
    """Integration tests for the three-layer memory system."""

    @pytest.mark.asyncio
    async def test_three_layer_workflow(self):
        """Test a complete workflow using all three memory layers."""
        # Session memory for current session data
        session_mem = SessionMemory(default_ttl=3600)

        # Project memory for project context
        tmpdir = _memory_temp_dir()
        project_db = tmpdir / "project.db"
        project_mem = ProjectMemory(str(project_db))

        # Engineering memory for knowledge base
        eng_db = tmpdir / "engineering.db"
        eng_mem = EngineeringMemory(str(eng_db))

        # Store session data
        await session_mem.put("session_1", "current_task", "debugging")

        # Store project context
        await project_mem.put("project_1", "config", {"name": "TestProject", "version": "1.0"})

        # Store engineering knowledge
        await eng_mem.put(
            "knowledge",
            "error_pattern_1",
            {
                "content": "Timeout errors in database connections",
                "type": "error_pattern",
                "tags": ["database", "timeout"],
            },
        )

        # Verify all layers
        session_data = await session_mem.get("session_1", "current_task")
        assert session_data == "debugging"

        project_data = await project_mem.get("project_1", "config")
        assert project_data["name"] == "TestProject"

        eng_data = await eng_mem.get("knowledge", "error_pattern_1")
        assert eng_data["type"] == "error_pattern"

    @pytest.mark.asyncio
    async def test_namespace_isolation_across_layers(self):
        """Test that namespaces are properly isolated across layers."""
        session_mem = SessionMemory()

        tmpdir = _memory_temp_dir()
        project_mem = ProjectMemory(str(tmpdir / "project.db"))
        EngineeringMemory(str(tmpdir / "eng.db"))

        # Store same key in different namespaces
        await session_mem.put("ns1", "key", "session_value_1")
        await session_mem.put("ns2", "key", "session_value_2")

        await project_mem.put("ns1", "key", "project_value_1")
        await project_mem.put("ns2", "key", "project_value_2")

        # Verify isolation
        assert await session_mem.get("ns1", "key") == "session_value_1"
        assert await session_mem.get("ns2", "key") == "session_value_2"

        assert await project_mem.get("ns1", "key") == "project_value_1"
        assert await project_mem.get("ns2", "key") == "project_value_2"

    @pytest.mark.asyncio
    async def test_error_handling(self):
        """Test error handling across memory layers."""
        session_mem = SessionMemory()

        # Test invalid namespace
        with pytest.raises(ValueError):
            await session_mem.put("", "key", "value")

        # Test invalid key
        with pytest.raises(ValueError):
            await session_mem.get("ns", "")

        # Test search with invalid namespace
        with pytest.raises(ValueError):
            await session_mem.search("", "query")

    @pytest.mark.asyncio
    async def test_concurrent_operations(self):
        """Test concurrent operations on memory layers."""
        session_mem = SessionMemory()

        async def store_data(ns, key, value):
            await session_mem.put(ns, key, value)

        # Run concurrent operations
        tasks = [store_data("ns1", f"key_{i}", f"value_{i}") for i in range(10)]
        await asyncio.gather(*tasks)

        # Verify all data was stored
        all_data = await session_mem.get_all("ns1")
        assert len(all_data) == 10
