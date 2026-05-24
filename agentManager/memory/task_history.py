"""Task History Memory - Medium-term memory layer for task tracking and history.

Provides task recording, status tracking, and historical analysis capabilities
integrated with the MemorySystem's MEDIUM_TERM layer (7-day TTL).
"""

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Dict, List, Optional

from .memory_system import MemoryEntry, MemoryLayer, MemorySystem


@dataclass
class TaskRecord:
    """Represents a single task record with execution metadata.

    Attributes:
        task_id: Unique identifier for the task
        session_id: Session identifier this task belongs to
        task_name: Human-readable name of the task
        status: Current status (pending, running, completed, failed)
        start_time: When the task started
        end_time: When the task ended (None if still running)
        result: Task result data (None if not completed)
        error: Error message if task failed (None if successful)
        metadata: Additional metadata dictionary for extensibility
    """
    task_id: str
    session_id: str
    task_name: str
    status: str
    start_time: datetime
    end_time: Optional[datetime] = None
    result: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert TaskRecord to dictionary for serialization.

        Returns:
            Dictionary representation of the task record
        """
        data = asdict(self)
        data['start_time'] = self.start_time.isoformat()
        data['end_time'] = self.end_time.isoformat() if self.end_time else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'TaskRecord':
        """Create TaskRecord from dictionary.

        Args:
            data: Dictionary containing task record data

        Returns:
            TaskRecord instance
        """
        data = data.copy()
        data['start_time'] = datetime.fromisoformat(data['start_time'])
        if data['end_time']:
            data['end_time'] = datetime.fromisoformat(data['end_time'])
        return cls(**data)


class TaskHistory:
    """Medium-term task history manager with MemorySystem integration.

    Tracks task execution, status changes, and provides query capabilities
    for task analysis and debugging.
    """

    def __init__(self, memory_system: MemorySystem) -> None:
        """Initialize TaskHistory with a MemorySystem instance.

        Args:
            memory_system: MemorySystem instance for persistence
        """
        self.memory_system = memory_system
        self._task_cache: Dict[str, TaskRecord] = {}

    def record_task_start(self, session_id: str, task_id: str, task_name: str) -> None:
        """Record the start of a task.

        Args:
            session_id: Session identifier
            task_id: Unique task identifier
            task_name: Human-readable task name
        """
        record = TaskRecord(
            task_id=task_id,
            session_id=session_id,
            task_name=task_name,
            status="running",
            start_time=datetime.utcnow()
        )
        self._task_cache[task_id] = record
        self._persist_task(record)

    def record_task_end(
        self,
        task_id: str,
        status: str,
        result: Optional[Dict[str, Any]] = None,
        error: Optional[str] = None
    ) -> None:
        """Record the completion of a task.

        Args:
            task_id: Unique task identifier
            status: Final status (completed, failed, etc.)
            result: Task result data if successful
            error: Error message if task failed
        """
        record = self._task_cache.get(task_id)
        if not record:
            return

        record.status = status
        record.end_time = datetime.utcnow()
        record.result = result
        record.error = error
        self._persist_task(record)

    def get_task_record(self, task_id: str) -> Optional[TaskRecord]:
        """Retrieve a task record by ID.

        Args:
            task_id: Unique task identifier

        Returns:
            TaskRecord if found, None otherwise
        """
        if task_id in self._task_cache:
            return self._task_cache[task_id]

        entry = self.memory_system.retrieve(f"task_{task_id}")
        if entry:
            record = TaskRecord.from_dict(json.loads(entry.content))
            self._task_cache[task_id] = record
            return record
        return None

    def get_session_tasks(self, session_id: str) -> List[TaskRecord]:
        """Retrieve all tasks for a session.

        Args:
            session_id: Session identifier

        Returns:
            List of TaskRecord objects for the session
        """
        entries = self.memory_system.search(
            f"session_id\": \"{session_id}",
            layer=MemoryLayer.MEDIUM_TERM
        )
        records = []
        for entry in entries:
            try:
                record = TaskRecord.from_dict(json.loads(entry.content))
                records.append(record)
            except (json.JSONDecodeError, ValueError):
                continue
        return sorted(records, key=lambda r: r.start_time)

    def get_failed_tasks(self, session_id: Optional[str] = None) -> List[TaskRecord]:
        """Retrieve all failed tasks, optionally filtered by session.

        Args:
            session_id: Optional session identifier to filter by

        Returns:
            List of failed TaskRecord objects
        """
        query = "\"status\": \"failed"
        if session_id:
            query += f"\" AND \"session_id\": \"{session_id}"

        entries = self.memory_system.search(
            query,
            layer=MemoryLayer.MEDIUM_TERM
        )
        records = []
        for entry in entries:
            try:
                record = TaskRecord.from_dict(json.loads(entry.content))
                if record.status == "failed":
                    records.append(record)
            except (json.JSONDecodeError, ValueError):
                continue
        return records

    def get_task_duration(self, task_id: str) -> Optional[float]:
        """Calculate task execution duration in seconds.

        Args:
            task_id: Unique task identifier

        Returns:
            Duration in seconds if task has ended, None otherwise
        """
        record = self.get_task_record(task_id)
        if not record or not record.end_time:
            return None
        return (record.end_time - record.start_time).total_seconds()

    def search_tasks(
        self,
        query: str,
        session_id: Optional[str] = None
    ) -> List[TaskRecord]:
        """Search tasks by query string, optionally filtered by session.

        Args:
            query: Search query string (searches task_name and metadata)
            session_id: Optional session identifier to filter by

        Returns:
            List of matching TaskRecord objects
        """
        search_query = query
        if session_id:
            search_query += f" session_id:{session_id}"

        entries = self.memory_system.search(
            search_query,
            layer=MemoryLayer.MEDIUM_TERM
        )
        records = []
        for entry in entries:
            try:
                record = TaskRecord.from_dict(json.loads(entry.content))
                records.append(record)
            except (json.JSONDecodeError, ValueError):
                continue
        return records

    def _persist_task(self, record: TaskRecord) -> None:
        """Persist a task record to memory system.

        Args:
            record: TaskRecord to persist
        """
        entry = MemoryEntry(
            entry_id=f"task_{record.task_id}",
            content=json.dumps(record.to_dict()),
            layer=MemoryLayer.MEDIUM_TERM,
            tags=["task", record.status, record.session_id],
            metadata={
                "task_id": record.task_id,
                "session_id": record.session_id,
                "task_name": record.task_name,
                "status": record.status
            }
        )
        self.memory_system.store(entry)
