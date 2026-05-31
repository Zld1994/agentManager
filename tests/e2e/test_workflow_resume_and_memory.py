"""E2E tests for P3: memory write-back, checkpoint resume, and crash recovery.

Covers:
- P3-1: WorkflowCoordinator automatically writes task results and recovery
  outcomes to a MemoryBackend when one is provided.
- P3-2: resume_workflow restores completed tasks from checkpoints and
  continues executing remaining tasks.
- P3-3: A workflow that crashes mid-execution can be resumed from persisted
  state via a new WorkflowCoordinator instance.
"""

import asyncio
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional

from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType
from agentManager.engine.scheduler import SchedulerEngine
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.memory.memory_backend import MemoryBackend
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
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class FakeDAGNode:
    node_id: str
    task_type: str
    dependencies: List[str]
    metadata: Dict[str, Any]
    status: FakeTaskStatus = FakeTaskStatus.PENDING


class FakeDAGEngine:
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
                self.nodes[dep].status == FakeTaskStatus.COMPLETED
                for dep in node.dependencies
            ):
                ready.append(task_id)
        return ready

    def get_node(self, node_id: str) -> Optional[FakeDAGNode]:
        return self.nodes.get(node_id)

    def update_node_status(self, node_id: str, status: FakeTaskStatus) -> None:
        self.nodes[node_id].status = status


class InMemoryCheckpointManager(CheckpointManager):
    def __init__(self) -> None:
        self.checkpoints: Dict[str, ExecutionContext] = {}

    async def save_checkpoint(self, task_id: str, context: ExecutionContext) -> None:
        self.checkpoints[task_id] = context

    async def load_checkpoint(self, task_id: str) -> Optional[ExecutionContext]:
        return self.checkpoints.get(task_id)

    async def delete_checkpoint(self, task_id: str) -> None:
        self.checkpoints.pop(task_id, None)


class InMemoryMemoryBackend(MemoryBackend):
    def __init__(self) -> None:
        self.entries: Dict[str, Dict[str, Any]] = {}

    async def put(self, namespace: str, key: str, value: Any) -> None:
        self.entries.setdefault(namespace, {})[key] = value

    async def get(self, namespace: str, key: str) -> Optional[Any]:
        return self.entries.get(namespace, {}).get(key)

    async def search(self, namespace: str, query: str, limit: int = 10) -> List[Dict[str, Any]]:
        ns = self.entries.get(namespace, {})
        return [
            {"key": k, "value": v, "namespace": namespace, "similarity": 1.0}
            for k, v in ns.items()
            if query in str(v)
        ][:limit]

    async def delete(self, namespace: str, key: str) -> bool:
        ns = self.entries.get(namespace, {})
        return ns.pop(key, None) is not None

    async def clear(self, namespace: str) -> int:
        count = len(self.entries.get(namespace, {}))
        self.entries.pop(namespace, None)
        return count

    async def exists(self, namespace: str, key: str) -> bool:
        return key in self.entries.get(namespace, {})

    async def get_all(self, namespace: str) -> Dict[str, Any]:
        return dict(self.entries.get(namespace, {}))


