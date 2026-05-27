"""Task executor for managing task execution lifecycle.

This module implements the TaskExecutor class that orchestrates the complete
task execution flow, including lifecycle management, error handling, and recovery.
"""

import logging
from typing import Dict, Any, Optional, Protocol
from abc import ABC, abstractmethod

from agentManager.engine.scheduler import SchedulerEngine
from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.runtime.execution_context import ExecutionContext

logger = logging.getLogger(__name__)


class TaskLike(Protocol):
    """Protocol for task objects accepted by TaskExecutor."""

    node_id: str
    metadata: Dict[str, Any]


class CheckpointManager(ABC):
    """Abstract base class for checkpoint management."""

    @abstractmethod
    async def save_checkpoint(
        self, task_id: str, context: ExecutionContext
    ) -> None:
        """Save execution checkpoint.

        Args:
            task_id: Task identifier
            context: Execution context to save
        """
        pass

    @abstractmethod
    async def load_checkpoint(self, task_id: str) -> Optional[ExecutionContext]:
        """Load execution checkpoint.

        Args:
            task_id: Task identifier

        Returns:
            Execution context or None if not found
        """
        pass

    @abstractmethod
    async def delete_checkpoint(self, task_id: str) -> None:
        """Delete execution checkpoint.

        Args:
            task_id: Task identifier
        """
        pass


