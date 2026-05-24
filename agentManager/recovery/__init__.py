"""Recovery module for task recovery operations.

This module provides recovery capabilities for failed tasks, including:
- Error classification and failure type detection
- Multiple recovery strategies (RETRY, EVENT_REPLAY, SNAPSHOT_RESTORE, HITL, ESCALATE)
- Recovery context management
- Recovery engine orchestration
"""

from agentManager.recovery.recovery_context import (
    RecoveryContext,
    FailureType,
    RecoveryStrategy,
)
from agentManager.recovery.error_classifier import ErrorClassifier
from agentManager.recovery.recovery_engine import RecoveryEngine

__all__ = [
    "RecoveryContext",
    "FailureType",
    "RecoveryStrategy",
    "ErrorClassifier",
    "RecoveryEngine",
]