class ControlledWorkerSandbox(WorkerSandbox):
    def __init__(
        self,
        failing_tasks: Optional[set[str]] = None,
        fail_then_succeed: Optional[set[str]] = None,
    ) -> None:
        self.failing_tasks = failing_tasks or set()
        self.fail_then_succeed = fail_then_succeed or set()
        self.execution_order: List[str] = []
        self.attempt_counts: Dict[str, int] = {}

    async def execute(self, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        self.execution_order.append(task_id)
        self.attempt_counts[task_id] = self.attempt_counts.get(task_id, 0) + 1
        if task_data.get("repair_attempt"):
            return {"task_id": task_id, "ok": True, "repair_attempt": True}
        if task_id in self.fail_then_succeed and self.attempt_counts[task_id] <= 1:
            raise RuntimeError(f"task {task_id} transiently failed")
        if task_id in self.failing_tasks:
            raise RuntimeError(f"task {task_id} failed")
        return {"task_id": task_id, "ok": True}

    async def verify(self, task_id: str, result: Dict[str, Any]) -> bool:
        return True


class AsyncEventCollector(BaseEventBus):
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
            events = [e for e in events if e.event_type == event_type]
        if workflow_id is not None:
            events = [e for e in events if e.workflow_id == workflow_id]
        return events

    async def clear(self) -> None:
        self.events.clear()


class VerifyingDefectRepairPipeline:
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
        return status, repaired_code if status == RepairStatus.SUCCESS else None

    def get_repair_history(self, task_id: str) -> List[RepairResult]:
        return self._history.get(task_id, [])


@dataclass
class P3Harness:
    dag: FakeDAGEngine
    scheduler: SchedulerEngine
    state_machine: StateMachine
    event_bus: AsyncEventCollector
    checkpoint_manager: InMemoryCheckpointManager
    sandbox: ControlledWorkerSandbox
    task_executor: TaskExecutor
    memory_backend: InMemoryMemoryBackend
    coordinator: WorkflowCoordinator
    workflow_id: str = "wf-p3"


def _build_p3_harness(
    failing_tasks: Optional[set[str]] = None,
    fail_then_succeed: Optional[set[str]] = None,
    max_retries: int = 0,
    enable_defect_repair: bool = False,
    include_repair_code: bool = False,
    with_memory: bool = True,
) -> P3Harness:
    dag = FakeDAGEngine()
    extract_metadata = {"workflow_id": "wf-p3"}
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
            metadata={"workflow_id": "wf-p3"},
        )
    )
    dag.add_node(
        FakeDAGNode(
            node_id="load",
            task_type="io",
            dependencies=[],
            metadata={"workflow_id": "wf-p3"},
        )
    )
    dag.add_edge("extract", "transform")
    dag.add_edge("transform", "load")

    scheduler = SchedulerEngine(max_concurrent_tasks=2)
    state_machine = StateMachine()
    event_bus = AsyncEventCollector()
    checkpoint_manager = InMemoryCheckpointManager()
    sandbox = ControlledWorkerSandbox(
        failing_tasks=failing_tasks,
        fail_then_succeed=fail_then_succeed,
    )

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

    memory_backend = InMemoryMemoryBackend() if with_memory else None

    coordinator = WorkflowCoordinator(
        dag_engine=dag,
        scheduler=scheduler,
        task_executor=task_executor,
        event_bus=event_bus,
        state_machine=state_machine,
        recovery_engine=recovery_engine if enable_defect_repair else None,
        memory_backend=memory_backend,
    )

    return P3Harness(
        dag=dag,
        scheduler=scheduler,
        state_machine=state_machine,
        event_bus=event_bus,
        checkpoint_manager=checkpoint_manager,
        sandbox=sandbox,
        task_executor=task_executor,
        memory_backend=memory_backend,
        coordinator=coordinator,
    )


# ---------------------------------------------------------------------------
# P3-1: Memory write-back tests
# ---------------------------------------------------------------------------


def test_memory_write_back_on_task_completion() -> None:
    """Completed tasks should automatically write results to memory backend."""
    harness = _build_p3_harness()

    result = asyncio.run(
        harness.coordinator.run_workflow(workflow_id=harness.workflow_id)
    )

    assert result.success is True
    assert result.completed_tasks == ["extract", "transform", "load"]

    entries = asyncio.run(
        harness.memory_backend.get_all(namespace=harness.workflow_id)
    )
    assert "task:extract:completed" in entries
    assert "task:transform:completed" in entries
    assert "task:load:completed" in entries

    extract_record = entries["task:extract:completed"]
    assert extract_record["type"] == "task_execution"
    assert extract_record["outcome"] == "completed"
    assert extract_record["task_id"] == "extract"


def test_memory_write_back_on_recovery_success() -> None:
    """Recovered tasks should write recovery records to memory backend."""
    harness = _build_p3_harness(
        failing_tasks={"extract"},
        max_retries=0,
        enable_defect_repair=True,
        include_repair_code=True,
    )

    result = asyncio.run(
        harness.coordinator.run_workflow(workflow_id=harness.workflow_id)
    )

    assert result.success is True

    entries = asyncio.run(
        harness.memory_backend.get_all(namespace=harness.workflow_id)
    )
    recovery_keys = [k for k in entries if k.startswith("recovery:")]
    assert len(recovery_keys) >= 1

    for key in recovery_keys:
        record = entries[key]
        assert record["type"] == "task_recovery"
        assert record["task_id"] == "extract"


def test_no_memory_write_back_when_backend_is_none() -> None:
    """When no memory backend is provided, no write-back should occur."""
    harness = _build_p3_harness(with_memory=False)

    result = asyncio.run(
        harness.coordinator.run_workflow(workflow_id=harness.workflow_id)
    )

    assert result.success is True
    assert harness.memory_backend is None