class WorkerSandbox(ABC):
    """Abstract base class for worker sandbox execution."""

    @abstractmethod
    async def execute(
        self, task_id: str, task_data: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Execute task in sandbox.

        Args:
            task_id: Task identifier
            task_data: Task data and parameters

        Returns:
            Execution result

        Raises:
            Exception: If execution fails
        """
        pass

    @abstractmethod
    async def verify(
        self, task_id: str, result: Dict[str, Any]
    ) -> bool:
        """Verify task execution result.

        Args:
            task_id: Task identifier
            result: Execution result to verify

        Returns:
            True if verification passed
        """
        pass


class TaskExecutor:
    """Orchestrates task execution lifecycle.

    Manages the complete execution flow from PENDING through IMPLEMENTING,
    VERIFYING, and COMPLETED states, with error handling and recovery.
    """

    # Configuration constants
    DEFAULT_MAX_RETRIES = 3
    DEFAULT_RETRY_DELAY = 1.0  # seconds

    def __init__(
        self,
        dag_engine: Any,
        scheduler: SchedulerEngine,
        worker_sandbox: WorkerSandbox,
        event_bus: BaseEventBus,
        state_machine: StateMachine,
        checkpoint_manager: CheckpointManager,
        max_retries: int = DEFAULT_MAX_RETRIES,
    ):
        """Initialize TaskExecutor.

        Args:
            dag_engine: DAG engine for dependency management
            scheduler: Scheduler for task scheduling
            worker_sandbox: Sandbox for task execution
            event_bus: Event bus for publishing events
            state_machine: State machine for state management
            checkpoint_manager: Manager for saving/loading checkpoints
            max_retries: Maximum retry attempts
        """
        self.dag_engine = dag_engine
        self.scheduler = scheduler
        self.worker_sandbox = worker_sandbox
        self.event_bus = event_bus
        self.state_machine = state_machine
        self.checkpoint_manager = checkpoint_manager
        self.max_retries = max_retries

        # Execution contexts for tracking
        self.execution_contexts: Dict[str, ExecutionContext] = {}
        # Task registry for recovery-triggered reruns.
        self._task_registry: Dict[str, TaskLike] = {}

        logger.info(
            f"TaskExecutor initialized with max_retries={max_retries}"
        )

    async def run_task(self, task: TaskLike) -> ExecutionContext:
        """Execute a single task with full lifecycle management.

        Manages the complete task execution flow:
        1. Initialize execution context
        2. Transition to IMPLEMENTING state
        3. Execute task in sandbox
        4. Transition to VERIFYING state
        5. Verify execution result
        6. Transition to COMPLETED state
        7. Handle errors and retries

        Args:
            task: DAG node representing the task

        Returns:
            ExecutionContext with execution results

        Raises:
            Exception: If task execution fails after all retries
        """
        task_id = task.node_id
        workflow_id = task.metadata.get("workflow_id", "unknown")
        self._task_registry[task_id] = task

        logger.info(f"Starting execution of task {task_id}")

        # Initialize execution context
        context = ExecutionContext(
            task_id=task_id,
            workflow_id=workflow_id,
            metadata=task.metadata.copy(),
        )
        context.mark_started()  # Mark as started immediately

        # Initialize state machine if task state has not been set yet.
        if self.state_machine.get_state(task_id) is None:
            self.state_machine.initialize(task_id, TaskState.PENDING)
        self.execution_contexts[task_id] = context

        try:
            # Try to load checkpoint if exists
            checkpoint = await self.checkpoint_manager.load_checkpoint(task_id)
            if checkpoint:
                logger.info(f"Loaded checkpoint for task {task_id}")
                context = checkpoint
                self.execution_contexts[task_id] = context

            # Publish task started event
            await self._publish_event(
                EventType.TASK_STARTED,
                workflow_id,
                {"task_id": task_id, "status": "started"},
            )

            # Execute task with retry logic
            result = await self._execute_with_retry(task, context)

            # Transition to VERIFYING
            self.state_machine.transition(
                task_id, TaskState.VERIFYING, "Verifying execution result"
            )

            # Mark as completed
            context.mark_completed(result)
            self.state_machine.transition(
                task_id, TaskState.COMPLETED, "Task completed successfully"
            )

            # Save checkpoint
            await self.checkpoint_manager.save_checkpoint(task_id, context)

            # Publish task completed event
            await self._publish_event(
                EventType.TASK_COMPLETED,
                workflow_id,
                {
                    "task_id": task_id,
                    "status": "completed",
                    "result": result,
                    "duration": context.get_duration(),
                },
            )

            duration = context.get_duration()
            if duration is not None:
                logger.info(
                    f"Task {task_id} completed successfully in {duration:.2f}s"
                )
            else:
                logger.info(f"Task {task_id} completed successfully")

            return context

        except Exception as e:
            logger.error(f"Task {task_id} failed: {str(e)}", exc_info=True)
            context.mark_failed(str(e))
            self.state_machine.transition(
                task_id, TaskState.FAILED, f"Task failed: {str(e)}"
            )

            # Save checkpoint before publishing failure
            await self.checkpoint_manager.save_checkpoint(task_id, context)

            # Publish task failed event
            await self._publish_event(
                EventType.TASK_FAILED,
                workflow_id,
                {
                    "task_id": task_id,
                    "status": "failed",
                    "error": str(e),
                    "retry_count": context.retry_count,
                },
            )

            raise

    async def _execute_with_retry(
        self, task: TaskLike, context: ExecutionContext
    ) -> Dict[str, Any]:
        """Execute task with retry logic.

        Args:
            task: Task to execute
            context: Execution context

        Returns:
            Execution result

        Raises:
            Exception: If all retries exhausted
        """
        task_id = task.node_id
        last_error = None

        # Transition to IMPLEMENTING once at the start
        self.state_machine.transition(
            task_id,
            TaskState.IMPLEMENTING,
            "Starting task execution",
        )

        for attempt in range(self.max_retries + 1):
            try:
                logger.info(
                    f"Executing task {task_id} (attempt {attempt + 1}/"
                    f"{self.max_retries + 1})"
                )

                # Execute task
                result = await self.worker_sandbox.execute(
                    task_id, task.metadata
                )

                # Verify result
                is_valid = await self.worker_sandbox.verify(task_id, result)

                if not is_valid:
                    raise ValueError("Verification failed")

                logger.info(
                    f"Task {task_id} executed and verified successfully"
                )
                return result

            except Exception as e:
                last_error = e
                context.increment_retry()
                logger.warning(
                    f"Task {task_id} attempt {attempt + 1} failed: {str(e)}"
                )

                if attempt < self.max_retries:
                    logger.info(
                        f"Retrying task {task_id} "
                        f"(attempt {attempt + 2}/{self.max_retries + 1})"
                    )
                    continue
                else:
                    break

        # All retries exhausted - transition to VERIFYING then fail
        self.state_machine.transition(
            task_id, TaskState.VERIFYING, "Verification after retries"
        )

        # All retries exhausted
        raise Exception(
            f"Task {task_id} failed after {self.max_retries + 1} attempts: "
            f"{str(last_error)}"
        )

    async def _publish_event(
        self,
        event_type: EventType,
        workflow_id: str,
        payload: Dict[str, Any],
    ) -> None:
        """Publish event to event bus.

        Args:
            event_type: Type of event
            workflow_id: Workflow identifier
            payload: Event payload
        """
        try:
            event = Event(
                event_type=event_type,
                workflow_id=workflow_id,
                payload=payload,
            )
            await self.event_bus.publish(event)
            logger.debug(f"Published event: {event_type.value}")
        except Exception as e:
            logger.error(f"Failed to publish event: {str(e)}")

    def get_execution_context(self, task_id: str) -> Optional[ExecutionContext]:
        """Get execution context for a task.

        Args:
            task_id: Task identifier

        Returns:
            ExecutionContext or None if not found
        """
        return self.execution_contexts.get(task_id)

    def get_all_contexts(self) -> Dict[str, ExecutionContext]:
        """Get all execution contexts.

        Returns:
            Dictionary of all execution contexts
        """
        return self.execution_contexts.copy()

    def get_task(self, task_id: str) -> Optional[TaskLike]:
        """Get the most recently seen task object for a task id."""
        return self._task_registry.get(task_id)

    async def cleanup(self, task_id: str) -> None:
        """Clean up execution context for a task.

        Args:
            task_id: Task identifier
        """
        if task_id in self.execution_contexts:
            del self.execution_contexts[task_id]
            logger.info(f"Cleaned up execution context for task {task_id}")
        self._task_registry.pop(task_id, None)
