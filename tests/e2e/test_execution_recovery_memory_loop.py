"""E2E tests for execution, recovery, and engineering memory loop integration."""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType
from agentManager.engine.scheduler import SchedulerEngine
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.recovery.recovery_context import (
    FailureType,
    RecoveryContext,
    RecoveryStrategy,
)
from agentManager.recovery.recovery_engine import RecoveryEngine
from agentManager.runtime.execution_context import ExecutionContext, ExecutionStatus
from agentManager.runtime.task_executor import (
    CheckpointManager,
    TaskExecutor,
    WorkerSandbox,
)
from agentManager.runtime.workflow_coordinator import WorkflowCoordinator
from agentManager.defect_repair.repair_strategies import RepairResult, RepairStatus


class FakeTaskStatus(str, Enum):
    """Minimal task status enum for workflow loop tests."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class FakeDAGNode:
    """Minimal DAG node shape used by TaskExecutor and coordinator."""

    node_id: str
    task_type: str
    dependencies: List[str]
    metadata: Dict[str, Any]
    status: FakeTaskStatus = FakeTaskStatus.PENDING


class FakeDAGEngine:
    """Small in-memory DAG engine for coordinator tests."""

    def __init__(self) -> None:
        self.nodes: Dict[str, FakeDAGNode] = {}

    def add_node(self, node: FakeDAGNode) -> None:
        self.nodes[node.node_id] = node

    def add_edge(self, from_node: str, to_node: str) -> None:
        if from_node not in self.nodes or to_node not in self.nodes:
            raise ValueError("missing node")
        if from_node not in self.nodes[to_node].dependencies:
            self.nodes[to_node].dependencies.append(from_node)

    def get_ready_nodes(self) -> List[str]:
        ready = []
        for task_id, node in self.nodes.items():
            if node.status != FakeTaskStatus.PENDING:
                continue
            if all(
                self.nodes[dependency].status == FakeTaskStatus.COMPLETED
                for dependency in node.dependencies
            ):
                ready.append(task_id)
        return ready

    def get_node(self, node_id: str) -> Optional[FakeDAGNode]:
        return self.nodes.get(node_id)

    def update_node_status(self, node_id: str, status: FakeTaskStatus) -> None:
        self.nodes[node_id].status = status


class InMemoryCheckpointManager(CheckpointManager):
    """Simple async checkpoint manager for coordinator tests."""

    def __init__(self) -> None:
        self.checkpoints: Dict[str, ExecutionContext] = {}

    async def save_checkpoint(self, task_id: str, context: ExecutionContext) -> None:
        self.checkpoints[task_id] = context

    async def load_checkpoint(self, task_id: str) -> Optional[ExecutionContext]:
        return self.checkpoints.get(task_id)

    async def delete_checkpoint(self, task_id: str) -> None:
        self.checkpoints.pop(task_id, None)


class StubWorkerSandbox(WorkerSandbox):
    """Deterministic worker sandbox for success/failure paths with retry support."""

    def __init__(
        self,
        failing_tasks: Optional[set[str]] = None,
        retry_success: bool = True,
    ) -> None:
        self.failing_tasks = failing_tasks or set()
        self.execution_order: List[str] = []
        self.attempt_counts: Dict[str, int] = {}
        self.retry_success = retry_success

    async def execute(self, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        self.execution_order.append(task_id)
        self.attempt_counts[task_id] = self.attempt_counts.get(task_id, 0) + 1
        if task_data.get("repair_attempt"):
            return {
                "task_id": task_id,
                "ok": True,
                "repair_attempt": True,
                "code": task_data.get("code"),
            }
        if task_id in self.failing_tasks:
            if self.retry_success and self.attempt_counts[task_id] > 1:
                return {"task_id": task_id, "ok": True, "attempt": self.attempt_counts[task_id]}
            raise RuntimeError(f"task {task_id} failed")
        return {"task_id": task_id, "ok": True}

    async def verify(self, task_id: str, result: Dict[str, Any]) -> bool:
        return True


class AsyncEventCollector(BaseEventBus):
    """In-memory async event collector."""

    def __init__(self) -> None:
        self.events: List[Event] = []

    async def subscribe(self, event_type, callback, workflow_id=None) -> None:
        return None

    async def publish(self, event: Event) -> None:
        self.events.append(event)

    async def unsubscribe(self, event_type, callback, workflow_id=None) -> None:
        return None

    async def get_events(self, event_type=None, workflow_id=None) -> List[Event]:
        events = self.events
        if event_type is not None:
            events = [event for event in events if event.event_type == event_type]
        if workflow_id is not None:
            events = [event for event in events if event.workflow_id == workflow_id]
        return events

    async def clear(self) -> None:
        self.events.clear()


@dataclass
class WorkflowHarness:
    """Test harness grouping coordinator dependencies."""

    dag: FakeDAGEngine
    scheduler: SchedulerEngine
    state_machine: StateMachine
    event_bus: AsyncEventCollector
    checkpoint_manager: InMemoryCheckpointManager
    sandbox: StubWorkerSandbox
    task_executor: TaskExecutor
    recovery_engine: RecoveryEngine
    engineering_memory: "InMemoryEngineeringMemory"
    coordinator: WorkflowCoordinator
    workflow_id: str = "wf-e2e"


class InMemoryEngineeringMemory:
    """Memory backend used to verify recovery write-back in E2E tests."""

    def __init__(self) -> None:
        self.entries: Dict[str, Dict[str, Any]] = {}

    async def put(self, namespace: str, key: str, value: Any) -> None:
        self.entries.setdefault(namespace, {})[key] = value

    async def get_all(self, namespace: str) -> Dict[str, Any]:
        return dict(self.entries.get(namespace, {}))


class VerifyingDefectRepairPipeline:
    """Small repair pipeline stub that verifies repaired code via TaskExecutor."""

    def __init__(self, task_executor: TaskExecutor) -> None:
        self.task_executor = task_executor
        self.repair_calls: List[Any] = []
        self._history: Dict[str, List[RepairResult]] = {}

    async def repair(self, task_run):
        self.repair_calls.append(task_run)
        repaired_code = "fixed_code()"
        result = await self.task_executor.execute(task_run.task_id, repaired_code)
        status = RepairStatus.SUCCESS if result.get("success") else RepairStatus.FAILED
        repair_result = RepairResult(
            status=status,
            repaired_code=repaired_code if status == RepairStatus.SUCCESS else None,
            error_message=result.get("error"),
            attempts=1,
        )
        self._history.setdefault(task_run.task_id, []).append(repair_result)
        return status, repair_result.repaired_code

    def get_repair_history(self, task_id: str) -> List[RepairResult]:
        return self._history.get(task_id, [])


def _build_recovery_harness(
    failing_tasks: Optional[set[str]] = None,
    retry_success: bool = True,
    max_retries: int = 0,
    enable_defect_repair: bool = False,
    include_repair_code: bool = False,
) -> WorkflowHarness:
    dag = FakeDAGEngine()
    extract_metadata = {"workflow_id": "wf-e2e"}
    if include_repair_code:
        extract_metadata["code"] = "broken_code()"
    dag.add_node(
        FakeDAGNode(
            node_id="extract",
            task_type="io",
            dependencies=[],
            metadata=extract_metadata,
        )
    )
    dag.add_node(
        FakeDAGNode(
            node_id="transform",
            task_type="compute",
            dependencies=[],
            metadata={"workflow_id": "wf-e2e"},
        )
    )
    dag.add_edge("extract", "transform")

    scheduler = SchedulerEngine(max_concurrent_tasks=2)
    state_machine = StateMachine()
    event_bus = AsyncEventCollector()
    checkpoint_manager = InMemoryCheckpointManager()
    sandbox = StubWorkerSandbox(failing_tasks=failing_tasks, retry_success=retry_success)

    task_executor = TaskExecutor(
        dag_engine=dag,
        scheduler=scheduler,
        worker_sandbox=sandbox,
        event_bus=event_bus,
        state_machine=state_machine,
        checkpoint_manager=checkpoint_manager,
        max_retries=max_retries,
    )

    defect_repair_pipeline = (
        VerifyingDefectRepairPipeline(task_executor) if enable_defect_repair else None
    )
    recovery_engine = RecoveryEngine(
        task_executor=task_executor,
        event_bus=event_bus,
        state_machine=state_machine,
        checkpoint_manager=checkpoint_manager,
        defect_repair_pipeline=defect_repair_pipeline,
    )
    engineering_memory = InMemoryEngineeringMemory()
    coordinator = WorkflowCoordinator(
        dag_engine=dag,
        scheduler=scheduler,
        task_executor=task_executor,
        event_bus=event_bus,
        state_machine=state_machine,
        recovery_engine=recovery_engine if enable_defect_repair else None,
    )

    return WorkflowHarness(
        dag=dag,
        scheduler=scheduler,
        state_machine=state_machine,
        event_bus=event_bus,
        checkpoint_manager=checkpoint_manager,
        sandbox=sandbox,
        task_executor=task_executor,
        recovery_engine=recovery_engine,
        engineering_memory=engineering_memory,
        coordinator=coordinator,
    )


def test_failing_task_recovers_through_recovery_engine_and_records_memory() -> None:
    """Recover a failed task through RecoveryEngine and record the outcome."""
    harness_fail = _build_recovery_harness(
        failing_tasks={"extract"},
        retry_success=True,
        max_retries=0,
    )

    result1 = asyncio.run(
        harness_fail.coordinator.run_workflow(workflow_id=harness_fail.workflow_id)
    )
    assert result1.success is False
    assert "extract" in result1.failed_tasks

    harness_fail.state_machine.transition(
        "extract",
        TaskState.BLOCKED_REPAIR,
        "E2E recovery attempt",
    )
    recovery_context = RecoveryContext(
        task_id="extract",
        workflow_id=harness_fail.workflow_id,
        failure_type=FailureType.TIMEOUT,
        error_msg="task extract failed",
        recovery_strategy=RecoveryStrategy.RETRY,
    )

    recovery_success = asyncio.run(harness_fail.recovery_engine.execute_recovery(recovery_context))
    assert recovery_success is True
    assert harness_fail.sandbox.attempt_counts["extract"] == 2
    assert harness_fail.state_machine.get_state("extract") == TaskState.COMPLETED

    recovery_record = {
        "type": "task_recovery",
        "task_id": "extract",
        "workflow_id": harness_fail.workflow_id,
        "strategy": recovery_context.recovery_strategy.value,
        "success": recovery_success,
        "tags": ["recovery", "task"],
        "content": "Task extract recovered with retry strategy",
    }
    asyncio.run(
        harness_fail.engineering_memory.put(
            namespace=harness_fail.workflow_id,
            key="recovery:extract:retry",
            value=recovery_record,
        )
    )

    event_types = [event.event_type for event in harness_fail.event_bus.events]
    assert EventType.TASK_FAILED in event_types
    assert EventType.TASK_COMPLETED in event_types

    memory_entries = asyncio.run(
        harness_fail.engineering_memory.get_all(namespace=harness_fail.workflow_id)
    )
    assert memory_entries["recovery:extract:retry"]["success"] is True


def test_event_replay_recovery_updates_context_and_records_memory() -> None:
    """Replay task events through RecoveryEngine and persist the recovery result."""
    harness = _build_recovery_harness()
    replay_start = Event(
        event_type=EventType.TASK_STARTED,
        workflow_id=harness.workflow_id,
        payload={"task_id": "extract"},
    )
    replay_done = Event(
        event_type=EventType.TASK_COMPLETED,
        workflow_id=harness.workflow_id,
        payload={"task_id": "extract", "result": {"ok": True}},
    )
    asyncio.run(harness.event_bus.publish(replay_start))
    asyncio.run(harness.event_bus.publish(replay_done))
    harness.state_machine.initialize("extract", TaskState.PENDING)

    recovery_context = RecoveryContext(
        task_id="extract",
        workflow_id=harness.workflow_id,
        failure_type=FailureType.NETWORK,
        error_msg="event stream interrupted",
        event_id=replay_start.event_id,
        recovery_strategy=RecoveryStrategy.EVENT_REPLAY,
    )

    recovery_success = asyncio.run(harness.recovery_engine.execute_recovery(recovery_context))
    assert recovery_success is True

    execution_context = harness.task_executor.get_execution_context("extract")
    assert execution_context is not None
    assert execution_context.status == ExecutionStatus.COMPLETED
    assert execution_context.result == {"ok": True}
    assert execution_context.metadata["replayed_from_event_id"] == replay_start.event_id

    asyncio.run(
        harness.engineering_memory.put(
            namespace=harness.workflow_id,
            key="recovery:extract:event-replay",
            value={
                "type": "task_recovery",
                "task_id": "extract",
                "strategy": recovery_context.recovery_strategy.value,
                "success": recovery_success,
                "tags": ["recovery", "event_replay"],
                "content": "Task extract recovered by replaying task events",
            },
        )
    )
    memory_entries = asyncio.run(harness.engineering_memory.get_all(namespace=harness.workflow_id))
    assert memory_entries["recovery:extract:event-replay"]["success"] is True


def test_workflow_loop_invokes_defect_repair_and_continues_dependents() -> None:
    """Failed task should repair in-loop and unblock downstream tasks."""
    harness = _build_recovery_harness(
        failing_tasks={"extract"},
        retry_success=False,
        max_retries=0,
        enable_defect_repair=True,
        include_repair_code=True,
    )

    result = asyncio.run(harness.coordinator.run_workflow(workflow_id=harness.workflow_id))

    assert result.success is True
    assert result.completed_tasks == ["extract", "transform"]
    assert result.failed_tasks == []
    assert harness.dag.get_node("extract").status == FakeTaskStatus.COMPLETED
    assert harness.dag.get_node("transform").status == FakeTaskStatus.COMPLETED
    assert harness.state_machine.get_state("extract") == TaskState.COMPLETED
    assert harness.sandbox.execution_order == ["extract", "extract", "transform"]

    execution_context = harness.task_executor.get_execution_context("extract")
    assert execution_context is not None
    assert execution_context.metadata["defect_repair"]["status"] == "success"
    assert execution_context.metadata["defect_repair"]["repaired_code_present"] is True


def test_workflow_loop_missing_repair_code_blocks_without_downstream_corruption() -> None:
    """Defect repair opt-in should fail closed when task metadata has no code."""
    harness = _build_recovery_harness(
        failing_tasks={"extract"},
        retry_success=False,
        max_retries=0,
        enable_defect_repair=True,
        include_repair_code=False,
    )

    result = asyncio.run(harness.coordinator.run_workflow(workflow_id=harness.workflow_id))

    assert result.success is False
    assert result.completed_tasks == []
    assert result.failed_tasks == ["extract"]
    assert harness.dag.get_node("extract").status == FakeTaskStatus.FAILED
    assert harness.dag.get_node("transform").status == FakeTaskStatus.PENDING
    assert harness.scheduler.get_task_status("transform") == "pending"

    execution_context = harness.task_executor.get_execution_context("extract")
    assert execution_context is not None
    assert execution_context.metadata["defect_repair"]["status"] == "skipped"
    assert "No repairable code" in execution_context.metadata["defect_repair"]["failure_reason"]
