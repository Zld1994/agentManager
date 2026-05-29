"""E2E tests for runtime workflow coordination loop."""

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
    """Deterministic worker sandbox for success/failure paths."""

    def __init__(self, failing_tasks: Optional[set[str]] = None) -> None:
        self.failing_tasks = failing_tasks or set()
        self.execution_order: List[str] = []

    async def execute(self, task_id: str, task_data: Dict[str, Any]) -> Dict[str, Any]:
        self.execution_order.append(task_id)
        if task_id in self.failing_tasks:
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
    coordinator: WorkflowCoordinator
    workflow_id: str = "wf-e2e"


def _build_harness(failing_tasks: Optional[set[str]] = None) -> WorkflowHarness:
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
    dag.add_node(
        FakeDAGNode(
            node_id="load",
            task_type="io",
            dependencies=[],
            metadata={"workflow_id": "wf-e2e"},
        )
    )
    dag.add_edge("extract", "transform")
    dag.add_edge("transform", "load")

    scheduler = SchedulerEngine(max_concurrent_tasks=2)
    state_machine = StateMachine()
    event_bus = AsyncEventCollector()
    checkpoint_manager = InMemoryCheckpointManager()
    sandbox = StubWorkerSandbox(failing_tasks=failing_tasks)

    task_executor = TaskExecutor(
        dag_engine=dag,
        scheduler=scheduler,
        worker_sandbox=sandbox,
        event_bus=event_bus,
        state_machine=state_machine,
        checkpoint_manager=checkpoint_manager,
        max_retries=0,
    )
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
        coordinator=coordinator,
    )


def test_workflow_coordinator_runs_end_to_end_successfully() -> None:
    """Coordinator should run a DAG end-to-end and emit workflow/task events."""
    harness = _build_harness()

    result = asyncio.run(harness.coordinator.run_workflow(workflow_id=harness.workflow_id))

    assert result.success is True
    assert result.completed_tasks == ["extract", "transform", "load"]
    assert result.failed_tasks == []
    assert harness.sandbox.execution_order == ["extract", "transform", "load"]

    assert harness.dag.get_node("extract").status == FakeTaskStatus.COMPLETED
    assert harness.dag.get_node("transform").status == FakeTaskStatus.COMPLETED
    assert harness.dag.get_node("load").status == FakeTaskStatus.COMPLETED

    assert harness.state_machine.get_state("extract") == TaskState.COMPLETED
    assert harness.state_machine.get_state("transform") == TaskState.COMPLETED
    assert harness.state_machine.get_state("load") == TaskState.COMPLETED

    assert harness.scheduler.get_task_status("extract") == "completed"
    assert harness.scheduler.get_task_status("transform") == "completed"
    assert harness.scheduler.get_task_status("load") == "completed"

    assert harness.checkpoint_manager.checkpoints["extract"].status == ExecutionStatus.COMPLETED
    assert harness.checkpoint_manager.checkpoints["transform"].status == ExecutionStatus.COMPLETED
    assert harness.checkpoint_manager.checkpoints["load"].status == ExecutionStatus.COMPLETED

    event_types = [event.event_type for event in harness.event_bus.events]
    assert EventType.WORKFLOW_STARTED in event_types
    assert EventType.WORKFLOW_COMPLETED in event_types
    assert event_types.count(EventType.TASK_STARTED) == 3
    assert event_types.count(EventType.TASK_COMPLETED) == 3


def test_workflow_coordinator_traces_workflow_run(monkeypatch) -> None:
    """Coordinator should create a workflow-level observability span."""
    spans = []

    class RecordingSpan:
        def __init__(self, name, **attributes):
            self.name = name
            self.attributes = dict(attributes)

        def __enter__(self):
            spans.append(self)
            return self

        def __exit__(self, exc_type, exc, traceback):
            return False

        def set_attribute(self, key, value):
            self.attributes[key] = value

    monkeypatch.setattr(
        "agentManager.runtime.workflow_coordinator.trace_operation",
        lambda name, **attributes: RecordingSpan(name, **attributes),
    )
    harness = _build_harness()

    asyncio.run(harness.coordinator.run_workflow(workflow_id=harness.workflow_id))

    assert spans[0].name == "workflow.run"
    assert spans[0].attributes["workflow_id"] == harness.workflow_id
    assert spans[0].attributes["task_count"] == 3


def test_workflow_coordinator_closes_trace_on_unexpected_error(monkeypatch) -> None:
    """Coordinator spans should close and record unexpected exceptions."""
    spans = []

    class RecordingSpan:
        def __init__(self, name, **attributes):
            self.name = name
            self.attributes = dict(attributes)
            self.error = None

        def __enter__(self):
            spans.append(self)
            return self

        def __exit__(self, exc_type, exc, traceback):
            if exc is not None:
                self.error = str(exc)
            return False

        def set_attribute(self, key, value):
            self.attributes[key] = value

    monkeypatch.setattr(
        "agentManager.runtime.workflow_coordinator.trace_operation",
        lambda name, **attributes: RecordingSpan(name, **attributes),
    )
    harness = _build_harness()
    monkeypatch.setattr(
        harness.coordinator,
        "_register_missing_tasks",
        lambda: (_ for _ in ()).throw(RuntimeError("registration failed")),
    )

    try:
        asyncio.run(harness.coordinator.run_workflow(workflow_id=harness.workflow_id))
    except RuntimeError:
        pass

    assert spans[0].error == "registration failed"


def test_workflow_coordinator_marks_failures_and_emits_workflow_failed() -> None:
    """Coordinator should mark failed tasks and publish WORKFLOW_FAILED."""
    harness = _build_harness(failing_tasks={"transform"})

    result = asyncio.run(harness.coordinator.run_workflow(workflow_id=harness.workflow_id))

    assert result.success is False
    assert result.completed_tasks == ["extract"]
    assert "transform" in result.failed_tasks
    assert harness.dag.get_node("extract").status == FakeTaskStatus.COMPLETED
    assert harness.dag.get_node("transform").status == FakeTaskStatus.FAILED
    assert harness.scheduler.get_task_status("transform") == "failed"
    assert harness.checkpoint_manager.checkpoints["transform"].status == ExecutionStatus.FAILED

    event_types = [event.event_type for event in harness.event_bus.events]
    assert EventType.WORKFLOW_STARTED in event_types
    assert EventType.WORKFLOW_FAILED in event_types
    assert EventType.WORKFLOW_COMPLETED not in event_types
