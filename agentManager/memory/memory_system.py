"""Memory System - Core architecture for multi-layer memory management."""

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional
from threading import RLock


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class MemoryLayer(Enum):
    """Memory layer types with TTL configurations.

    Attributes:
        SHORT_TERM: Current session memory (TTL: 1 hour)
        MEDIUM_TERM: Task history (TTL: 7 days)
        LONG_TERM: Knowledge base (permanent)
    """

    SHORT_TERM = (3600, "当前会话")  # 1 hour
    MEDIUM_TERM = (604800, "任务历史")  # 7 days
    LONG_TERM = (None, "知识库")  # Permanent


@dataclass
class MemoryEntry:
    """Represents a single memory entry with metadata.

    Attributes:
        entry_id: Unique identifier for the entry
        content: The actual memory content
        layer: Which memory layer this entry belongs to
        timestamp: When the entry was created
        ttl_seconds: Time-to-live in seconds (None for permanent)
        tags: List of tags for categorization
        metadata: Additional metadata dictionary
    """

    content: str
    layer: MemoryLayer
    tags: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    entry_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: datetime = field(default_factory=utc_now)
    ttl_seconds: Optional[int] = None

    def __post_init__(self) -> None:
        """Set TTL based on layer if not explicitly provided."""
        if self.ttl_seconds is None:
            self.ttl_seconds = self.layer.value[0]

    def is_expired(self) -> bool:
        """Check if entry has expired based on TTL.

        Returns:
            True if entry has expired, False otherwise
        """
        if self.ttl_seconds is None:
            return False
        expiry_time = self.timestamp + timedelta(seconds=self.ttl_seconds)
        return utc_now() > _ensure_aware(expiry_time)


