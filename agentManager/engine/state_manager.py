"""State Machine for task lifecycle management.

This module manages task state transitions and ensures valid state flows.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional
from datetime import datetime, timezone
import logging

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class TaskState(str, Enum):
    """Task execution states."""
    PENDING = "pending"
    READY = "ready"
    IMPLEMENTING = "implementing"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED_REPAIR = "blocked_repair"
    BLOCKED_HITL = "blocked_hitl"


@dataclass
class StateTransition:
    """Record of a state transition."""
    task_id: str
    from_state: TaskState
    to_state: TaskState
    timestamp: datetime = field(default_factory=utc_now)
    reason: str = ""


class StateMachine:
    """Manages task state transitions."""

    # Valid state transitions
    VALID_TRANSITIONS = {
        TaskState.PENDING: [
            TaskState.READY,
            TaskState.IMPLEMENTING,  # Allow direct transition for testing
            TaskState.BLOCKED_REPAIR,
            TaskState.FAILED,
        ],
        TaskState.READY: [
            TaskState.IMPLEMENTING,
            TaskState.BLOCKED_REPAIR,
            TaskState.FAILED,
        ],
        TaskState.IMPLEMENTING: [
            TaskState.VERIFYING,
            TaskState.FAILED,
            TaskState.BLOCKED_REPAIR,
        ],
        TaskState.VERIFYING: [
            TaskState.COMPLETED,
            TaskState.FAILED,
            TaskState.BLOCKED_REPAIR,
        ],
        TaskState.COMPLETED: [],  # Terminal state
        TaskState.FAILED: [
            TaskState.BLOCKED_REPAIR,
            TaskState.BLOCKED_HITL,
        ],
        TaskState.BLOCKED_REPAIR: [
            TaskState.IMPLEMENTING,
            TaskState.BLOCKED_HITL,
            TaskState.FAILED,
        ],
        TaskState.BLOCKED_HITL: [],  # Terminal state
    }

    def __init__(self, repository: Optional[Any] = None):
        """Initialize state machine."""
        self.repository = repository
        self.states: Dict[str, TaskState] = {}
        self.history: Dict[str, List[StateTransition]] = {}

    def initialize(self, task_id: str, initial_state: TaskState = TaskState.PENDING) -> None:
        """Initialize task state.

        Args:
            task_id: Task ID
            initial_state: Initial state (default: PENDING)
        """
        if task_id in self.states:
            raise ValueError(f"Task {task_id} already initialized")

        self.states[task_id] = initial_state
        self.history[task_id] = []
        if self.repository is not None:
            self.repository.save_task_state(task_id, initial_state)
            self.repository.append_audit_record(
                self._audit_record(
                    "task_state_initialized",
                    task_id,
                    {"state": initial_state.value},
                )
            )
        logger.info(f"Initialized task {task_id} with state {initial_state.value}")

    def transition(
        self,
        task_id: str,
        new_state: TaskState,
        reason: str = "",
    ) -> None:
        """Transition task to new state.

        Args:
            task_id: Task ID
            new_state: Target state
            reason: Reason for transition

        Raises:
            ValueError: If task not initialized or transition invalid
        """
        if task_id not in self.states:
            self.get_state(task_id)

        if task_id not in self.states:
            raise ValueError(f"Task {task_id} not initialized")
        if task_id not in self.history:
            self.history[task_id] = self.get_history(task_id)

        current_state = self.states[task_id]

        # Allow emergency transitions from any non-terminal state
        emergency_transition = (
            new_state in [TaskState.BLOCKED_HITL, TaskState.COMPLETED, TaskState.FAILED]
            and current_state not in [TaskState.COMPLETED, TaskState.BLOCKED_HITL]
        )

        # Check if transition is valid
        if not emergency_transition:
            valid_next_states = self.VALID_TRANSITIONS.get(current_state, [])
            if new_state not in valid_next_states:
                raise ValueError(
                    f"Invalid transition: {current_state.value} → {new_state.value}"
                )

        # Record transition
        transition = StateTransition(
            task_id=task_id,
            from_state=current_state,
            to_state=new_state,
            reason=reason,
        )
        self.history[task_id].append(transition)
        self.states[task_id] = new_state
        if self.repository is not None:
            self.repository.save_task_state(task_id, new_state)
            self.repository.save_transition(transition)
            self.repository.append_audit_record(
                self._audit_record(
                    "task_state_transitioned",
                    task_id,
                    {
                        "from_state": current_state.value,
                        "to_state": new_state.value,
                        "reason": reason,
                    },
                )
            )

        log_msg = f"Transitioned {task_id}: {current_state.value} → {new_state.value}"
        if reason:
            log_msg += f" ({reason})"
        logger.info(log_msg)

    def get_state(self, task_id: str) -> Optional[TaskState]:
        """Get current state of task.

        Args:
            task_id: Task ID

        Returns:
            Current TaskState or None if not initialized
        """
        state = self.states.get(task_id)
        if state is not None or self.repository is None:
            return state

        state = self.repository.load_task_state(task_id)
        if state is not None:
            self.states[task_id] = state
        return state

    def get_history(self, task_id: str) -> List[StateTransition]:
        """Get state transition history.

        Args:
            task_id: Task ID

        Returns:
            List of state transitions
        """
        history = self.history.get(task_id)
        if history is not None and history:
            return history
        if self.repository is None:
            return history or []

        persisted_history = self.repository.load_transitions(task_id)
        if persisted_history:
            self.history[task_id] = persisted_history
        return persisted_history

    def is_terminal(self, task_id: str) -> bool:
        """Check if task is in terminal state.

        Args:
            task_id: Task ID

        Returns:
            True if in COMPLETED or BLOCKED_HITL state
        """
        state = self.get_state(task_id)
        return state in [TaskState.COMPLETED, TaskState.BLOCKED_HITL]

    def is_failed(self, task_id: str) -> bool:
        """Check if task is in failed state.

        Args:
            task_id: Task ID

        Returns:
            True if in FAILED or BLOCKED_REPAIR state
        """
        state = self.get_state(task_id)
        return state in [TaskState.FAILED, TaskState.BLOCKED_REPAIR]

    def _audit_record(self, action: str, entity_id: str, payload: dict[str, str]) -> Any:
        """Create an audit record without requiring storage imports by default."""
        from agentManager.storage import AuditRecord

        return AuditRecord(action=action, entity_id=entity_id, payload=payload)
