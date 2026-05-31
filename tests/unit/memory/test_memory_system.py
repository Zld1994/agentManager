"""Unit tests for Memory System core architecture."""

import json
import tempfile
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from agentManager.memory import MemoryEntry, MemoryLayer, MemorySystem


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def memory_system(temp_db):
    """Create a MemorySystem instance with temporary database."""
    system = MemorySystem(db_path=temp_db)
    yield system
    system.close()


def utc_now():
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TestMemoryLayer:
    """Test MemoryLayer enum."""

    def test_layer_values(self):
        """Test that layers have correct TTL values."""
        assert MemoryLayer.SHORT_TERM.value[0] == 3600  # 1 hour
        assert MemoryLayer.MEDIUM_TERM.value[0] == 604800  # 7 days
        assert MemoryLayer.LONG_TERM.value[0] is None  # Permanent

    def test_layer_descriptions(self):
        """Test that layers have Chinese descriptions."""
        assert MemoryLayer.SHORT_TERM.value[1] == "当前会话"
        assert MemoryLayer.MEDIUM_TERM.value[1] == "任务历史"
        assert MemoryLayer.LONG_TERM.value[1] == "知识库"


class TestMemoryEntry:
    """Test MemoryEntry dataclass."""

    def test_entry_creation_with_defaults(self):
        """Test creating entry with default values."""
        entry = MemoryEntry(
            content="Test content",
            layer=MemoryLayer.SHORT_TERM
        )
        assert entry.content == "Test content"
        assert entry.layer == MemoryLayer.SHORT_TERM
        assert entry.entry_id is not None
        assert entry.timestamp is not None
        assert entry.tags == []
        assert entry.metadata == {}

    def test_entry_ttl_auto_set(self):
        """Test that TTL is automatically set based on layer."""
        entry = MemoryEntry(
            content="Test",
            layer=MemoryLayer.SHORT_TERM
        )
        assert entry.ttl_seconds == 3600

        entry = MemoryEntry(
            content="Test",
            layer=MemoryLayer.LONG_TERM
        )
        assert entry.ttl_seconds is None

    def test_entry_custom_ttl(self):
        """Test overriding TTL."""
        entry = MemoryEntry(
            content="Test",
            layer=MemoryLayer.SHORT_TERM,
            ttl_seconds=7200
        )
        assert entry.ttl_seconds == 7200

    def test_entry_with_tags_and_metadata(self):
        """Test entry with tags and metadata."""
        entry = MemoryEntry(
            content="Test",
            layer=MemoryLayer.MEDIUM_TERM,
            tags=["important", "urgent"],
            metadata={"priority": "high", "source": "api"}
        )
        assert entry.tags == ["important", "urgent"]
        assert entry.metadata["priority"] == "high"

    def test_entry_is_expired_short_term(self):
        """Test expiration check for short-term memory."""
        entry = MemoryEntry(
            content="Test",
            layer=MemoryLayer.SHORT_TERM,
            timestamp=utc_now() - timedelta(hours=2)
        )
        assert entry.is_expired()

    def test_entry_not_expired(self):
        """Test non-expired entry."""
        entry = MemoryEntry(
            content="Test",
            layer=MemoryLayer.SHORT_TERM
        )
        assert not entry.is_expired()

    def test_entry_long_term_never_expires(self):
        """Test that long-term entries never expire."""
        entry = MemoryEntry(
            content="Test",
            layer=MemoryLayer.LONG_TERM,
            timestamp=utc_now() - timedelta(days=365)
        )
        assert not entry.is_expired()


