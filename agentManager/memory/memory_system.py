"""Memory System - Core architecture for multi-layer memory management."""

import json
import sqlite3
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional


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
    timestamp: datetime = field(default_factory=datetime.utcnow)
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
        return datetime.utcnow() > expiry_time


class MemorySystem:
    """Multi-layer memory system with SQLite persistence and TTL management.

    Provides storage, retrieval, search, and cleanup operations for memory entries
    across multiple layers with automatic expiration handling.
    """

    def __init__(self, storage_backend: str = "sqlite", db_path: Optional[str] = None) -> None:
        """Initialize the memory system.

        Args:
            storage_backend: Backend type (currently only "sqlite" supported)
            db_path: Path to SQLite database file. Defaults to "memory.db"

        Raises:
            ValueError: If unsupported backend is specified
        """
        if storage_backend != "sqlite":
            raise ValueError(f"Unsupported backend: {storage_backend}")

        self.backend = storage_backend
        self.db_path = Path(db_path or "memory.db")
        self._init_db()

    def _init_db(self) -> None:
        """Initialize SQLite database schema with required tables and indexes."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
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
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_layer ON memory_entries(layer)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_timestamp ON memory_entries(timestamp)
            """)
            conn.commit()

    def store(self, entry: MemoryEntry) -> str:
        """Store a memory entry in the system.

        Args:
            entry: MemoryEntry object to store

        Returns:
            The entry_id of the stored entry
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                INSERT OR REPLACE INTO memory_entries
                (entry_id, content, layer, timestamp, ttl_seconds, tags, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                entry.entry_id,
                entry.content,
                entry.layer.name,
                entry.timestamp.timestamp(),
                entry.ttl_seconds,
                json.dumps(entry.tags),
                json.dumps(entry.metadata)
            ))
            conn.commit()
        return entry.entry_id

    def retrieve(self, entry_id: str) -> Optional[MemoryEntry]:
        """Retrieve a memory entry by ID.

        Args:
            entry_id: The ID of the entry to retrieve

        Returns:
            MemoryEntry if found and not expired, None otherwise
        """
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT content, layer, timestamp, ttl_seconds, tags, metadata
                FROM memory_entries WHERE entry_id = ?
            """, (entry_id,))
            row = cursor.fetchone()

        if not row:
            return None

        content, layer, timestamp, ttl_seconds, tags, metadata = row
        entry = MemoryEntry(
            entry_id=entry_id,
            content=content,
            layer=MemoryLayer[layer],
            timestamp=datetime.fromtimestamp(timestamp),
            ttl_seconds=ttl_seconds,
            tags=json.loads(tags),
            metadata=json.loads(metadata)
        )

        if entry.is_expired():
            self._delete_entry(entry_id)
            return None

        return entry

    def search(self, query: str, layer: Optional[MemoryLayer] = None) -> List[MemoryEntry]:
        """Search memory entries by content and optional layer filter.

        Args:
            query: Search query string (case-insensitive substring match)
            layer: Optional layer filter. If None, searches all layers

        Returns:
            List of matching MemoryEntry objects (excluding expired entries)
        """
        with sqlite3.connect(self.db_path) as conn:
            if layer:
                cursor = conn.execute("""
                    SELECT entry_id, content, layer, timestamp, ttl_seconds, tags, metadata
                    FROM memory_entries
                    WHERE layer = ? AND content LIKE ?
                """, (layer.name, f"%{query}%"))
            else:
                cursor = conn.execute("""
                    SELECT entry_id, content, layer, timestamp, ttl_seconds, tags, metadata
                    FROM memory_entries WHERE content LIKE ?
                """, (f"%{query}%",))

            rows = cursor.fetchall()

        entries = []
        for row in rows:
            entry_id, content, layer_name, timestamp, ttl_seconds, tags, metadata = row
            entry = MemoryEntry(
                entry_id=entry_id,
                content=content,
                layer=MemoryLayer[layer_name],
                timestamp=datetime.fromtimestamp(timestamp),
                ttl_seconds=ttl_seconds,
                tags=json.loads(tags),
                metadata=json.loads(metadata)
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
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
        with sqlite3.connect(self.db_path) as conn:
            cursor = conn.execute("""
                SELECT COUNT(*), SUM(LENGTH(content))
                FROM memory_entries WHERE layer = ?
            """, (layer.name,))
            count, total_size = cursor.fetchone()

        return {
            "layer": layer.name,
            "description": layer.value[1],
            "entry_count": count or 0,
            "total_size_bytes": total_size or 0,
            "ttl_seconds": layer.value[0]
        }

    def _delete_entry(self, entry_id: str) -> None:
        """Delete an entry by ID.

        Args:
            entry_id: The ID of the entry to delete
        """
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("DELETE FROM memory_entries WHERE entry_id = ?", (entry_id,))
            conn.commit()
