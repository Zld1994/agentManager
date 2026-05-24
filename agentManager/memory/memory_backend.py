"""Memory Backend Interface - Abstract base for memory implementations.

Defines the core interface for memory operations with namespace isolation,
supporting put, get, search, delete, and clear operations.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class MemoryBackend(ABC):
    """Abstract base class for memory backend implementations.

    Provides interface for storing, retrieving, searching, and managing
    memory entries with namespace isolation.
    """

    @abstractmethod
    async def put(self, namespace: str, key: str, value: Any) -> None:
        """Store a value in memory.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace
            value: Value to store (should be serializable)

        Raises:
            ValueError: If namespace or key is invalid
            Exception: If storage operation fails
        """
        pass

    @abstractmethod
    async def get(self, namespace: str, key: str) -> Optional[Any]:
        """Retrieve a value from memory.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace

        Returns:
            Stored value if found, None otherwise

        Raises:
            ValueError: If namespace or key is invalid
        """
        pass

    @abstractmethod
    async def search(
        self,
        namespace: str,
        query: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search for values in a namespace.

        Args:
            namespace: Namespace to search in
            query: Search query string
            limit: Maximum number of results to return

        Returns:
            List of matching entries with metadata

        Raises:
            ValueError: If namespace is invalid
        """
        pass

    @abstractmethod
    async def delete(self, namespace: str, key: str) -> bool:
        """Delete a value from memory.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace

        Returns:
            True if deleted, False if not found

        Raises:
            ValueError: If namespace or key is invalid
        """
        pass

    @abstractmethod
    async def clear(self, namespace: str) -> int:
        """Clear all entries in a namespace.

        Args:
            namespace: Namespace to clear

        Returns:
            Number of entries deleted

        Raises:
            ValueError: If namespace is invalid
        """
        pass

    @abstractmethod
    async def exists(self, namespace: str, key: str) -> bool:
        """Check if a key exists in namespace.

        Args:
            namespace: Namespace for isolation
            key: Unique key within namespace

        Returns:
            True if key exists, False otherwise
        """
        pass

    @abstractmethod
    async def get_all(self, namespace: str) -> Dict[str, Any]:
        """Get all entries in a namespace.

        Args:
            namespace: Namespace to retrieve from

        Returns:
            Dictionary of all key-value pairs in namespace
        """
        pass
