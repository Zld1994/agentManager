"""Priority queue utilities for scheduler task ordering."""

import heapq
from dataclasses import dataclass, field
from itertools import count
from typing import Any, List, Tuple


@dataclass
class PriorityQueue:
    """Stable max-priority queue."""

    _items: List[Tuple[int, int, Any]] = field(default_factory=list)
    _counter: count = field(default_factory=count)

    def push(self, item: Any, priority: int = 0) -> None:
        """Push an item where higher priority values are returned first."""
        heapq.heappush(self._items, (-priority, next(self._counter), item))

    def pop(self) -> Any:
        """Pop the highest-priority item."""
        if not self._items:
            raise IndexError("pop from empty priority queue")
        return heapq.heappop(self._items)[2]

    def peek(self) -> Any:
        """Return the highest-priority item without removing it."""
        if not self._items:
            raise IndexError("peek from empty priority queue")
        return self._items[0][2]

    def __len__(self) -> int:
        return len(self._items)

    def is_empty(self) -> bool:
        """Return whether the queue is empty."""
        return not self._items
