"""Recovery context for task recovery operations.

This module defines the RecoveryContext data class that encapsulates
all information needed for task recovery.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
from datetime import datetime, timezone


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class FailureType(str, Enum):
    """Types of failures that can occur during task execution."""

    TIMEOUT = "timeout"
    NETWORK = "network"
    SYNTAX = "syntax"
    RUNTIME = "runtime"
    UNKNOWN = "unknown"


class RecoveryStrategy(str, Enum):
    """Recovery strategies available for task recovery."""

    RETRY = "retry"
    EVENT_REPLAY = "event_replay"
    SNAPSHOT_RESTORE = "snapshot_restore"
    DEFECT_REPAIR = "defect_repair"
    HITL = "hitl"  # Human-In-The-Loop
    ESCALATE = "escalate"


@dataclass
class RecoveryContext:
    """Context information for task recovery.

    Encapsulates all information needed to recover a failed task,
    including failure details, checkpoint information, and recovery strategy.
    """

    task_id: str
    workflow_id: str
    failure_type: FailureType
    error_msg: str
    checkpoint_id: Optional[str] = None
    event_id: Optional[str] = None
    retry_count: int = 0
    recovery_strategy: Optional[RecoveryStrategy] = None
    timestamp: datetime = field(default_factory=utc_now)

    def __post_init__(self):
        """Validate recovery context after initialization."""
        if not self.task_id:
            raise ValueError("task_id is required")
        if not self.workflow_id:
            raise ValueError("workflow_id is required")
        if not self.error_msg:
            raise ValueError("error_msg is required")

    def to_dict(self) -> dict:
        """Convert recovery context to dictionary.

        Returns:
            Dictionary representation of recovery context
        """
        return {
            "task_id": self.task_id,
            "workflow_id": self.workflow_id,
            "failure_type": self.failure_type.value,
            "error_msg": self.error_msg,
            "checkpoint_id": self.checkpoint_id,
            "event_id": self.event_id,
            "retry_count": self.retry_count,
            "recovery_strategy": (self.recovery_strategy.value if self.recovery_strategy else None),
            "timestamp": self.timestamp.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RecoveryContext":
        """Create recovery context from dictionary.

        Args:
            data: Dictionary containing recovery context data

        Returns:
            RecoveryContext instance
        """
        timestamp = data.get("timestamp", utc_now())
        if isinstance(timestamp, str):
            timestamp = datetime.fromisoformat(timestamp)

        return cls(
            task_id=data["task_id"],
            workflow_id=data["workflow_id"],
            failure_type=FailureType(data["failure_type"]),
            error_msg=data["error_msg"],
            checkpoint_id=data.get("checkpoint_id"),
            event_id=data.get("event_id"),
            retry_count=data.get("retry_count", 0),
            recovery_strategy=(
                RecoveryStrategy(data["recovery_strategy"])
                if data.get("recovery_strategy")
                else None
            ),
            timestamp=timestamp,
        )