def test_memory_write_back_is_best_effort() -> None:
    """Memory write-back failures should not affect workflow execution."""

    class FailingMemoryBackend(MemoryBackend):
        async def put(self, namespace, key, value):
            raise RuntimeError("storage unavailable")

        async def get(self, namespace, key):
            return None

        async def search(self, namespace, query, limit=10):
            return []

        async def delete(self, namespace, key):
            return False

        async def clear(self, namespace):
            return 0

        async def exists(self, namespace, key):
            return False

        async def get_all(self, namespace):
            return {}

    dag = FakeDAGEngine()
    dag.add_node(
        FakeDAGNode(
            node_id="task_a",
            task_type="io",
            dependencies=[],
            metadata={"workflow_id": "wf-p3"},
        )
    )

    scheduler = SchedulerEngine(max_concurrent_tasks=2)
    state_machine = StateMachine()
    event_bus = AsyncEventCollector()
    checkpoint_manager = InMemoryCheckpointManager()
    sandbox = ControlledWorkerSandbox()

    task_executor = TaskExecutor(
        dag_engine=dag,
        scheduler=scheduler,
        worker_sandbox=sandbox,
        event_bus=event_bus,
        state_machine=state_machine,
        checkpoint_manager=checkpoint_manager,
        max_retries=0,
    )

    failing_memory = FailingMemoryBackend()
    coordinator = WorkflowCoordinator(
        dag_engine=dag,
        scheduler=scheduler,
        task_executor=task_executor,
        event_bus=event_bus,
        state_machine=state_machine,
        memory_backend=failing_memory,
    )

    result = asyncio.run(coordinator.run_workflow(workflow_id="wf-p3"))

    assert result.success is True
    assert result.completed_tasks == ["task_a"]


# ---------------------------------------------------------------------------
# P3-2: Resume from checkpoint tests
# ---------------------------------------------------------------------------


def test_resume_workflow_skips_completed_tasks() -> None:
    """resume_workflow should skip tasks already completed in checkpoint."""
    harness = _build_p3_harness()

    result = asyncio.run(
        harness.coordinator.run_workflow(workflow_id=harness.workflow_id)
    )
    assert result.success is True
    assert len(harness.sandbox.execution_order) == 3

    new_scheduler = SchedulerEngine(max_concurrent_tasks=2)
    new_state_machine = StateMachine()
    new_event_bus = AsyncEventCollector()
    new_sandbox = ControlledWorkerSandbox()

    for node_id, node in harness.dag.nodes.items():
        new_scheduler.add_task(
            task_id=node_id,
            priority=0,
            dependencies=list(node.dependencies),
        )
        new_state_machine.initialize(node_id, TaskState.PENDING)

    new_task_executor = TaskExecutor(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        worker_sandbox=new_sandbox,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
        checkpoint_manager=harness.checkpoint_manager,
        max_retries=0,
    )

    new_coordinator = WorkflowCoordinator(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        task_executor=new_task_executor,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
    )

    resumed = asyncio.run(
        new_coordinator.resume_workflow(workflow_id=harness.workflow_id)
    )

    assert resumed.success is True
    assert len(new_sandbox.execution_order) == 0


def test_resume_workflow_continues_incomplete_tasks() -> None:
    """resume_workflow should continue tasks not yet completed."""
    harness = _build_p3_harness()

    asyncio.run(
        harness.coordinator.run_workflow(workflow_id=harness.workflow_id)
    )

    for node_id in ["transform", "load"]:
        node = harness.dag.get_node(node_id)
        node.status = FakeTaskStatus.PENDING
        harness.checkpoint_manager.checkpoints.pop(node_id, None)

    new_scheduler = SchedulerEngine(max_concurrent_tasks=2)
    new_state_machine = StateMachine()
    new_event_bus = AsyncEventCollector()
    new_sandbox = ControlledWorkerSandbox()

    for node_id, node in harness.dag.nodes.items():
        new_scheduler.add_task(
            task_id=node_id,
            priority=0,
            dependencies=list(node.dependencies),
        )
        new_state_machine.initialize(node_id, TaskState.PENDING)

    new_task_executor = TaskExecutor(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        worker_sandbox=new_sandbox,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
        checkpoint_manager=harness.checkpoint_manager,
        max_retries=0,
    )

    new_coordinator = WorkflowCoordinator(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        task_executor=new_task_executor,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
    )

    resumed = asyncio.run(
        new_coordinator.resume_workflow(workflow_id=harness.workflow_id)
    )

    assert resumed.success is True
    assert "transform" in resumed.completed_tasks
    assert "load" in resumed.completed_tasks
    assert new_sandbox.execution_order == ["transform", "load"]


def test_resume_workflow_with_no_checkpoints_runs_all() -> None:
    """resume_workflow with no checkpoints should run all tasks normally."""
    harness = _build_p3_harness()
    harness.checkpoint_manager.checkpoints.clear()

    result = asyncio.run(
        harness.coordinator.resume_workflow(workflow_id=harness.workflow_id)
    )

    assert result.success is True
    assert len(result.completed_tasks) == 3


# ---------------------------------------------------------------------------
# P3-3: Crash/restart recovery tests
# ---------------------------------------------------------------------------


