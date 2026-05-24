"""Engineering Memory - Long-term memory layer with vector search support.

Stores error cases, repair experiences, and test results with semantic
search capabilities based on text similarity for knowledge base functionality.
"""

import asyncio
import json
import logging
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory_backend import MemoryBackend

logger = logging.getLogger(__name__)


def _simple_vector_similarity(text1: str, text2: str) -> float:
    """Calculate simple text similarity using word overlap.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity score between 0 and 1
    """
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())

    if not words1 or not words2:
        return 0.0

    intersection = len(words1 & words2)
    union = len(words1 | words2)
    return intersection / union if union > 0 else 0.0


def _tokenize_text(text: str) -> List[str]:
    """Simple tokenization for text.

    Args:
        text: Text to tokenize

    Returns:
        List of tokens
    """
    import re
    # Remove special characters and split by whitespace
    tokens = re.findall(r'\w+', text.lower())
    return tokens


class EngineeringMemory(MemoryBackend):
    """Long-term memory for engineering knowledge with vector search.

    Features:
    - SQLite-based persistent storage
    - Vector similarity search for semantic matching
    - Error case and repair experience tracking
    - Test result history
    - Knowledge base functionality
    - Namespace isolation
    - Async operations
    """

    def __init__(self, db_path: str = "engineering_memory.db"):
        """Initialize EngineeringMemory with SQLite backend.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self._init_db()
        logger.info(f"EngineeringMemory initialized with db={db_path}")

    def _init_db(self) -> None:
        """Initialize SQLite database schema with vector support."""
        with sqlite3.connect(self.db_path) as conn:
            # Main memory table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS engineering_memory (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    content_type TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    tags TEXT,
                    metadata TEXT,
                    PRIMARY KEY (namespace, key)
                )
            """)

            # Vector embeddings table for semantic search
            conn.execute("""
                CREATE TABLE IF NOT EXISTS memory_vectors (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    tokens TEXT NOT NULL,
                    PRIMARY KEY (namespace, key),
                    FOREIGN KEY (namespace, key)
                        REFERENCES engineering_memory(namespace, key)
                        ON DELETE CASCADE
                )
            """)

            # Indexes for performance
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_namespace
                ON engineering_memory(namespace)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_content_type
                ON engineering_memory(content_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON engineering_memory(created_at)
            """)
            conn.commit()

    async def put(self, namespace: str, key: str, value: Any) -> None:
        """Store a value with vector indexing.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace
            value: Value to store (dict with 'content' and optional 'type', 'tags')

        Raises:
            ValueError: If namespace or key is invalid
        """
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            try:
                import time
                current_time = time.time()

                # Extract content and metadata
                if isinstance(value, dict):
                    content = value.get("content", "")
                    content_type = value.get("type", "general")
                    tags = value.get("tags", [])
                else:
                    content = str(value)
                    content_type = "general"
                    tags = []

                value_json = json.dumps(value)
                tags_json = json.dumps(tags)

                # Tokenize content for vector search
                tokens = _tokenize_text(content)
                tokens_json = json.dumps(tokens)

                with sqlite3.connect(self.db_path) as conn:
                    # Store main entry
                    conn.execute("""
                        INSERT OR REPLACE INTO engineering_memory
                        (namespace, key, value, content_type, created_at,
                         updated_at, tags, metadata)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (namespace, key, value_json, content_type,
                          current_time, current_time, tags_json, None))

                    # Store vector tokens
                    conn.execute("""
                        INSERT OR REPLACE INTO memory_vectors
                        (namespace, key, tokens)
                        VALUES (?, ?, ?)
                    """, (namespace, key, tokens_json))

                    conn.commit()

                logger.debug(f"Stored {namespace}:{key} with {len(tokens)} tokens")
            except Exception as e:
                logger.error(f"Failed to store {namespace}:{key}: {e}")
                raise

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        """Retrieve a value from storage.

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
                        SELECT value FROM engineering_memory
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
        """Search using vector similarity.

        Args:
            namespace: Namespace to search in
            query: Search query string
            limit: Maximum number of results

        Returns:
            List of matching entries sorted by similarity
        """
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT em.key, em.value, mv.tokens
                        FROM engineering_memory em
                        LEFT JOIN memory_vectors mv
                            ON em.namespace = mv.namespace
                            AND em.key = mv.key
                        WHERE em.namespace = ?
                    """, (namespace,))
                    rows = cursor.fetchall()

                # Calculate similarity scores
                results = []
                query_tokens = set(_tokenize_text(query))

                for key, value, tokens_json in rows:
                    if tokens_json:
                        tokens = set(json.loads(tokens_json))
                        # Calculate Jaccard similarity
                        if tokens or query_tokens:
                            intersection = len(tokens & query_tokens)
                            union = len(tokens | query_tokens)
                            similarity = intersection / union if union > 0 else 0.0
                        else:
                            similarity = 0.0
                    else:
                        similarity = 0.0

                    if similarity > 0:
                        results.append({
                            "key": key,
                            "value": json.loads(value),
                            "namespace": namespace,
                            "similarity": similarity
                        })

                # Sort by similarity descending
                results.sort(key=lambda x: x["similarity"], reverse=True)
                return results[:limit]

            except Exception as e:
                logger.error(f"Search failed in {namespace}: {e}")
                raise

    async def delete(self, namespace: str, key: str) -> bool:
        """Delete a value from storage.

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
                        DELETE FROM engineering_memory
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
                        DELETE FROM engineering_memory WHERE namespace = ?
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
                        SELECT 1 FROM engineering_memory
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
                        SELECT key, value FROM engineering_memory
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

    async def get_by_type(
        self,
        namespace: str,
        content_type: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Get entries by content type.

        Args:
            namespace: Namespace to search in
            content_type: Type of content to filter by
            limit: Maximum number of results

        Returns:
            List of matching entries
        """
        if not namespace or not content_type:
            raise ValueError("Namespace and content_type cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT key, value FROM engineering_memory
                        WHERE namespace = ? AND content_type = ?
                        LIMIT ?
                    """, (namespace, content_type, limit))
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
                logger.error(f"Failed to get by type in {namespace}: {e}")
                raise

    async def get_namespace_stats(self, namespace: str) -> Dict[str, Any]:
        """Get statistics for a namespace.

        Args:
            namespace: Namespace to analyze

        Returns:
            Dictionary with entry count, size, and type distribution
        """
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            try:
                with sqlite3.connect(self.db_path) as conn:
                    # Total stats
                    cursor = conn.execute("""
                        SELECT COUNT(*), SUM(LENGTH(value))
                        FROM engineering_memory WHERE namespace = ?
                    """, (namespace,))
                    count, total_size = cursor.fetchone()

                    # Type distribution
                    cursor = conn.execute("""
                        SELECT content_type, COUNT(*)
                        FROM engineering_memory WHERE namespace = ?
                        GROUP BY content_type
                    """, (namespace,))
                    type_dist = dict(cursor.fetchall())

                return {
                    "namespace": namespace,
                    "entry_count": count or 0,
                    "total_size_bytes": total_size or 0,
                    "type_distribution": type_dist
                }
            except Exception as e:
                logger.error(f"Failed to get stats for {namespace}: {e}")
                raise
