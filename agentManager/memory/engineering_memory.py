"""Engineering memory layer with pluggable vector search backend."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional

from .memory_backend import MemoryBackend
from agentManager.config.settings import get_durable_backend_settings

from .vector_backend import SQLiteVectorSearchBackend, VectorSearchBackend, create_vector_backend

logger = logging.getLogger(__name__)


def _extract_search_text(value: Any) -> str:
    """Build index text from stored value."""
    if isinstance(value, dict):
        content = value.get("content", "")
        tags = value.get("tags", [])
        tag_text = " ".join(str(tag) for tag in tags)
        return f"{content} {tag_text}".strip()
    return str(value)


class EngineeringMemory(MemoryBackend):
    """Long-term engineering memory with SQLite persistence and vector search."""

    def __init__(
        self,
        db_path: str = "engineering_memory.db",
        vector_backend: Optional[VectorSearchBackend] = None,
    ):
        self.db_path = Path(db_path)
        self._lock = asyncio.Lock()
        self.vector_backend = vector_backend or SQLiteVectorSearchBackend(db_path=str(self.db_path))
        self._init_db()
        logger.info("EngineeringMemory initialized with db=%s", db_path)

    @classmethod
    def from_settings(cls, db_path: str = "engineering_memory.db") -> "EngineeringMemory":
        """Create engineering memory from durable backend environment settings."""
        settings = get_durable_backend_settings()
        vector_backend = create_vector_backend(
            settings["vector_backend"],
            db_path=db_path,
            url=os.getenv("QDRANT_URL", "http://localhost:6333"),
            collection_name=os.getenv("QDRANT_COLLECTION", "agentmanager_memory"),
            api_key=os.getenv("QDRANT_API_KEY") or None,
        )
        return cls(db_path=db_path, vector_backend=vector_backend)

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
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
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_namespace
                ON engineering_memory(namespace)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_content_type
                ON engineering_memory(content_type)
                """
            )
            conn.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_created_at
                ON engineering_memory(created_at)
                """
            )
            conn.commit()

    async def put(self, namespace: str, key: str, value: Any) -> None:
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            import time

            current_time = time.time()
            content_type = value.get("type", "general") if isinstance(value, dict) else "general"
            tags = value.get("tags", []) if isinstance(value, dict) else []
            value_json = json.dumps(value)
            tags_json = json.dumps(tags)

            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    """
                    INSERT OR REPLACE INTO engineering_memory
                    (namespace, key, value, content_type, created_at, updated_at, tags, metadata)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        namespace,
                        key,
                        value_json,
                        content_type,
                        current_time,
                        current_time,
                        tags_json,
                        None,
                    ),
                )
                conn.commit()

        await self.vector_backend.upsert(namespace, key, _extract_search_text(value))

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT value FROM engineering_memory
                    WHERE namespace = ? AND key = ?
                    """,
                    (namespace, key),
                )
                row = cursor.fetchone()
        if not row:
            return None
        return json.loads(row[0])

    async def search(self, namespace: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        vector_results = await self.vector_backend.query(namespace, query, limit=limit)
        if vector_results:
            return await self._hydrate_vector_results(namespace, vector_results)

        # Fallback keyword search against stored payload text if vector backend returns nothing.
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT key, value
                    FROM engineering_memory
                    WHERE namespace = ? AND value LIKE ?
                    LIMIT ?
                    """,
                    (namespace, f"%{query}%", limit),
                )
                rows = cursor.fetchall()

        return [
            {
                "key": key,
                "value": json.loads(value),
                "namespace": namespace,
                "similarity": 1.0,
            }
            for key, value in rows
        ]

    async def _hydrate_vector_results(self, namespace: str, vector_results) -> List[Dict[str, Any]]:
        results: List[Dict[str, Any]] = []
        for result in vector_results:
            value = await self.get(namespace, result.key)
            if value is None:
                continue
            results.append(
                {
                    "key": result.key,
                    "value": value,
                    "namespace": namespace,
                    "similarity": result.score,
                }
            )
        return results

    async def delete(self, namespace: str, key: str) -> bool:
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    DELETE FROM engineering_memory
                    WHERE namespace = ? AND key = ?
                    """,
                    (namespace, key),
                )
                conn.commit()
                deleted = cursor.rowcount > 0

        await self.vector_backend.remove(namespace, key)
        return deleted

    async def clear(self, namespace: str) -> int:
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "DELETE FROM engineering_memory WHERE namespace = ?",
                    (namespace,),
                )
                conn.commit()
                count = cursor.rowcount

        await self.vector_backend.clear(namespace)
        return count

    async def exists(self, namespace: str, key: str) -> bool:
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT 1 FROM engineering_memory
                    WHERE namespace = ? AND key = ?
                    """,
                    (namespace, key),
                )
                return cursor.fetchone() is not None

    async def get_all(self, namespace: str) -> Dict[str, Any]:
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT key, value FROM engineering_memory
                    WHERE namespace = ?
                    """,
                    (namespace,),
                )
                rows = cursor.fetchall()

        return {key: json.loads(value) for key, value in rows}

    async def get_by_type(
        self,
        namespace: str,
        content_type: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        if not namespace or not content_type:
            raise ValueError("Namespace and content_type cannot be empty")

        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT key, value FROM engineering_memory
                    WHERE namespace = ? AND content_type = ?
                    LIMIT ?
                    """,
                    (namespace, content_type, limit),
                )
                rows = cursor.fetchall()

        return [
            {
                "key": key,
                "value": json.loads(value),
                "namespace": namespace,
            }
            for key, value in rows
        ]

    async def get_namespace_stats(self, namespace: str) -> Dict[str, Any]:
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    """
                    SELECT COUNT(*), SUM(LENGTH(value))
                    FROM engineering_memory WHERE namespace = ?
                    """,
                    (namespace,),
                )
                count, total_size = cursor.fetchone()

                cursor = conn.execute(
                    """
                    SELECT content_type, COUNT(*)
                    FROM engineering_memory WHERE namespace = ?
                    GROUP BY content_type
                    """,
                    (namespace,),
                )
                type_dist = dict(cursor.fetchall())

        return {
            "namespace": namespace,
            "entry_count": count or 0,
            "total_size_bytes": total_size or 0,
            "type_distribution": type_dist,
        }
