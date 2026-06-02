"""Profile memory layer with in-process TTL storage."""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .memory_backend import MemoryBackend

logger = logging.getLogger(__name__)


class ProfileMemory(MemoryBackend):
    """Short-term profile/session memory with TTL-based expiration."""

    def __init__(self, default_ttl: int = 3600):
        self.default_ttl = default_ttl
        self._storage: Dict[str, Dict[str, Any]] = {}
        self._expiry: Dict[str, Dict[str, float]] = {}
        self._lock = asyncio.Lock()
        logger.info("ProfileMemory initialized with TTL=%ss", default_ttl)

    async def put(self, namespace: str, key: str, value: Any) -> None:
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                self._storage[namespace] = {}
                self._expiry[namespace] = {}

            self._storage[namespace][key] = value
            self._expiry[namespace][key] = time.time() + self.default_ttl

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            if namespace not in self._storage or key not in self._storage[namespace]:
                return None

            if time.time() > self._expiry[namespace].get(key, 0):
                del self._storage[namespace][key]
                del self._expiry[namespace][key]
                return None
            return self._storage[namespace][key]

    async def search(self, namespace: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                return []

            results: List[Dict[str, Any]] = []
            current_time = time.time()
            for key, value in self._storage[namespace].items():
                if current_time > self._expiry[namespace].get(key, 0):
                    continue
                if query.lower() in key.lower():
                    results.append({"key": key, "value": value, "namespace": namespace})
                    if len(results) >= limit:
                        break
            return results

    async def delete(self, namespace: str, key: str) -> bool:
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            if namespace not in self._storage or key not in self._storage[namespace]:
                return False
            del self._storage[namespace][key]
            del self._expiry[namespace][key]
            return True

    async def clear(self, namespace: str) -> int:
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                return 0
            count = len(self._storage[namespace])
            del self._storage[namespace]
            del self._expiry[namespace]
            return count

    async def exists(self, namespace: str, key: str) -> bool:
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            if namespace not in self._storage or key not in self._storage[namespace]:
                return False
            if time.time() > self._expiry[namespace].get(key, 0):
                del self._storage[namespace][key]
                del self._expiry[namespace][key]
                return False
            return True

    async def get_all(self, namespace: str) -> Dict[str, Any]:
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                return {}

            current_time = time.time()
            return {
                key: value
                for key, value in self._storage[namespace].items()
                if current_time <= self._expiry[namespace].get(key, 0)
            }

    async def cleanup_expired(self) -> int:
        async with self._lock:
            count = 0
            current_time = time.time()
            for namespace in list(self._storage.keys()):
                expired_keys = [
                    key for key, expiry in self._expiry[namespace].items() if current_time > expiry
                ]
                for key in expired_keys:
                    del self._storage[namespace][key]
                    del self._expiry[namespace][key]
                    count += 1
            return count
