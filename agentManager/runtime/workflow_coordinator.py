"""Runtime workflow coordinator.

Connects DAG readiness, scheduler dispatch, task execution, task lifecycle
events, state transitions, checkpoint persistence, and final workflow outcome.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List
import heapq
import logging

from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType
from agentManager.engine.scheduler import SchedulerEngine
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.observability.tracing import trace_operation
from agentManager.recovery.recovery_context import RecoveryContext, RecoveryStrategy
from agentManager.runtime.execution_context import ExecutionContext
from agentManager.runtime.task_executor import TaskExecutor

logger = logging.getLogger(__name__)


@dataclass
class WorkflowRunResult:
    """Summary of one workflow loop run."""

    workflow_id: str
    success: bool
    completed_tasks: List[str] = field(default_factory=list)
    failed_tasks: List[str] = field(default_factory=list)
    execution_contexts: Dict[str, ExecutionContext] = field(default_factory=dict)


class WorkflowCoordinator:
    """Coordinates a full workflow run over existing runtime components."""

    def __init__(
        self,
        dag_engine: Any,
        scheduler: SchedulerEngine,
        task_executor: TaskExecutor,
        event_bus: BaseEventBus,
        state_machine: StateMachine,
        recovery_engine: Any = None,
        max_iterations: int = 1000,
    ) -> None:
        self.dag_engine = dag_engine
        self.scheduler = scheduler
        self.task_executor = task_executor
        self.event_bus = event_bus
        self.state_machine = state_machine
        self.recovery_engine = recovery_engine
        self.max_iterations = max_iterations

    async def run_workflow(self, workflow_id: str) -> WorkflowRunResult:
        """Run workflow tasks until completion/failure or loop guard timeout."""
        with trace_operation(
            "workflow.run",
            workflow_id=workflow_id,
            task_count=len(self.dag_engine.nodes),
        ) as span:
            self._register_missing_tasks()
            await self._publish(
                EventType.WORKFLOW_STARTED,
                workflow_id,
                {"task_count": len(self.dag_engine.nodes)},
            )

            idle_iterations = 0
            for _ in range(self.max_iterations):
                ready_tasks = self.dag_engine.get_ready_nodes()
                self._mark_ready(ready_tasks)
                self._clear_backoff_for_ready_tasks(ready_tasks)
                self.scheduler.execute_scheduled_tasks()
                self._sync_scheduler_failures()

                running_tasks = list(self.scheduler.get_running_tasks())
                if not running_tasks:
                    if self._all_tasks_terminal():
                        break

                    idle_iterations += 1
                    if idle_iterations > 2:
                        logger.warning(
                            "Workflow %s stopped after idle iterations", workflow_id
                        )
                        break
                    continue

                idle_iterations = 0
                for task_id in running_tasks:
                    await self._execute_scheduled_task(task_id)

                if self._all_tasks_terminal():
                    break
            else:
                logger.warning(
                    "Workflow %s stopped at max_iterations=%s",
                    workflow_id,
                    self.max_iterations,
                )

            completed_tasks = [
                task_id
                for task_id, task in self.scheduler.tasks.items()
                if task.status == "completed"
            ]
            failed_tasks = [
                task_id
                for task_id, task in self.scheduler.tasks.items()
                if task.status == "failed"
            ]
            success = len(failed_tasks) == 0 and len(completed_tasks) == len(
                self.scheduler.tasks
            )

            result = WorkflowRunResult(
                workflow_id=workflow_id,
                success=success,
                completed_tasks=completed_tasks,
                failed_tasks=failed_tasks,
                execution_contexts=self.task_executor.get_all_contexts(),
            )

            await self._publish(
                EventType.WORKFLOW_COMPLETED if success else EventType.WORKFLOW_FAILED,
                workflow_id,
                {
                    "completed_tasks": result.completed_tasks,
                    "failed_tasks": result.failed_tasks,
                    "task_count": len(self.scheduler.tasks),
                },
            )
            span.set_attribute("success", success)
            return result

    def _register_missing_tasks(self) -> None:
        """Register DAG nodes with scheduler and state machine when needed."""
        for node_id, node in self.dag_engine.nodes.items():
            if node_id not in self.scheduler.tasks:
                self.scheduler.add_task(
                    task_id=node_id,
                    priority=int(node.metadata.get("priority", 0)),
                    dependencies=list(node.dependencies),
                )
            if self.state_machine.get_state(node_id) is None:
                self.state_machine.initialize(node_id, TaskState.PENDING)

    def _mark_ready(self, ready_tasks: List[str]) -> None:
        """Transition state machine nodes from pending to ready when possible."""
        for task_id in ready_tasks:
            current = self.state_machine.get_state(task_id)
            if current is None:
                self.state_machine.initialize(task_id, TaskState.PENDING)
                current = TaskState.PENDING
            if current == TaskState.PENDING:
                self.state_machine.transition(
                    task_id, TaskState.READY, "Dependencies satisfied"
                )

    def _clear_backoff_for_ready_tasks(self, ready_tasks: List[str]) -> None:
        """Clear scheduler backoff when DAG says a task is ready to run."""
        for task_id in ready_tasks:
            scheduled_task = self.scheduler.tasks.get(task_id)
            if scheduled_task and scheduled_task.status == "pending":
                scheduled_task.next_retry_at = None
                scheduled_task.retry_attempts = 0

    async def _execute_scheduled_task(self, task_id: str) -> None:
        """Execute one scheduler-dispatched task and sync engine statuses."""
        node = self.dag_engine.get_node(task_id)
        if node is None:
            self.scheduler.mark_failed(task_id)
            return

        status_enum = node.status.__class__
        self.dag_engine.update_node_status(task_id, status_enum.RUNNING)
        try:
            await self.task_executor.run_task(node)
            self.scheduler.mark_completed(task_id)
            self.dag_engine.update_node_status(task_id, status_enum.COMPLETED)
        except Exception as exc:
            recovered = await self._recover_failed_task(task_id, node, exc)
            if recovered:
                current_state = self.state_machine.get_state(task_id)
                if current_state == TaskState.COMPLETED:
                    self.scheduler.mark_completed(task_id)
                    self.dag_engine.update_node_status(task_id, status_enum.COMPLETED)
                    return
                if current_state == TaskState.READY:
                    self._mark_scheduler_pending(task_id)
                    self.dag_engine.update_node_status(task_id, status_enum.PENDING)
                    return
                logger.warning(
                    "Recovery for task %s did not produce a runnable or "
                    "completed state",
                    task_id,
                )

            self.scheduler.mark_failed(task_id)
            self.dag_engine.update_node_status(task_id, status_enum.FAILED)
            self._set_failed_state(task_id, "Task execution failed")

    async def _recover_failed_task(
        self,
        task_id: str,
        node: Any,
        error: Exception,
    ) -> bool:
        """Run optional recovery after task execution fails."""
        if self.recovery_engine is None:
            return False

        failure_type, strategy = self.recovery_engine.error_classifier.classify(error)
        repair_pipeline = getattr(self.recovery_engine, "defect_repair_pipeline", None)
        if repair_pipeline is not None:
            strategy = RecoveryStrategy.DEFECT_REPAIR

        workflow_id = node.metadata.get("workflow_id", "unknown")
        ctx = RecoveryContext(
            task_id=task_id,
            workflow_id=workflow_id,
            failure_type=failure_type,
            error_msg=str(error),
            recovery_strategy=strategy,
        )

        try:
            return await self.recovery_engine.execute_recovery(ctx)
        except Exception as exc:
            logger.error("Recovery failed for task %s: %s", task_id, exc)
            return False

    def _mark_scheduler_pending(self, task_id: str) -> None:
        """Return a recovered running task to the scheduler pending queue."""
        task = self.scheduler.tasks.get(task_id)
        if task is None:
            return
        task.status = "pending"
        task.next_retry_at = None
        task.retry_attempts = 0
        self.scheduler.running_tasks.discard(task_id)
        if not any(item[1] == task_id for item in self.scheduler.execution_queue):
            heapq.heappush(self.scheduler.execution_queue, (-task.priority, task_id))

    def _all_tasks_terminal(self) -> bool:
        """Return True when every scheduled task is completed or failed."""
        if not self.scheduler.tasks:
            return True
        return all(
            task.status in {"completed", "failed"}
            for task in self.scheduler.tasks.values()
        )

    def _sync_scheduler_failures(self) -> None:
        """Propagate scheduler-side failures to DAG and state machine."""
        for task_id, task in self.scheduler.tasks.items():
            if task.status != "failed":
                continue

            node = self.dag_engine.get_node(task_id)
            if node:
                status_enum = node.status.__class__
                if node.status not in {status_enum.COMPLETED, status_enum.FAILED}:
                    self.dag_engine.update_node_status(task_id, status_enum.FAILED)
            self._set_failed_state(task_id, "Scheduler marked task as failed")

    def _set_failed_state(self, task_id: str, reason: str) -> None:
        """Ensure the state machine reflects a failed task."""
        current = self.state_machine.get_state(task_id)
        if current is None:
            self.state_machine.initialize(task_id, TaskState.PENDING)
            current = TaskState.PENDING

        if current not in {TaskState.COMPLETED, TaskState.BLOCKED_HITL, TaskState.FAILED}:
            self.state_machine.transition(task_id, TaskState.FAILED, reason)

    async def _publish(
        self,
        event_type: EventType,
        workflow_id: str,
        payload: Dict[str, object],
    ) -> None:
        """Publish workflow-level events while tolerating bus failures."""
        try:
            await self.event_bus.publish(
                Event(
                    event_type=event_type,
                    workflow_id=workflow_id,
                    payload=payload,
                )
            )
        except Exception as exc:
            logger.error(
                "Failed to publish workflow event %s for workflow %s: %s",
                event_type.value,
                workflow_id,
                exc,
            )
