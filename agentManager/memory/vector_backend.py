"""Vector search backend interfaces and fallback implementations."""

from __future__ import annotations

import asyncio
import json
import re
import sqlite3
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Set


def _tokenize(text: str) -> Set[str]:
    return set(re.findall(r"\w+", text.lower()))


def _jaccard_score(a: Set[str], b: Set[str]) -> float:
    if not a and not b:
        return 0.0
    union = a | b
    if not union:
        return 0.0
    return len(a & b) / len(union)


@dataclass(frozen=True)
class VectorSearchResult:
    """Single vector search match."""

    key: str
    score: float


class VectorSearchBackend(ABC):
    """Pluggable vector backend API used by engineering memory."""

    @abstractmethod
    async def upsert(self, namespace: str, key: str, text: str) -> None:
        """Create or update vector index data for the key."""

    @abstractmethod
    async def remove(self, namespace: str, key: str) -> bool:
        """Delete indexed vector data for the key."""

    @abstractmethod
    async def query(self, namespace: str, query_text: str, limit: int = 10) -> List[VectorSearchResult]:
        """Return ranked search results for a namespace."""

    @abstractmethod
    async def clear(self, namespace: str) -> int:
        """Delete all vector index entries for a namespace."""


class InMemoryVectorSearchBackend(VectorSearchBackend):
    """In-process vector index for tests and local prototype usage."""

    def __init__(self) -> None:
        self._index: Dict[str, Dict[str, Set[str]]] = {}
        self._lock = asyncio.Lock()

    async def upsert(self, namespace: str, key: str, text: str) -> None:
        async with self._lock:
            if namespace not in self._index:
                self._index[namespace] = {}
            self._index[namespace][key] = _tokenize(text)

    async def remove(self, namespace: str, key: str) -> bool:
        async with self._lock:
            namespace_index = self._index.get(namespace)
            if not namespace_index or key not in namespace_index:
                return False
            del namespace_index[key]
            return True

    async def query(self, namespace: str, query_text: str, limit: int = 10) -> List[VectorSearchResult]:
        async with self._lock:
            namespace_index = self._index.get(namespace, {})
            if not namespace_index:
                return []
            query_tokens = _tokenize(query_text)
            results = [
                VectorSearchResult(key=key, score=_jaccard_score(tokens, query_tokens))
                for key, tokens in namespace_index.items()
            ]
        filtered = [result for result in results if result.score > 0]
        filtered.sort(key=lambda item: item.score, reverse=True)
        return filtered[:limit]

    async def clear(self, namespace: str) -> int:
        async with self._lock:
            namespace_index = self._index.get(namespace)
            if not namespace_index:
                return 0
            count = len(namespace_index)
            del self._index[namespace]
            return count


class SQLiteVectorSearchBackend(VectorSearchBackend):
    """SQLite-backed vector index used as default persistent fallback."""

    def __init__(self, db_path: str, table_name: str = "memory_vectors") -> None:
        self.db_path = Path(db_path)
        self.table_name = table_name
        self._lock = asyncio.Lock()
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                f"""
                CREATE TABLE IF NOT EXISTS {self.table_name} (
                    namespace TEXT NOT NULL,
                    key TEXT NOT NULL,
                    tokens TEXT NOT NULL,
                    PRIMARY KEY (namespace, key)
                )
                """
            )
            conn.execute(
                f"""
                CREATE INDEX IF NOT EXISTS idx_{self.table_name}_namespace
                ON {self.table_name}(namespace)
                """
            )
            conn.commit()

    async def upsert(self, namespace: str, key: str, text: str) -> None:
        tokens_json = json.dumps(sorted(_tokenize(text)))
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    f"""
                    INSERT OR REPLACE INTO {self.table_name}
                    (namespace, key, tokens) VALUES (?, ?, ?)
                    """,
                    (namespace, key, tokens_json),
                )
                conn.commit()

    async def remove(self, namespace: str, key: str) -> bool:
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    f"DELETE FROM {self.table_name} WHERE namespace = ? AND key = ?",
                    (namespace, key),
                )
                conn.commit()
                return cursor.rowcount > 0

    async def query(self, namespace: str, query_text: str, limit: int = 10) -> List[VectorSearchResult]:
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    f"SELECT key, tokens FROM {self.table_name} WHERE namespace = ?",
                    (namespace,),
                )
                rows = cursor.fetchall()

        query_tokens = _tokenize(query_text)
        results: List[VectorSearchResult] = []
        for key, tokens_json in rows:
            tokens = set(json.loads(tokens_json))
            score = _jaccard_score(tokens, query_tokens)
            if score > 0:
                results.append(VectorSearchResult(key=key, score=score))

        results.sort(key=lambda item: item.score, reverse=True)
        return results[:limit]

    async def clear(self, namespace: str) -> int:
        async with self._lock:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    f"DELETE FROM {self.table_name} WHERE namespace = ?",
                    (namespace,),
                )
                conn.commit()
                return cursor.rowcount