class TestMemorySystem:
    """Test MemorySystem class."""

    def test_initialization(self, temp_db):
        """Test system initialization."""
        system = MemorySystem(db_path=temp_db)
        assert system.backend == "sqlite"
        assert system.db_path == Path(temp_db)
        system.close()

    def test_invalid_backend(self, temp_db):
        """Test that invalid backend raises error."""
        with pytest.raises(ValueError, match="Unsupported backend"):
            MemorySystem(storage_backend="redis", db_path=temp_db)

    def test_store_and_retrieve(self, memory_system):
        """Test storing and retrieving an entry."""
        entry = MemoryEntry(
            content="Test content",
            layer=MemoryLayer.SHORT_TERM,
            tags=["test"]
        )
        entry_id = memory_system.store(entry)
        assert entry_id == entry.entry_id

        retrieved = memory_system.retrieve(entry_id)
        assert retrieved is not None
        assert retrieved.content == "Test content"
        assert retrieved.layer == MemoryLayer.SHORT_TERM
        assert retrieved.tags == ["test"]

    def test_retrieve_nonexistent(self, memory_system):
        """Test retrieving non-existent entry."""
        result = memory_system.retrieve("nonexistent-id")
        assert result is None

    def test_retrieve_expired_entry(self, memory_system):
        """Test that expired entries are not retrieved."""
        entry = MemoryEntry(
            content="Expired content",
            layer=MemoryLayer.SHORT_TERM,
            timestamp=utc_now() - timedelta(hours=2)
        )
        memory_system.store(entry)

        retrieved = memory_system.retrieve(entry.entry_id)
        assert retrieved is None

    def test_search_by_content(self, memory_system):
        """Test searching entries by content."""
        entry1 = MemoryEntry(
            content="Python programming",
            layer=MemoryLayer.SHORT_TERM
        )
        entry2 = MemoryEntry(
            content="JavaScript development",
            layer=MemoryLayer.SHORT_TERM
        )
        memory_system.store(entry1)
        memory_system.store(entry2)

        results = memory_system.search("Python")
        assert len(results) == 1
        assert results[0].content == "Python programming"

    def test_search_by_layer(self, memory_system):
        """Test searching entries filtered by layer."""
        entry1 = MemoryEntry(
            content="Short term data",
            layer=MemoryLayer.SHORT_TERM
        )
        entry2 = MemoryEntry(
            content="Long term data",
            layer=MemoryLayer.LONG_TERM
        )
        memory_system.store(entry1)
        memory_system.store(entry2)

        results = memory_system.search("data", layer=MemoryLayer.SHORT_TERM)
        assert len(results) == 1
        assert results[0].layer == MemoryLayer.SHORT_TERM

    def test_search_case_insensitive(self, memory_system):
        """Test that search is case-insensitive."""
        entry = MemoryEntry(
            content="Important Data",
            layer=MemoryLayer.SHORT_TERM
        )
        memory_system.store(entry)

        results = memory_system.search("important")
        assert len(results) == 1

    def test_cleanup_expired(self, memory_system):
        """Test cleanup of expired entries."""
        entry1 = MemoryEntry(
            content="Expired",
            layer=MemoryLayer.SHORT_TERM,
            timestamp=utc_now() - timedelta(hours=2)
        )
        entry2 = MemoryEntry(
            content="Valid",
            layer=MemoryLayer.LONG_TERM
        )
        memory_system.store(entry1)
        memory_system.store(entry2)

        deleted = memory_system.cleanup_expired()
        assert deleted == 1

        retrieved = memory_system.retrieve(entry2.entry_id)
        assert retrieved is not None

    def test_cleanup_long_term_not_deleted(self, memory_system):
        """Test that long-term entries are not deleted during cleanup."""
        entry = MemoryEntry(
            content="Permanent",
            layer=MemoryLayer.LONG_TERM,
            timestamp=utc_now() - timedelta(days=365)
        )
        memory_system.store(entry)

        deleted = memory_system.cleanup_expired()
        assert deleted == 0

        retrieved = memory_system.retrieve(entry.entry_id)
        assert retrieved is not None

    def test_get_layer_stats_empty(self, memory_system):
        """Test layer stats for empty layer."""
        stats = memory_system.get_layer_stats(MemoryLayer.SHORT_TERM)
        assert stats["layer"] == "SHORT_TERM"
        assert stats["description"] == "当前会话"
        assert stats["entry_count"] == 0
        assert stats["total_size_bytes"] == 0
        assert stats["ttl_seconds"] == 3600

    def test_get_layer_stats_with_entries(self, memory_system):
        """Test layer stats with entries."""
        entry1 = MemoryEntry(
            content="Content 1",
            layer=MemoryLayer.SHORT_TERM
        )
        entry2 = MemoryEntry(
            content="Content 2",
            layer=MemoryLayer.SHORT_TERM
        )
        memory_system.store(entry1)
        memory_system.store(entry2)

        stats = memory_system.get_layer_stats(MemoryLayer.SHORT_TERM)
        assert stats["entry_count"] == 2
        assert stats["total_size_bytes"] > 0

    def test_multiple_layers_isolation(self, memory_system):
        """Test that entries in different layers are isolated."""
        entry1 = MemoryEntry(
            content="Short term",
            layer=MemoryLayer.SHORT_TERM
        )
        entry2 = MemoryEntry(
            content="Long term",
            layer=MemoryLayer.LONG_TERM
        )
        memory_system.store(entry1)
        memory_system.store(entry2)

        short_stats = memory_system.get_layer_stats(MemoryLayer.SHORT_TERM)
        long_stats = memory_system.get_layer_stats(MemoryLayer.LONG_TERM)

        assert short_stats["entry_count"] == 1
        assert long_stats["entry_count"] == 1

    def test_store_update_existing(self, memory_system):
        """Test updating an existing entry."""
        entry = MemoryEntry(
            content="Original",
            layer=MemoryLayer.SHORT_TERM,
            entry_id="test-id"
        )
        memory_system.store(entry)

        updated_entry = MemoryEntry(
            content="Updated",
            layer=MemoryLayer.SHORT_TERM,
            entry_id="test-id"
        )
        memory_system.store(updated_entry)

        retrieved = memory_system.retrieve("test-id")
        assert retrieved.content == "Updated"

    def test_context_manager_closes_connection(self, temp_db):
        """Test MemorySystem closes its SQLite connection as a context manager."""
        with MemorySystem(db_path=temp_db) as system:
            assert system._conn is not None

        assert system._conn is None