def test_workflow_crash_restart_recovers_from_persisted_state() -> None:
    """A crashed workflow should recover when a new coordinator is created
    with the same checkpoint manager and a fresh state machine."""
    harness = _build_p3_harness()

    partial_result = asyncio.run(
        harness.coordinator.run_workflow(workflow_id=harness.workflow_id)
    )
    assert partial_result.success is True

    harness.dag.get_node("transform").status = FakeTaskStatus.PENDING
    harness.dag.get_node("load").status = FakeTaskStatus.PENDING
    harness.checkpoint_manager.checkpoints.pop("transform", None)
    harness.checkpoint_manager.checkpoints.pop("load", None)

    new_scheduler = SchedulerEngine(max_concurrent_tasks=2)
    new_state_machine = StateMachine()
    new_sandbox = ControlledWorkerSandbox()
    new_event_bus = AsyncEventCollector()

    for node_id, node in harness.dag.nodes.items():
        new_scheduler.add_task(
            task_id=node_id,
            priority=0,
            dependencies=list(node.dependencies),
        )
        new_state_machine.initialize(node_id, TaskState.PENDING)

    new_task_executor = TaskExecutor(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        worker_sandbox=new_sandbox,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
        checkpoint_manager=harness.checkpoint_manager,
        max_retries=0,
    )

    new_coordinator = WorkflowCoordinator(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        task_executor=new_task_executor,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
    )

    recovered = asyncio.run(
        new_coordinator.resume_workflow(workflow_id=harness.workflow_id)
    )

    assert recovered.success is True
    assert "transform" in recovered.completed_tasks
    assert "load" in recovered.completed_tasks
    assert "extract" not in new_sandbox.execution_order
    assert new_sandbox.execution_order == ["transform", "load"]


def test_workflow_crash_mid_task_resumes_correctly() -> None:
    """A task that was running when crash occurred should re-execute."""
    harness = _build_p3_harness()

    asyncio.run(
        harness.coordinator.run_workflow(workflow_id=harness.workflow_id)
    )

    harness.dag.get_node("transform").status = FakeTaskStatus.RUNNING
    harness.checkpoint_manager.checkpoints.pop("transform", None)
    harness.dag.get_node("load").status = FakeTaskStatus.PENDING
    harness.checkpoint_manager.checkpoints.pop("load", None)

    new_scheduler = SchedulerEngine(max_concurrent_tasks=2)
    new_state_machine = StateMachine()
    new_sandbox = ControlledWorkerSandbox()
    new_event_bus = AsyncEventCollector()

    for node_id, node in harness.dag.nodes.items():
        new_scheduler.add_task(
            task_id=node_id,
            priority=0,
            dependencies=list(node.dependencies),
        )
        new_state_machine.initialize(node_id, TaskState.PENDING)

    new_task_executor = TaskExecutor(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        worker_sandbox=new_sandbox,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
        checkpoint_manager=harness.checkpoint_manager,
        max_retries=0,
    )

    new_coordinator = WorkflowCoordinator(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        task_executor=new_task_executor,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
    )

    recovered = asyncio.run(
        new_coordinator.resume_workflow(workflow_id=harness.workflow_id)
    )

    assert recovered.success is True
    assert "transform" in new_sandbox.execution_order
    assert "load" in new_sandbox.execution_order


def test_crash_recovery_with_memory_write_back() -> None:
    """Crash recovery should also write results to memory backend."""
    harness = _build_p3_harness()

    asyncio.run(
        harness.coordinator.run_workflow(workflow_id=harness.workflow_id)
    )

    harness.dag.get_node("load").status = FakeTaskStatus.PENDING
    harness.checkpoint_manager.checkpoints.pop("load", None)

    new_scheduler = SchedulerEngine(max_concurrent_tasks=2)
    new_state_machine = StateMachine()
    new_sandbox = ControlledWorkerSandbox()
    new_event_bus = AsyncEventCollector()
    new_memory = InMemoryMemoryBackend()

    for node_id, node in harness.dag.nodes.items():
        new_scheduler.add_task(
            task_id=node_id,
            priority=0,
            dependencies=list(node.dependencies),
        )
        new_state_machine.initialize(node_id, TaskState.PENDING)

    new_task_executor = TaskExecutor(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        worker_sandbox=new_sandbox,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
        checkpoint_manager=harness.checkpoint_manager,
        max_retries=0,
    )

    new_coordinator = WorkflowCoordinator(
        dag_engine=harness.dag,
        scheduler=new_scheduler,
        task_executor=new_task_executor,
        event_bus=new_event_bus,
        state_machine=new_state_machine,
        memory_backend=new_memory,
    )

    recovered = asyncio.run(
        new_coordinator.resume_workflow(workflow_id=harness.workflow_id)
    )

    assert recovered.success is True

    entries = asyncio.run(new_memory.get_all(namespace=harness.workflow_id))
    assert "task:load:completed" in entries
