"""Execution context for task execution tracking.

This module defines the ExecutionContext data class that tracks the state
and metadata of a task execution throughout its lifecycle.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, Optional
from enum import Enum


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class ExecutionStatus(str, Enum):
    """Execution status enumeration."""
    PENDING = "pending"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class ExecutionContext:
    """Tracks execution context for a task.

    Attributes:
        task_id: Unique identifier for the task
        workflow_id: Identifier for the parent workflow
        status: Current execution status
        start_time: When execution started
        end_time: When execution ended
        result: Execution result data
        error: Error information if execution failed
        retry_count: Number of retry attempts
        metadata: Additional execution metadata
    """
    task_id: str
    workflow_id: str
    status: ExecutionStatus = ExecutionStatus.PENDING
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    result: Dict[str, Any] = field(default_factory=dict)
    error: Optional[str] = None
    retry_count: int = 0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def mark_started(self) -> None:
        """Mark execution as started."""
        self.start_time = utc_now()
        self.status = ExecutionStatus.IMPLEMENTING

    def mark_verifying(self) -> None:
        """Mark execution as verifying."""
        self.status = ExecutionStatus.VERIFYING

    def mark_completed(self, result: Dict[str, Any]) -> None:
        """Mark execution as completed.

        Args:
            result: Execution result data
        """
        self.end_time = utc_now()
        self.status = ExecutionStatus.COMPLETED
        self.result = result

    def mark_failed(self, error: str) -> None:
        """Mark execution as failed.

        Args:
            error: Error message
        """
        self.end_time = utc_now()
        self.status = ExecutionStatus.FAILED
        self.error = error

    def increment_retry(self) -> None:
        """Increment retry counter."""
        self.retry_count += 1

    def get_duration(self) -> Optional[float]:
        """Get execution duration in seconds.

        Returns:
            Duration in seconds or None if not completed
        """
        if self.start_time is None:
            return None

        end = self.end_time or utc_now()
        return (end - self.start_time).total_seconds()

    def to_dict(self) -> Dict[str, Any]:
        """Convert context to dictionary.

        Returns:
            Dictionary representation of context
        """
        return {
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "status": self.status.value,
            "start_time": self.start_time.isoformat() if self.start_time else None,
            "end_time": self.end_time.isoformat() if self.end_time else None,
            "result": self.result,
            "error": self.error,
            "retry_count": self.retry_count,
            "metadata": self.metadata,
            "duration": self.get_duration(),
        }