class TestMemorySystemVectorBackend:
    """Test MemorySystem with pluggable vector backend."""

    def test_accepts_vector_backend(self, temp_db):
        from agentManager.memory.vector_backend import InMemoryVectorSearchBackend
        vector = InMemoryVectorSearchBackend()
        mem = MemorySystem(db_path=temp_db, vector_backend=vector)
        assert mem.vector_backend is vector
        mem.close()

    def test_none_vector_backend_is_default(self, temp_db):
        mem = MemorySystem(db_path=temp_db)
        assert mem.vector_backend is None
        mem.close()

    def test_sync_search_falls_back_on_vector_error(self, temp_db):
        from unittest.mock import AsyncMock, MagicMock
        vector = MagicMock()
        vector.query = AsyncMock(side_effect=RuntimeError("vector error"))
        mem = MemorySystem(db_path=temp_db, vector_backend=vector)
        entry = MemoryEntry(content="Python programming", layer=MemoryLayer.SHORT_TERM)
        mem.store(entry)
        results = mem._search_via_vector_backend_sync("Python")
        assert len(results) == 1
        assert results[0].content == "Python programming"
        mem.close()

    def test_search_uses_substring_when_no_vector_backend(self, temp_db):
        mem = MemorySystem(db_path=temp_db)
        entry = MemoryEntry(content="Python programming", layer=MemoryLayer.SHORT_TERM)
        mem.store(entry)
        results = mem.search("Python")
        assert len(results) == 1
        mem.close()

    def test_search_falls_back_to_substring_inside_running_loop(self, temp_db):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        vector = MagicMock()
        vector.query = AsyncMock(return_value=[])
        mem = MemorySystem(db_path=temp_db, vector_backend=vector)
        entry = MemoryEntry(content="Python programming", layer=MemoryLayer.SHORT_TERM)
        mem.store(entry)

        async def _run():
            results = mem.search("Python")
            assert len(results) == 1
            assert results[0].content == "Python programming"

        asyncio.run(_run())
        mem.close()

    @pytest.mark.asyncio
    async def test_asearch_uses_vector_backend(self, temp_db):
        from unittest.mock import AsyncMock, MagicMock
        from agentManager.memory.vector_backend import VectorSearchResult
        vector = MagicMock()
        vector.upsert = AsyncMock(return_value=None)
        vector.query = AsyncMock(return_value=[
            VectorSearchResult(key="entry-1", score=0.9)
        ])
        mem = MemorySystem(db_path=temp_db, vector_backend=vector)
        entry = MemoryEntry(content="Python programming", layer=MemoryLayer.SHORT_TERM, entry_id="entry-1")
        mem.store(entry)

        results = await mem.asearch("Python")
        assert len(results) == 1
        assert results[0].content == "Python programming"
        vector.query.assert_awaited_once()
        mem.close()

    @pytest.mark.asyncio
    async def test_astore_awaits_vector_upsert(self, temp_db):
        from unittest.mock import AsyncMock, MagicMock
        vector = MagicMock()
        vector.upsert = AsyncMock()
        mem = MemorySystem(db_path=temp_db, vector_backend=vector)
        entry = MemoryEntry(content="Test content", layer=MemoryLayer.SHORT_TERM)

        await mem.astore(entry)
        vector.upsert.assert_awaited_once()
        mem.close()
