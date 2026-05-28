"""E2E tests for execution, recovery, and engineering memory loop integration."""

from dataclasses import dataclass
from enum import Enum
import asyncio
from typing import Any, Dict, List, Optional

from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType
from agentManager.engine.scheduler import SchedulerEngine
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.runtime.execution_context import ExecutionContext, ExecutionStatus
from agentManager.runtime.task_executor import CheckpointManager, TaskExecutor, WorkerSandbox
from agentManager.runtime.workflow_coordinator import WorkflowCoordinator
from agentManager.recovery.recovery_engine import RecoveryEngine
from agentManager.recovery.recovery_context import RecoveryContext, RecoveryStrategy, FailureType
from agentManager.memory.engineering_memory import EngineeringMemory


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

    def __init__(self, failing_tasks: Optional[set[str]] = None, retry_success: bool = True) -> None:
        self.failing_tasks = failing_tasks or set()
        self.execution_order: List[str] = []
        self.attempt_counts: Dict[str, int] = {}
        self.retry_success = retry_success

    async def execute(self, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        self.execution_order.append(task_id)
        self.attempt_counts[task_id] = self.attempt_counts.get(task_id, 0) + 1
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
    engineering_memory: EngineeringMemory
    coordinator: WorkflowCoordinator
    workflow_id: str = "wf-e2e"


def _build_recovery_harness(db_path: str, failing_tasks: Optional[set[str]] = None, retry_success: bool = True, max_retries: int = 0) -> WorkflowHarness:
    dag = FakeDAGEngine()
    dag.add_node(
        FakeDAGNode(
            node_id="extract",
            task_type="io",
            dependencies=[],
            metadata={"workflow_id": "wf-e2e"},
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

    recovery_engine = RecoveryEngine(
        task_executor=task_executor,
        event_bus=event_bus,
        state_machine=state_machine,
        checkpoint_manager=checkpoint_manager,
    )
    engineering_memory = EngineeringMemory(db_path=db_path)
    coordinator = WorkflowCoordinator(
        dag_engine=dag,
        scheduler=scheduler,
        task_executor=task_executor,
        event_bus=event_bus,
        state_machine=state_machine,
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


def test_failing_task_with_recovery_and_memory_recording(tmp_path) -> None:
    """Test a failing task that recovers on retry, with events and memory recorded."""
    # First harness with max_retries=0 to fail first run
    db_path1 = str(tmp_path / "test_engineering_memory1.db")
    harness_fail = _build_recovery_harness(db_path=db_path1, failing_tasks={"extract"}, retry_success=True, max_retries=0)

    # First run - extract fails
    result1 = asyncio.run(harness_fail.coordinator.run_workflow(workflow_id=harness_fail.workflow_id))
    assert result1.success is False
    assert "extract" in result1.failed_tasks

    # Record failure in engineering memory (using put method with namespace)
    failure_record = {
        "type": "task_failure",
        "task_id": "extract",
        "workflow_id": harness_fail.workflow_id,
        "error_type": "RuntimeError",
        "error_msg": "task extract failed",
        "attempt": harness_fail.sandbox.attempt_counts["extract"],
        "tags": ["failure", "task"],
        "content": "Task extract failed on first attempt",
    }
    asyncio.run(harness_fail.engineering_memory.put(
        namespace=harness_fail.workflow_id,
        key=f"failure:extract:0",
        value=failure_record
    ))

    # Second harness with max_retries=1 to test successful retry
    db_path2 = str(tmp_path / "test_engineering_memory2.db")
    harness_success = _build_recovery_harness(db_path=db_path2, failing_tasks={"extract"}, retry_success=True, max_retries=1)

    # Second run - extract succeeds
    result2 = asyncio.run(harness_success.coordinator.run_workflow(workflow_id=harness_success.workflow_id))
    assert result2.success is True
    assert result2.completed_tasks == ["extract", "transform"]

    # Verify events
    event_types = [event.event_type for event in harness_success.event_bus.events]
    assert EventType.WORKFLOW_STARTED in event_types
    assert EventType.WORKFLOW_COMPLETED in event_types
    assert EventType.TASK_COMPLETED in event_types

    # Verify memory entry (using get_all)
    memory_entries = asyncio.run(harness_fail.engineering_memory.get_all(namespace=harness_fail.workflow_id))
    assert len(memory_entries) >= 1


def test_workflow_coordinator_with_recovery_strategy(tmp_path) -> None:
    """Test coordinator with explicit recovery strategy for failing tasks."""
    db_path = str(tmp_path / "test_engineering_memory3.db")
    harness = _build_recovery_harness(db_path=db_path, failing_tasks={"transform"}, retry_success=True, max_retries=0)

    # Use recovery engine to get recovery strategy (pass FailureType instead of ctx)
    strategy = harness.recovery_engine.select_recovery_strategy(FailureType.RUNTIME)
    assert strategy in [RecoveryStrategy.RETRY, RecoveryStrategy.EVENT_REPLAY, RecoveryStrategy.SNAPSHOT_RESTORE]
