"""Session Memory - Short-term memory layer with TTL and fast access.

Stores temporary session data with automatic expiration, optimized for
quick access and frequent updates during active sessions.
"""

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

from .memory_backend import MemoryBackend

logger = logging.getLogger(__name__)


class SessionMemory(MemoryBackend):
    """Short-term memory for current session data with TTL support.

    Features:
    - In-memory storage for fast access
    - Automatic TTL-based expiration
    - Namespace isolation
    - Async operations
    """

    def __init__(self, default_ttl: int = 3600):
        """Initialize SessionMemory.

        Args:
            default_ttl: Default time-to-live in seconds (default: 1 hour)
        """
        self.default_ttl = default_ttl
        self._storage: Dict[str, Dict[str, Any]] = {}
        self._expiry: Dict[str, Dict[str, float]] = {}
        self._lock = asyncio.Lock()
        logger.info(f"SessionMemory initialized with TTL={default_ttl}s")

    async def put(self, namespace: str, key: str, value: Any) -> None:
        """Store a value with TTL.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace
            value: Value to store

        Raises:
            ValueError: If namespace or key is invalid
        """
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                self._storage[namespace] = {}
                self._expiry[namespace] = {}

            self._storage[namespace][key] = value
            self._expiry[namespace][key] = time.time() + self.default_ttl
            logger.debug(f"Stored {namespace}:{key}")

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        """Retrieve a value, checking expiration.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace

        Returns:
            Stored value if found and not expired, None otherwise
        """
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                return None

            if key not in self._storage[namespace]:
                return None

            # Check expiration
            expiry_time = self._expiry[namespace].get(key, 0)
            if time.time() > expiry_time:
                del self._storage[namespace][key]
                del self._expiry[namespace][key]
                logger.debug(f"Expired {namespace}:{key}")
                return None

            return self._storage[namespace][key]

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
            List of matching entries
        """
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                return []

            results = []
            for key, value in self._storage[namespace].items():
                # Check expiration
                expiry_time = self._expiry[namespace].get(key, 0)
                if time.time() > expiry_time:
                    continue

                if query.lower() in key.lower():
                    results.append({
                        "key": key,
                        "value": value,
                        "namespace": namespace
                    })
                    if len(results) >= limit:
                        break

            return results

    async def delete(self, namespace: str, key: str) -> bool:
        """Delete a value from memory.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace

        Returns:
            True if deleted, False if not found
        """
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                return False

            if key not in self._storage[namespace]:
                return False

            del self._storage[namespace][key]
            del self._expiry[namespace][key]
            logger.debug(f"Deleted {namespace}:{key}")
            return True

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
            if namespace not in self._storage:
                return 0

            count = len(self._storage[namespace])
            del self._storage[namespace]
            del self._expiry[namespace]
            logger.info(f"Cleared {namespace}: {count} entries")
            return count

    async def exists(self, namespace: str, key: str) -> bool:
        """Check if a key exists and is not expired.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace

        Returns:
            True if key exists and not expired
        """
        if not namespace or not key:
            raise ValueError("Namespace and key cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                return False

            if key not in self._storage[namespace]:
                return False

            expiry_time = self._expiry[namespace].get(key, 0)
            if time.time() > expiry_time:
                del self._storage[namespace][key]
                del self._expiry[namespace][key]
                return False

            return True

    async def get_all(self, namespace: str) -> Dict[str, Any]:
        """Get all non-expired entries in a namespace.

        Args:
            namespace: Namespace to retrieve from

        Returns:
            Dictionary of all key-value pairs
        """
        if not namespace:
            raise ValueError("Namespace cannot be empty")

        async with self._lock:
            if namespace not in self._storage:
                return {}

            result = {}
            current_time = time.time()
            for key, value in self._storage[namespace].items():
                expiry_time = self._expiry[namespace].get(key, 0)
                if current_time <= expiry_time:
                    result[key] = value

            return result

    async def cleanup_expired(self) -> int:
        """Remove all expired entries across all namespaces.

        Returns:
            Number of entries deleted
        """
        async with self._lock:
            count = 0
            current_time = time.time()

            for namespace in list(self._storage.keys()):
                expired_keys = []
                for key, expiry_time in self._expiry[namespace].items():
                    if current_time > expiry_time:
                        expired_keys.append(key)

                for key in expired_keys:
                    del self._storage[namespace][key]
                    del self._expiry[namespace][key]
                    count += 1

            if count > 0:
                logger.info(f"Cleaned up {count} expired entries")
            return count
