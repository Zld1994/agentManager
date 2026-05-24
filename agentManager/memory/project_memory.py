"""Project Memory - Medium-term memory layer with persistent storage.

Stores project-level context including configuration, architecture, and
constraints with SQLite persistence for durability across sessions.
"""

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory_backend import MemoryBackend

logger = logging.getLogger(__name__)


class ProjectMemory(MemoryBackend):
    """Medium-term memory for project-level context with persistence.

    Features:
    - SQLite-based persistent storage
    - Project configuration and architecture tracking
    - Namespace isolation
    - Async operations with thread-safe database access
    """

    def __init__(self, db_path: str = "project_memory.db"):
        """Initialize ProjectMemory with SQLite backend.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self._init_db()
        logger.info(f"ProjectMemory initialized with db={db_path}")

    def _init_db(self) -> None:
        """Initialize SQLite database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS project_memory (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    metadata TEXT,
                    PRIMARY KEY (namespace, key)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_namespace
                ON project_memory(namespace)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_updated_at
                ON project_memory(updated_at)
            """)
            conn.commit()

    async def put(self, namespace: str, key: str, value: Any) -> None:
        """Store a value persistently.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace
            value: Value to store (will be JSON serialized)

        Raises:
            ValueError: If namespace or key is invalid
        """
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            try:
                import time
                current_time = time.time()
                value_json = json.dumps(value)

                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO project_memory
                        (namespace, key, value, created_at, updated_at, metadata)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (namespace, key, value_json, current_time, current_time, None))
                    conn.commit()

                logger.debug(f"Stored {namespace}:{key}")
            except Exception as e:
                logger.error(f"Failed to store {namespace}:{key}: {e}")
                raise

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        """Retrieve a value from persistent storage.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace

        Returns:
            Stored value if found, None otherwise
        """
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT value FROM project_memory
                        WHERE namespace = ? AND key = ?
                    """, (namespace, key))
                    row = cursor.fetchone()

                if row:
                    return json.loads(row[0])
                return None
            except Exception as e:
                logger.error(f"Failed to retrieve {namespace}:{key}: {e}")
                raise

    async def search(
        self,
        namespace: str,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for values by key substring match.

        Args:
            namespace: Namespace to search in
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching entries with metadata
        """
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT key, value FROM project_memory
                        WHERE namespace = ? AND key LIKE ?
                        LIMIT ?
                    """, (namespace, f"%{query}%", limit))
                    rows = cursor.fetchall()

                results = []
                for key, value in rows:
                    results.append({
                        "key": key,
                        "value": json.loads(value),
                        "namespace": namespace
                    })
                return results
            except Exception as e:
                logger.error(f"Search failed in {namespace}: {e}")
                raise

    async def delete(self, namespace: str, key: str) -> bool:
        """Delete a value from persistent storage.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace

        Returns:
            True if deleted, False if not found
        """
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        DELETE FROM project_memory
                        WHERE namespace = ? AND key = ?
                    """, (namespace, key))
                    conn.commit()
                    deleted = cursor.rowcount > 0

                if deleted:
                    logger.debug(f"Deleted {namespace}:{key}")
                return deleted
            except Exception as e:
                logger.error(f"Failed to delete {namespace}:{key}: {e}")
                raise

    async def clear(self, namespace: str) -> int:
        """Clear all entries in a namespace.

        Args:
            namespace: Namespace to clear

        Returns:
            Number of entries deleted
        """
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        DELETE FROM project_memory WHERE namespace = ?
                    """, (namespace,))
                    conn.commit()
                    count = cursor.rowcount

                logger.info(f"Cleared {namespace}: {count} entries")
                return count
            except Exception as e:
                logger.error(f"Failed to clear {namespace}: {e}")
                raise

    async def exists(self, namespace: str, key: str) -> bool:
        """Check if a key exists in namespace.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace

        Returns:
            True if key exists
        """
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT 1 FROM project_memory
                        WHERE namespace = ? AND key = ?
                    """, (namespace, key))
                    return cursor.fetchone() is not None
            except Exception as e:
                logger.error(f"Failed to check existence of {namespace}:{key}: {e}")
                raise

    async def get_all(self, namespace: str) -> Dict[str, Any]:
        """Get all entries in a namespace.

        Args:
            namespace: Namespace to retrieve from

        Returns:
            Dictionary of all key-value pairs
        """
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT key, value FROM project_memory
                        WHERE namespace = ?
                    """, (namespace,))
                    rows = cursor.fetchall()

                result = {}
                for key, value in rows:
                    result[key] = json.loads(value)
                return result
            except Exception as e:
                logger.error(f"Failed to get all from {namespace}: {e}")
                raise

    async def get_namespace_stats(self, namespace: str) -> Dict[str, Any]:
        """Get statistics for a namespace.

        Args:
            namespace: Namespace to analyze

        Returns:
            Dictionary with entry count and size info
        """
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT COUNT(*), SUM(LENGTH(value))
                        FROM project_memory WHERE namespace = ?
                    """, (namespace,))
                    count, total_size = cursor.fetchone()

                return {
                    "namespace": namespace,
                    "entry_count": count or 0,
                    "total_size_bytes": total_size or 0
                }
            except Exception as e:
                logger.error(f"Failed to get stats for {namespace}: {e}")
                raise
