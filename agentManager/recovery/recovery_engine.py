"""Recovery engine for task recovery operations.

This module implements the RecoveryEngine class that orchestrates
task recovery using various strategies based on failure types.
"""

import logging
from typing import Dict, Optional
from datetime import datetime, timezone

from agentManager.recovery.recovery_context import (
    RecoveryContext,
    FailureType,
    RecoveryStrategy,
)
from agentManager.recovery.error_classifier import ErrorClassifier
from agentManager.runtime.task_executor import TaskExecutor, CheckpointManager
from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType
from agentManager.engine.state_manager import StateMachine, TaskState

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


class RecoveryEngine:
    """Orchestrates task recovery using multiple strategies.

    Manages the recovery process for failed tasks, selecting appropriate
    recovery strategies based on failure types and executing recovery operations.
    """

    # Maximum retry attempts for RETRY strategy
    MAX_RETRY_ATTEMPTS = 3

    # Recovery strategy timeout (seconds)
    RECOVERY_TIMEOUT = 300

    def __init__(
        self,
        task_executor: TaskExecutor,
        event_bus: BaseEventBus,
        state_machine: StateMachine,
        checkpoint_manager: CheckpointManager,
    ):
        """Initialize RecoveryEngine.

        Args:
            task_executor: Task executor for running tasks
            event_bus: Event bus for publishing recovery events
            state_machine: State machine for state management
            checkpoint_manager: Manager for checkpoints
        """
        self.task_executor = task_executor
        self.event_bus = event_bus
        self.state_machine = state_machine
        self.checkpoint_manager = checkpoint_manager
        self.error_classifier = ErrorClassifier()

        # Recovery history tracking
        self.recovery_history: Dict[str, list] = {}

        logger.info("RecoveryEngine initialized")

    async def execute_recovery(self, ctx: RecoveryContext) -> bool:
        """Execute recovery for a failed task.

        Args:
            ctx: Recovery context containing failure information

        Returns:
            True if recovery succeeded, False otherwise

        Raises:
            ValueError: If recovery context is invalid
        """
        if not ctx:
            raise ValueError("Recovery context is required")

        task_id = ctx.task_id
        workflow_id = ctx.workflow_id

        logger.info(
            f"Starting recovery for task {task_id} in workflow {workflow_id} "
            f"with strategy {ctx.recovery_strategy}"
        )

        # Track recovery attempt
        self._track_recovery_attempt(ctx)

        try:
            # Select strategy if not already set
            if not ctx.recovery_strategy:
                ctx.recovery_strategy = self.select_recovery_strategy(
                    ctx.failure_type
                )
                logger.info(
                    f"Selected recovery strategy {ctx.recovery_strategy.value} "
                    f"for failure type {ctx.failure_type.value}"
                )

            # Execute recovery based on strategy
            if ctx.recovery_strategy == RecoveryStrategy.RETRY:
                success = await self._execute_retry(ctx)
            elif ctx.recovery_strategy == RecoveryStrategy.EVENT_REPLAY:
                success = await self._execute_event_replay(ctx)
            elif ctx.recovery_strategy == RecoveryStrategy.SNAPSHOT_RESTORE:
                success = await self._execute_snapshot_restore(ctx)
            elif ctx.recovery_strategy == RecoveryStrategy.HITL:
                success = await self._execute_hitl(ctx)
            elif ctx.recovery_strategy == RecoveryStrategy.ESCALATE:
                success = await self._execute_escalate(ctx)
            else:
                logger.error(
                    f"Unknown recovery strategy: {ctx.recovery_strategy}"
                )
                success = False

            # Publish recovery result event
            await self._publish_recovery_event(ctx, success)

            if success:
                logger.info(
                    f"Recovery succeeded for task {task_id} "
                    f"using strategy {ctx.recovery_strategy.value}"
                )
                # Only transition to READY for strategies that support retry
                # HITL and ESCALATE already transition to BLOCKED_HITL
                if ctx.recovery_strategy not in [
                    RecoveryStrategy.HITL,
                    RecoveryStrategy.ESCALATE,
                ]:
                    self.state_machine.transition(
                        task_id,
                        TaskState.READY,
                        f"Recovery succeeded with {ctx.recovery_strategy.value}",
                    )
            else:
                logger.warning(
                    f"Recovery failed for task {task_id} "
                    f"using strategy {ctx.recovery_strategy.value}"
                )
                # Transition to BLOCKED_HITL for manual intervention
                self.state_machine.transition(
                    task_id,
                    TaskState.BLOCKED_HITL,
                    f"Recovery failed with {ctx.recovery_strategy.value}",
                )

            return success

        except Exception as e:
            logger.error(f"Recovery execution failed: {str(e)}", exc_info=True)
            await self._publish_recovery_event(ctx, False, str(e))
            return False

    def select_recovery_strategy(
        self, failure_type: FailureType
    ) -> RecoveryStrategy:
        """Select recovery strategy based on failure type.

        Args:
            failure_type: Type of failure

        Returns:
            Recommended recovery strategy
        """
        strategy_map = {
            FailureType.TIMEOUT: RecoveryStrategy.RETRY,
            FailureType.NETWORK: RecoveryStrategy.EVENT_REPLAY,
            FailureType.SYNTAX: RecoveryStrategy.HITL,
            FailureType.RUNTIME: RecoveryStrategy.SNAPSHOT_RESTORE,
            FailureType.UNKNOWN: RecoveryStrategy.ESCALATE,
        }

        strategy = strategy_map.get(failure_type, RecoveryStrategy.ESCALATE)
        logger.info(
            f"Selected strategy {strategy.value} "
            f"for failure type {failure_type.value}"
        )
        return strategy

    async def _execute_retry(self, ctx: RecoveryContext) -> bool:
        """Execute RETRY recovery strategy.

        Retries the task up to MAX_RETRY_ATTEMPTS times.

        Args:
            ctx: Recovery context

        Returns:
            True if retry succeeded
        """
        task_id = ctx.task_id
        logger.info(f"Executing RETRY strategy for task {task_id}")

        if ctx.retry_count >= self.MAX_RETRY_ATTEMPTS:
            logger.warning(
                f"Task {task_id} has exceeded maximum retry attempts "
                f"({ctx.retry_count}/{self.MAX_RETRY_ATTEMPTS})"
            )
            return False

        try:
            # Get execution context
            exec_ctx = self.task_executor.get_execution_context(task_id)
            if not exec_ctx:
                logger.error(f"No execution context found for task {task_id}")
                return False

            # Increment retry count
            ctx.retry_count += 1
            logger.info(
                f"Retrying task {task_id} "
                f"(attempt {ctx.retry_count}/{self.MAX_RETRY_ATTEMPTS})"
            )

            # Note: Actual task re-execution would be handled by TaskExecutor
            # This marks the task as ready for retry
            return True

        except Exception as e:
            logger.error(f"RETRY strategy failed: {str(e)}", exc_info=True)
            return False

    async def _execute_event_replay(self, ctx: RecoveryContext) -> bool:
        """Execute EVENT_REPLAY recovery strategy.

        Replays events from checkpoint to recover task state.

        Args:
            ctx: Recovery context

        Returns:
            True if event replay succeeded
        """
        task_id = ctx.task_id
        workflow_id = ctx.workflow_id
        logger.info(f"Executing EVENT_REPLAY strategy for task {task_id}")

        try:
            if not ctx.event_id:
                logger.warning(
                    "No event_id provided for EVENT_REPLAY recovery"
                )
                return False

            # Get events from event bus
            events = await self.event_bus.get_events(workflow_id=workflow_id)

            if not events:
                logger.warning(f"No events found for workflow {workflow_id}")
                return False

            # Find the event to replay from
            replay_events = [e for e in events if e.event_id == ctx.event_id]

            if not replay_events:
                logger.warning(
                    f"Event {ctx.event_id} not found in event bus"
                )
                return False

            logger.info(
                f"Found {len(replay_events)} events to replay for task {task_id}"
            )

            # Replay events (in real implementation, would process each event)
            for event in replay_events:
                logger.debug(f"Replaying event: {event.event_type.value}")

            return True

        except Exception as e:
            logger.error(f"EVENT_REPLAY strategy failed: {str(e)}", exc_info=True)
            return False

    async def _execute_snapshot_restore(self, ctx: RecoveryContext) -> bool:
        """Execute SNAPSHOT_RESTORE recovery strategy.

        Restores task state from checkpoint snapshot.

        Args:
            ctx: Recovery context

        Returns:
            True if snapshot restore succeeded
        """
        task_id = ctx.task_id
        logger.info(f"Executing SNAPSHOT_RESTORE strategy for task {task_id}")

        try:
            if not ctx.checkpoint_id:
                logger.warning(
                    "No checkpoint_id provided for SNAPSHOT_RESTORE recovery"
                )
                return False

            # Load checkpoint
            checkpoint = await self.checkpoint_manager.load_checkpoint(task_id)

            if not checkpoint:
                logger.warning(f"No checkpoint found for task {task_id}")
                return False

            logger.info(
                f"Loaded checkpoint {ctx.checkpoint_id} for task {task_id}"
            )

            # Restore execution context
            self.task_executor.execution_contexts[task_id] = checkpoint

            logger.info(f"Restored execution context for task {task_id}")
            return True

        except Exception as e:
            logger.error(
                f"SNAPSHOT_RESTORE strategy failed: {str(e)}", exc_info=True
            )
            return False

    async def _execute_hitl(self, ctx: RecoveryContext) -> bool:
        """Execute HITL (Human-In-The-Loop) recovery strategy.

        Escalates task to human operator for manual intervention.

        Args:
            ctx: Recovery context

        Returns:
            True (HITL always succeeds as it transitions to manual state)
        """
        task_id = ctx.task_id
        logger.info(f"Executing HITL strategy for task {task_id}")

        try:
            # Transition to BLOCKED_HITL state
            self.state_machine.transition(
                task_id,
                TaskState.BLOCKED_HITL,
                f"Awaiting human intervention for error: {ctx.error_msg}",
            )

            logger.info(f"Task {task_id} escalated to human operator")
            return True

        except Exception as e:
            logger.error(f"HITL strategy failed: {str(e)}", exc_info=True)
            return False

    async def _execute_escalate(self, ctx: RecoveryContext) -> bool:
        """Execute ESCALATE recovery strategy.

        Escalates task to higher-level handling (e.g., incident management).

        Args:
            ctx: Recovery context

        Returns:
            True if escalation succeeded
        """
        task_id = ctx.task_id
        logger.info(f"Executing ESCALATE strategy for task {task_id}")

        try:
            # Log escalation details
            escalation_info = {
                "task_id": task_id,
                "workflow_id": ctx.workflow_id,
                "failure_type": ctx.failure_type.value,
                "error_msg": ctx.error_msg,
                "retry_count": ctx.retry_count,
                "timestamp": utc_now().isoformat(),
            }

            logger.warning(f"Task escalated: {escalation_info}")

            # Transition to BLOCKED_HITL for manual handling
            self.state_machine.transition(
                task_id,
                TaskState.BLOCKED_HITL,
                f"Escalated due to {ctx.failure_type.value}: {ctx.error_msg}",
            )

            return True

        except Exception as e:
            logger.error(f"ESCALATE strategy failed: {str(e)}", exc_info=True)
            return False

    def _track_recovery_attempt(self, ctx: RecoveryContext) -> None:
        """Track recovery attempt in history.

        Args:
            ctx: Recovery context
        """
        task_id = ctx.task_id

        if task_id not in self.recovery_history:
            self.recovery_history[task_id] = []

        attempt = {
            "timestamp": utc_now().isoformat(),
            "failure_type": ctx.failure_type.value,
            "error_msg": ctx.error_msg,
            "retry_count": ctx.retry_count,
            "strategy": (
                ctx.recovery_strategy.value
                if ctx.recovery_strategy
                else None
            ),
        }

        self.recovery_history[task_id].append(attempt)
        logger.debug(f"Tracked recovery attempt for task {task_id}")

    async def _publish_recovery_event(
        self,
        ctx: RecoveryContext,
        success: bool,
        error_msg: Optional[str] = None,
    ) -> None:
        """Publish recovery event to event bus.

        Args:
            ctx: Recovery context
            success: Whether recovery succeeded
            error_msg: Optional error message if recovery failed
        """
        try:
            event_type = (
                EventType.TASK_COMPLETED if success else EventType.TASK_FAILED
            )

            payload = {
                "task_id": ctx.task_id,
                "recovery_strategy": (
                    ctx.recovery_strategy.value
                    if ctx.recovery_strategy
                    else None
                ),
                "failure_type": ctx.failure_type.value,
                "success": success,
                "retry_count": ctx.retry_count,
                "timestamp": utc_now().isoformat(),
            }

            if error_msg:
                payload["error"] = error_msg

            event = Event(
                event_type=event_type,
                workflow_id=ctx.workflow_id,
                payload=payload,
            )

            await self.event_bus.publish(event)
            logger.debug(f"Published recovery event for task {ctx.task_id}")

        except Exception as e:
            logger.error(f"Failed to publish recovery event: {str(e)}")