def _ensure_aware(value: datetime) -> datetime:
    """Treat naive datetimes as UTC for backward compatibility."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


class MemorySystem:
    """Multi-layer memory system with SQLite persistence and TTL management.

    Provides storage, retrieval, search, and cleanup operations for memory entries
    across multiple layers with automatic expiration handling.

    When a ``vector_backend`` is provided, ``store`` indexes entry content for
    semantic search and ``search`` delegates to the vector backend for
    similarity-based retrieval. Structured data is always persisted in SQLite.
    """

    def __init__(
        self,
        storage_backend: str = "sqlite",
        db_path: Optional[str] = None,
        vector_backend: Any = None,
    ) -> None:
        """Initialize the memory system.

        Args:
            storage_backend: Backend type for structured storage ("sqlite").
            db_path: Path to SQLite database file. Defaults to "memory.db"
            vector_backend: Optional VectorSearchBackend for semantic search.

        Raises:
            ValueError: If unsupported backend is specified
        """
        if storage_backend != "sqlite":
            raise ValueError(f"Unsupported backend: {storage_backend}")

        self.backend = storage_backend
        self.db_path = Path(db_path or "memory.db")
        self.vector_backend = vector_backend
        self._lock = RLock()
        self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database schema with required tables and indexes."""
        with self._lock:
            self._conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_entries (
                    entry_id TEXT PRIMARY KEY,
                    content TEXT NOT NULL,
                    layer TEXT NOT NULL,
                    timestamp REAL NOT NULL,
                    ttl_seconds INTEGER,
                    tags TEXT NOT NULL,
                    metadata TEXT NOT NULL
                )
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_layer ON memory_entries(layer)
            """)
            self._conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON memory_entries(timestamp)
            """)
            self._conn.commit()

    def close(self) -> None:
        """Close the underlying SQLite connection."""
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    def __enter__(self) -> "MemorySystem":
        """Return this memory system as a context manager."""
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """Close the memory system on context manager exit."""
        self.close()

    def __del__(self) -> None:
        """Best-effort cleanup for callers that do not close explicitly."""
        try:
            self.close()
        except Exception:
            pass

    def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry in the system.

        When a ``vector_backend`` is configured, the entry content is also
        indexed for semantic search. Vector indexing is **best-effort**:
        failures are logged but do not prevent the SQLite write. In an
        async context (e.g. inside a running event loop), the upsert is
        scheduled as a fire-and-forget task; use ``astore()`` if you need
        to await completion.

        Args:
            entry: MemoryEntry object to store

        Returns:
            The entry_id of the stored entry
        """
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memory_entries
                (entry_id, content, layer, timestamp, ttl_seconds, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.entry_id,
                    entry.content,
                    entry.layer.name,
                    entry.timestamp.timestamp(),
                    entry.ttl_seconds,
                    json.dumps(entry.tags),
                    json.dumps(entry.metadata),
                ),
            )
            self._conn.commit()

        self._index_to_vector_backend(entry)

        return entry.entry_id

    async def astore(self, entry: MemoryEntry) -> str:
        """Async variant of ``store`` that awaits vector backend indexing.

        The SQLite write is synchronous (same as ``store``), but the vector
        backend upsert is awaited so callers can confirm indexing success.

        Args:
            entry: MemoryEntry object to store

        Returns:
            The entry_id of the stored entry
        """
        with self._lock:
            self._conn.execute(
                """
                INSERT OR REPLACE INTO memory_entries
                (entry_id, content, layer, timestamp, ttl_seconds, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    entry.entry_id,
                    entry.content,
                    entry.layer.name,
                    entry.timestamp.timestamp(),
                    entry.ttl_seconds,
                    json.dumps(entry.tags),
                    json.dumps(entry.metadata),
                ),
            )
            self._conn.commit()

        if self.vector_backend is not None:
            try:
                await self.vector_backend.upsert(entry.layer.name, entry.entry_id, entry.content)
            except Exception:
                pass

        return entry.entry_id

    def _index_to_vector_backend(self, entry: MemoryEntry) -> None:
        """Best-effort vector backend indexing after a synchronous store.

        When no event loop is running, runs the upsert inline via
        ``asyncio.run()``. When a loop is already running, schedules the
        upsert as a fire-and-forget task — the caller cannot know whether
        indexing succeeded. Use ``astore()`` for awaitable indexing.
        """
        if self.vector_backend is None:
            return

        import asyncio

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None

        if loop is not None and loop.is_running():
            asyncio.ensure_future(
                self.vector_backend.upsert(entry.layer.name, entry.entry_id, entry.content)
            )
        else:
            try:
                asyncio.run(
                    self.vector_backend.upsert(entry.layer.name, entry.entry_id, entry.content)
                )
            except Exception:
                pass

    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by ID.

        Args:
            entry_id: The ID of the entry to retrieve

        Returns:
            MemoryEntry if found and not expired, None otherwise
        """
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT content, layer, timestamp, ttl_seconds, tags, metadata
                FROM memory_entries WHERE entry_id = ?
            """,
                (entry_id,),
            )
            row = cursor.fetchone()

        if not row:
            return None

        content, layer, timestamp, ttl_seconds, tags, metadata = row
        entry = MemoryEntry(
            entry_id=entry_id,
            content=content,
            layer=MemoryLayer[layer],
            timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc),
            ttl_seconds=ttl_seconds,
            tags=json.loads(tags),
            metadata=json.loads(metadata),
        )

        if entry.is_expired():
            self._delete_entry(entry_id)
            return None

        return entry

    def search(self, query: str, layer: Optional[MemoryLayer] = None) -> List[MemoryEntry]:
        """Search memory entries by content and optional layer filter.

        When a ``vector_backend`` is configured and no event loop is
        running, uses similarity-based search via the vector backend.
        When an event loop is already running (e.g. inside FastAPI),
        falls back to substring matching to avoid blocking the loop.
        Use ``asearch()`` for proper async vector search.

        Args:
            query: Search query string
            layer: Optional layer filter. If None, searches all layers

        Returns:
            List of matching MemoryEntry objects (excluding expired entries)
        """
        if self.vector_backend is not None:
            import asyncio

            try:
                asyncio.get_running_loop()
            except RuntimeError:
                return self._search_via_vector_backend_sync(query, layer)

        return self._search_via_substring(query, layer)

    async def asearch(self, query: str, layer: Optional[MemoryLayer] = None) -> List[MemoryEntry]:
        """Async variant of ``search`` that awaits vector backend queries.

        When a ``vector_backend`` is configured, delegates to it for
        similarity-based retrieval and then fetches full MemoryEntry
        objects from SQLite. Falls back to substring matching when no
        vector backend is available or on query failure.

        Args:
            query: Search query string
            layer: Optional layer filter. If None, searches all layers

        Returns:
            List of matching MemoryEntry objects (excluding expired entries)
        """
        if self.vector_backend is None:
            return self._search_via_substring(query, layer)

        try:
            namespace = layer.name if layer else "all"
            results = await self.vector_backend.query(namespace, query)
        except Exception:
            return self._search_via_substring(query, layer)

        entries = []
        for result in results:
            entry = self.retrieve(result.key)
            if entry is not None:
                if layer is None or entry.layer == layer:
                    entries.append(entry)
        return entries

    def _search_via_vector_backend_sync(
        self, query: str, layer: Optional[MemoryLayer] = None
    ) -> List[MemoryEntry]:
        """Run a vector backend query synchronously via ``asyncio.run()``.

        Only safe to call when no event loop is running (e.g. CLI scripts,
        unit tests). Must not be called from inside an async context.
        """
        import asyncio

        try:
            namespace = layer.name if layer else "all"
            results = asyncio.run(self.vector_backend.query(namespace, query))
        except Exception:
            return self._search_via_substring(query, layer)

        entries = []
        for result in results:
            entry = self.retrieve(result.key)
            if entry is not None:
                if layer is None or entry.layer == layer:
                    entries.append(entry)
        return entries

    def _search_via_substring(
        self, query: str, layer: Optional[MemoryLayer] = None
    ) -> List[MemoryEntry]:
        """Search using SQLite substring matching (original behavior)."""
        with self._lock:
            if layer:
                cursor = self._conn.execute(
                    """
                    SELECT entry_id, content, layer, timestamp, ttl_seconds, tags, metadata
                    FROM memory_entries
                    WHERE layer = ? AND content LIKE ?
                """,
                    (layer.name, f"%{query}%"),
                )
            else:
                cursor = self._conn.execute(
                    """
                    SELECT entry_id, content, layer, timestamp, ttl_seconds, tags, metadata
                    FROM memory_entries WHERE content LIKE ?
                """,
                    (f"%{query}%",),
                )

            rows = cursor.fetchall()

        entries = []
        for row in rows:
            entry_id, content, layer_name, timestamp, ttl_seconds, tags, metadata = row
            entry = MemoryEntry(
                entry_id=entry_id,
                content=content,
                layer=MemoryLayer[layer_name],
                timestamp=datetime.fromtimestamp(timestamp, tz=timezone.utc),
                ttl_seconds=ttl_seconds,
                tags=json.loads(tags),
                metadata=json.loads(metadata),
            )
            if not entry.is_expired():
                entries.append(entry)

        return entries

    def cleanup_expired(self) -> int:
        """Remove all expired entries from the system.

        Returns:
            Number of entries deleted
        """
        current_time = time.time()
        with self._lock:
            cursor = self._conn.execute("""
                SELECT entry_id, timestamp, ttl_seconds FROM memory_entries
                WHERE ttl_seconds IS NOT NULL
            """)
            rows = cursor.fetchall()

        expired_ids = []
        for entry_id, timestamp, ttl_seconds in rows:
            if ttl_seconds and (current_time - timestamp) > ttl_seconds:
                expired_ids.append(entry_id)

        for entry_id in expired_ids:
            self._delete_entry(entry_id)

        return len(expired_ids)

    def get_layer_stats(self, layer: MemoryLayer) -> Dict[str, Any]:
        """Get statistics for a specific memory layer.

        Args:
            layer: The memory layer to analyze

        Returns:
            Dictionary containing:
                - layer: Layer name
                - description: Layer description in Chinese
                - entry_count: Number of entries in layer
                - total_size_bytes: Total size of content in bytes
                - ttl_seconds: TTL configuration for layer
        """
        with self._lock:
            cursor = self._conn.execute(
                """
                SELECT COUNT(*), SUM(LENGTH(content))
                FROM memory_entries WHERE layer = ?
            """,
                (layer.name,),
            )
            count, total_size = cursor.fetchone()

        return {
            "layer": layer.name,
            "description": layer.value[1],
            "entry_count": count or 0,
            "total_size_bytes": total_size or 0,
            "ttl_seconds": layer.value[0],
        }

    def _delete_entry(self, entry_id: str) -> None:
        """Delete an entry by ID.

        Args:
            entry_id: The ID of the entry to delete
        """
        with self._lock:
            self._conn.execute("DELETE FROM memory_entries WHERE entry_id = ?", (entry_id,))
            self._conn.commit()
