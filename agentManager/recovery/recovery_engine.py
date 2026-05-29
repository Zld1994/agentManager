"""Recovery engine for task recovery operations.

This module implements the RecoveryEngine class that orchestrates
task recovery using various strategies based on failure types.
"""

import logging
import inspect
import sys
from typing import Any, Dict, Optional
from datetime import datetime, timezone

from agentManager.recovery.recovery_context import (
    RecoveryContext,
    FailureType,
    RecoveryStrategy,
)
from agentManager.recovery.error_classifier import ErrorClassifier
from agentManager.runtime.task_executor import TaskExecutor, CheckpointManager
from agentManager.runtime.execution_context import ExecutionContext
from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.observability.audit import audit_recovery_escalated
from agentManager.observability.tracing import trace_operation

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
        defect_repair_pipeline: Optional[Any] = None,
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
        self.defect_repair_pipeline = defect_repair_pipeline
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
        span_cm = trace_operation(
            "recovery.execute",
            task_id=task_id,
            workflow_id=workflow_id,
            failure_type=ctx.failure_type.value,
        )
        span = span_cm.__enter__()

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
            elif ctx.recovery_strategy == RecoveryStrategy.DEFECT_REPAIR:
                success = await self._execute_defect_repair(ctx)
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
            span.set_attribute("success", success)
            if ctx.recovery_strategy == RecoveryStrategy.ESCALATE:
                audit_recovery_escalated(
                    workflow_id,
                    task_id,
                    ctx.error_msg,
                )

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
                    self._mark_recovery_ready(ctx)
            else:
                logger.warning(
                    f"Recovery failed for task {task_id} "
                    f"using strategy {ctx.recovery_strategy.value}"
                )
                # Transition to BLOCKED_HITL for manual intervention
                current_state = None
                get_state = getattr(self.state_machine, "get_state", None)
                if callable(get_state):
                    current_state = get_state(task_id)
                if current_state != TaskState.BLOCKED_HITL:
                    self.state_machine.transition(
                        task_id,
                        TaskState.BLOCKED_HITL,
                        f"Recovery failed with {ctx.recovery_strategy.value}",
                    )

            return success

        except Exception as e:
            logger.error(f"Recovery execution failed: {str(e)}", exc_info=True)
            span.set_attribute("success", False)
            await self._publish_recovery_event(ctx, False, str(e))
            return False
        finally:
            span_cm.__exit__(*sys.exc_info())

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
            # Get/create execution context
            exec_ctx = self._get_or_create_execution_context(ctx)

            # Increment retry count
            ctx.retry_count += 1
            logger.info(
                f"Retrying task {task_id} "
                f"(attempt {ctx.retry_count}/{self.MAX_RETRY_ATTEMPTS})"
            )

            get_task = getattr(self.task_executor, "get_task", None)
            task = None
            if callable(get_task):
                task = get_task(task_id)
                if inspect.isawaitable(task):
                    task = await task

            if task is not None:
                await self.task_executor.run_task(task)
                exec_ctx.metadata.pop("recovery_retry_ready", None)
                exec_ctx.metadata.pop("recovery_retry_reason", None)
                exec_ctx.metadata["recovery_last_retry_at"] = utc_now().isoformat()
                return True

            exec_ctx.metadata["recovery_retry_ready"] = True
            exec_ctx.metadata["recovery_retry_reason"] = (
                "Task object unavailable for immediate re-run"
            )
            exec_ctx.metadata["recovery_retry_count"] = ctx.retry_count
            exec_ctx.metadata["recovery_last_retry_at"] = utc_now().isoformat()
            return True

        except Exception as e:
            exec_ctx = self._get_or_create_execution_context(ctx)
            exec_ctx.metadata["recovery_retry_error"] = str(e)
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

            # Find the replay start index
            replay_start = next(
                (i for i, event in enumerate(events) if event.event_id == ctx.event_id),
                None,
            )
            if replay_start is None:
                logger.warning(
                    f"Event {ctx.event_id} not found in event bus"
                )
                return False

            replay_events = events[replay_start:]
            exec_ctx = self._get_or_create_execution_context(ctx)
            replayed_event_ids = []

            logger.info(
                f"Found {len(replay_events)} events to replay for task {task_id}"
            )

            for event in replay_events:
                payload = getattr(event, "payload", {})
                if not isinstance(payload, dict):
                    payload = {}
                payload_task_id = payload.get("task_id")
                if payload_task_id and payload_task_id != task_id:
                    continue

                replayed_event_ids.append(event.event_id)
                self._apply_event_to_execution_context(ctx, exec_ctx, event)

            if not replayed_event_ids:
                logger.warning(
                    "No task-scoped events were replayed for task %s", task_id
                )
                return False

            exec_ctx.metadata["replayed_event_ids"] = replayed_event_ids
            exec_ctx.metadata["last_replayed_event_id"] = replayed_event_ids[-1]
            exec_ctx.metadata["replayed_from_event_id"] = ctx.event_id

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

            checkpoint_task_id = getattr(checkpoint, "task_id", None)
            if (
                isinstance(checkpoint_task_id, str)
                and checkpoint_task_id
                and checkpoint_task_id != task_id
            ):
                logger.warning(
                    "Checkpoint task id mismatch for task %s", task_id
                )
                return False

            expected_checkpoint_id = ctx.checkpoint_id
            actual_checkpoint_id = self._extract_checkpoint_id(checkpoint)
            if (
                actual_checkpoint_id is not None
                and actual_checkpoint_id != expected_checkpoint_id
            ):
                logger.warning(
                    "Checkpoint id mismatch for task %s (expected=%s, got=%s)",
                    task_id,
                    expected_checkpoint_id,
                    actual_checkpoint_id,
                )
                return False

            logger.info(
                f"Loaded checkpoint {ctx.checkpoint_id} for task {task_id}"
            )

            # Restore execution context
            self.task_executor.execution_contexts[task_id] = checkpoint
            if isinstance(getattr(checkpoint, "metadata", None), dict):
                checkpoint.metadata["restored_from_checkpoint"] = ctx.checkpoint_id

            logger.info(f"Restored execution context for task {task_id}")
            return True

        except Exception as e:
            logger.error(
                f"SNAPSHOT_RESTORE strategy failed: {str(e)}", exc_info=True
            )
            return False

    async def _execute_defect_repair(self, ctx: RecoveryContext) -> bool:
        """Execute optional defect repair strategy for repairable task code."""
        task_id = ctx.task_id
        logger.info("Executing DEFECT_REPAIR strategy for task %s", task_id)
        exec_ctx = self._get_or_create_execution_context(ctx)
        metadata = exec_ctx.metadata
        repair_meta = metadata.setdefault("defect_repair", {})

        if self.defect_repair_pipeline is None:
            repair_meta.update(
                {
                    "status": "unavailable",
                    "success": False,
                    "failure_reason": "Defect repair pipeline is not configured",
                }
            )
            return False

        task = None
        get_task = getattr(self.task_executor, "get_task", None)
        if callable(get_task):
            task = get_task(task_id)
            if inspect.isawaitable(task):
                task = await task

        task_metadata: Dict[str, Any] = {}
        if task is not None and isinstance(getattr(task, "metadata", None), dict):
            task_metadata = task.metadata

        code = task_metadata.get("code") or task_metadata.get("source_code") or ""
        if not code:
            repair_meta.update(
                {
                    "status": "skipped",
                    "success": False,
                    "failure_reason": "No repairable code found in task metadata",
                }
            )
            return False

        error_msg = exec_ctx.error or ctx.error_msg
        execution_trace = (
            task_metadata.get("execution_trace")
            or task_metadata.get("trace")
            or error_msg
        )

        try:
            from agentManager.defect_repair.repair_pipeline import TaskRun
            from agentManager.defect_repair.repair_strategies import RepairStatus

            task_run = TaskRun(
                task_id=task_id,
                code=code,
                error_msg=error_msg,
                execution_trace=execution_trace,
                code_context=task_metadata.get("code_context", ""),
                metadata=task_metadata.copy(),
            )
            status, repaired_code = await self.defect_repair_pipeline.repair(task_run)
            history = self.defect_repair_pipeline.get_repair_history(task_id)
            last_result = history[-1] if history else None

            repair_meta.update(
                {
                    "status": status.value,
                    "success": status == RepairStatus.SUCCESS,
                    "repaired_code_present": bool(repaired_code),
                    "attempts": getattr(last_result, "attempts", 0),
                }
            )
            if last_result is not None:
                repair_meta["error_message"] = getattr(
                    last_result, "error_message", None
                )
                repair_meta["metadata"] = getattr(last_result, "metadata", {})

            if status == RepairStatus.SUCCESS:
                exec_ctx.mark_completed(
                    {
                        "repair_status": status.value,
                        "repaired_code_present": bool(repaired_code),
                    }
                )
                self._safe_transition(
                    task_id,
                    TaskState.COMPLETED,
                    "Defect repair verified repaired task code",
                )
                return True

            if status == RepairStatus.ESCALATED:
                self._record_manual_intervention(
                    ctx, RecoveryStrategy.DEFECT_REPAIR.value
                )
                self._safe_transition(
                    task_id,
                    TaskState.BLOCKED_HITL,
                    "Defect repair escalated to human review",
                )
            return False

        except Exception as exc:
            repair_meta.update(
                {
                    "status": "failed",
                    "success": False,
                    "failure_reason": str(exc),
                }
            )
            logger.error(
                "DEFECT_REPAIR strategy failed for task %s: %s",
                task_id,
                exc,
                exc_info=True,
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
            self._record_manual_intervention(ctx, RecoveryStrategy.HITL.value)
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
            self._record_manual_intervention(
                ctx, RecoveryStrategy.ESCALATE.value
            )
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

    def _get_or_create_execution_context(
        self, ctx: RecoveryContext
    ) -> ExecutionContext:
        """Get an existing execution context or create one for recovery metadata."""
        execution_ctx = self.task_executor.get_execution_context(ctx.task_id)
        if execution_ctx:
            metadata = getattr(execution_ctx, "metadata", None)
            if not isinstance(metadata, dict):
                execution_ctx.metadata = {}
            return execution_ctx

        execution_ctx = ExecutionContext(
            task_id=ctx.task_id,
            workflow_id=ctx.workflow_id,
            metadata={},
        )
        self.task_executor.execution_contexts[ctx.task_id] = execution_ctx
        return execution_ctx

    @staticmethod
    def _extract_checkpoint_id(checkpoint: ExecutionContext) -> Optional[str]:
        """Extract checkpoint id from checkpoint context when available."""
        checkpoint_id = getattr(checkpoint, "checkpoint_id", None)
        if isinstance(checkpoint_id, str) and checkpoint_id:
            return checkpoint_id
        if isinstance(getattr(checkpoint, "metadata", None), dict):
            metadata_checkpoint_id = checkpoint.metadata.get("checkpoint_id")
            if (
                isinstance(metadata_checkpoint_id, str)
                and metadata_checkpoint_id
            ):
                return metadata_checkpoint_id
        return None

    def _apply_event_to_execution_context(
        self,
        recovery_ctx: RecoveryContext,
        execution_ctx: ExecutionContext,
        event: Event,
    ) -> None:
        """Apply one event into execution/state context during replay."""
        payload = getattr(event, "payload", {})
        if not isinstance(payload, dict):
            payload = {}

        if event.event_type == EventType.TASK_STARTED:
            execution_ctx.mark_started()
            self._safe_transition(
                recovery_ctx.task_id,
                TaskState.IMPLEMENTING,
                "Recovery event replay: task_started",
            )
            return

        if event.event_type == EventType.TASK_COMPLETED:
            result = payload.get("result", {})
            if not isinstance(result, dict):
                result = {"result": result}
            execution_ctx.mark_completed(result)
            self._safe_transition(
                recovery_ctx.task_id,
                TaskState.COMPLETED,
                "Recovery event replay: task_completed",
            )
            return

        if event.event_type == EventType.TASK_FAILED:
            error = str(payload.get("error", recovery_ctx.error_msg))
            execution_ctx.mark_failed(error)
            retry_count = payload.get("retry_count")
            if isinstance(retry_count, int):
                execution_ctx.retry_count = retry_count
            self._safe_transition(
                recovery_ctx.task_id,
                TaskState.FAILED,
                "Recovery event replay: task_failed",
            )
            return

        if event.event_type == EventType.TASK_BLOCKED:
            self._safe_transition(
                recovery_ctx.task_id,
                TaskState.BLOCKED_HITL,
                "Recovery event replay: task_blocked",
            )

    def _mark_recovery_ready(self, ctx: RecoveryContext) -> None:
        """Mark a recovered task ready unless recovery already completed it."""
        task_id = ctx.task_id
        current_state = None
        get_state = getattr(self.state_machine, "get_state", None)
        if callable(get_state):
            current_state = get_state(task_id)

        if current_state in {TaskState.COMPLETED, TaskState.READY}:
            return

        reason = f"Recovery succeeded with {ctx.recovery_strategy.value}"
        if current_state == TaskState.FAILED:
            self.state_machine.transition(task_id, TaskState.BLOCKED_REPAIR, reason)
            return

        if current_state == TaskState.BLOCKED_REPAIR:
            return

        self.state_machine.transition(task_id, TaskState.READY, reason)

    def _safe_transition(
        self, task_id: str, new_state: TaskState, reason: str
    ) -> None:
        """Best-effort state transition for replay operations."""
        try:
            get_state = getattr(self.state_machine, "get_state", None)
            initialize = getattr(self.state_machine, "initialize", None)
            if callable(get_state) and callable(initialize):
                if get_state(task_id) is None:
                    initialize(task_id, TaskState.PENDING)
            self.state_machine.transition(task_id, new_state, reason)
        except Exception as exc:
            logger.debug(
                "Skipping replay transition for %s -> %s: %s",
                task_id,
                new_state.value,
                exc,
            )

    def _record_manual_intervention(
        self, ctx: RecoveryContext, strategy: str
    ) -> None:
        """Persist manual intervention context for HITL/ESCALATE handling."""
        execution_ctx = self._get_or_create_execution_context(ctx)
        interventions = execution_ctx.metadata.setdefault(
            "manual_intervention", []
        )
        interventions.append(
            {
                "strategy": strategy,
                "failure_type": ctx.failure_type.value,
                "error_msg": ctx.error_msg,
                "retry_count": ctx.retry_count,
                "checkpoint_id": ctx.checkpoint_id,
                "event_id": ctx.event_id,
                "timestamp": utc_now().isoformat(),
            }
        )
