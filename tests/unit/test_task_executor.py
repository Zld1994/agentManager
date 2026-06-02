"""Unit tests for TaskExecutor.

Comprehensive test suite for the TaskExecutor class covering:
- Task execution lifecycle
- Error handling and retries
- Event publishing
- Checkpoint management
- State transitions
"""

import pytest

from agentManager.runtime.task_executor import (
    TaskExecutor,
    CheckpointManager,
    WorkerSandbox,
)
from agentManager.runtime.execution_context import (
    ExecutionContext,
    ExecutionStatus,
)
from agentManager.engine.dag import DAGEngine, DAGNode
from agentManager.engine.scheduler import SchedulerEngine
from agentManager.engine.event_bus.base import BaseEventBus, Event, EventType
from agentManager.engine.state_manager import StateMachine, TaskState


class MockCheckpointManager(CheckpointManager):
    """Mock checkpoint manager for testing."""

    def __init__(self):
        """Initialize mock checkpoint manager."""
        self.checkpoints = {}

    async def save_checkpoint(self, task_id: str, context: ExecutionContext) -> None:
        """Save checkpoint."""
        self.checkpoints[task_id] = context

    async def load_checkpoint(self, task_id: str):
        """Load checkpoint."""
        return self.checkpoints.get(task_id)

    async def delete_checkpoint(self, task_id: str) -> None:
        """Delete checkpoint."""
        if task_id in self.checkpoints:
            del self.checkpoints[task_id]


class MockWorkerSandbox(WorkerSandbox):
    """Mock worker sandbox for testing."""

    def __init__(self, should_fail: bool = False, verify_fails: bool = False):
        """Initialize mock sandbox.

        Args:
            should_fail: Whether execution should fail
            verify_fails: Whether verification should fail
        """
        self.should_fail = should_fail
        self.verify_fails = verify_fails
        self.execute_count = 0
        self.verify_count = 0

    async def execute(self, task_id: str, task_data: dict) -> dict:
        """Execute task."""
        self.execute_count += 1
        if self.should_fail:
            raise Exception("Execution failed")
        return {"result": "success", "task_id": task_id}

    async def verify(self, task_id: str, result: dict) -> bool:
        """Verify result."""
        self.verify_count += 1
        if self.verify_fails:
            return False
        return True


class MockEventBus(BaseEventBus):
    """Mock event bus for testing."""

    def __init__(self):
        """Initialize mock event bus."""
        self.events = []
        self.subscribers = {}

    async def subscribe(self, event_type, callback, workflow_id=None):
        """Subscribe to events."""
        key = (event_type, workflow_id)
        if key not in self.subscribers:
            self.subscribers[key] = []
        self.subscribers[key].append(callback)

    async def publish(self, event: Event) -> None:
        """Publish event."""
        self.events.append(event)

    async def unsubscribe(self, event_type, callback, workflow_id=None):
        """Unsubscribe from events."""
        key = (event_type, workflow_id)
        if key in self.subscribers:
            self.subscribers[key].remove(callback)

    async def get_events(self, event_type=None, workflow_id=None):
        """Get events."""
        events = self.events
        if event_type:
            events = [e for e in events if e.event_type == event_type]
        if workflow_id:
            events = [e for e in events if e.workflow_id == workflow_id]
        return events

    async def clear(self) -> None:
        """Clear all events."""
        self.events = []
        self.subscribers = {}


@pytest.fixture
def dag_engine():
    """Create DAG engine fixture."""
    return DAGEngine()


@pytest.fixture
def scheduler():
    """Create scheduler fixture."""
    return SchedulerEngine(max_concurrent_tasks=10)


@pytest.fixture
def worker_sandbox():
    """Create worker sandbox fixture."""
    return MockWorkerSandbox()


@pytest.fixture
def event_bus():
    """Create event bus fixture."""
    return MockEventBus()


@pytest.fixture
def state_machine():
    """Create state machine fixture."""
    return StateMachine()


@pytest.fixture
def checkpoint_manager():
    """Create checkpoint manager fixture."""
    return MockCheckpointManager()


@pytest.fixture
def task_executor(
    dag_engine, scheduler, worker_sandbox, event_bus, state_machine, checkpoint_manager
):
    """Create task executor fixture."""
    return TaskExecutor(
        dag_engine=dag_engine,
        scheduler=scheduler,
        worker_sandbox=worker_sandbox,
        event_bus=event_bus,
        state_machine=state_machine,
        checkpoint_manager=checkpoint_manager,
        max_retries=2,
    )


@pytest.fixture
def sample_task():
    """Create sample task fixture."""
    return DAGNode(
        node_id="task_1",
        task_type="test_task",
        metadata={"workflow_id": "workflow_1", "param1": "value1"},
    )


class TestTaskExecutorInitialization:
    """Test TaskExecutor initialization."""

    def test_initialization(self, task_executor):
        """Test TaskExecutor initialization."""
        assert task_executor.max_retries == 2
        assert task_executor.execution_contexts == {}

    def test_initialization_with_custom_retries(
        self, dag_engine, scheduler, worker_sandbox, event_bus, state_machine, checkpoint_manager
    ):
        """Test initialization with custom retry count."""
        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=worker_sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
            max_retries=5,
        )
        assert executor.max_retries == 5


class TestTaskExecution:
    """Test task execution."""

    @pytest.mark.asyncio
    async def test_successful_task_execution(self, task_executor, sample_task):
        """Test successful task execution."""
        context = await task_executor.run_task(sample_task)

        assert context.task_id == "task_1"
        assert context.status == ExecutionStatus.COMPLETED
        assert context.result == {"result": "success", "task_id": "task_1"}
        assert context.error is None
        assert context.retry_count == 0

    @pytest.mark.asyncio
    async def test_run_task_traces_task_execution(self, task_executor, sample_task, monkeypatch):
        """Task execution should create an observability span."""
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
            "agentManager.runtime.task_executor.trace_operation",
            lambda name, **attributes: RecordingSpan(name, **attributes),
        )

        await task_executor.run_task(sample_task)

        assert spans[0].name == "task.run"
        assert spans[0].attributes["task_id"] == "task_1"
        assert spans[0].attributes["workflow_id"] == "workflow_1"

    @pytest.mark.asyncio
    async def test_task_execution_with_retry(
        self, dag_engine, scheduler, event_bus, state_machine, checkpoint_manager
    ):
        """Test task execution with retry on first failure."""
        # Create sandbox that fails once then succeeds
        sandbox = MockWorkerSandbox()
        sandbox.should_fail = True

        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
            max_retries=2,
        )

        task = DAGNode(
            node_id="task_1",
            task_type="test_task",
            metadata={"workflow_id": "workflow_1"},
        )

        # Should fail because sandbox always fails
        with pytest.raises(Exception):
            await executor.run_task(task)

        assert sandbox.execute_count == 3  # Initial + 2 retries

    @pytest.mark.asyncio
    async def test_task_execution_failure(
        self, dag_engine, scheduler, event_bus, state_machine, checkpoint_manager
    ):
        """Test task execution failure."""
        sandbox = MockWorkerSandbox(should_fail=True)

        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
            max_retries=1,
        )

        task = DAGNode(
            node_id="task_1",
            task_type="test_task",
            metadata={"workflow_id": "workflow_1"},
        )

        with pytest.raises(Exception):
            await executor.run_task(task)

        context = executor.get_execution_context("task_1")
        assert context.status == ExecutionStatus.FAILED
        assert context.error is not None
        assert context.retry_count == 2  # Initial + 1 retry

    @pytest.mark.asyncio
    async def test_execute_adapter_runs_repaired_code(
        self, task_executor, sample_task, worker_sandbox
    ):
        """Test repair compatibility adapter executes and verifies code."""
        await task_executor.run_task(sample_task)

        result = await task_executor.execute("task_1", "x = 1")

        assert result["success"] is True
        assert worker_sandbox.execute_count == 2
        context = task_executor.get_execution_context("task_1")
        assert context.metadata["last_repaired_code"] == "x = 1"
        assert context.metadata["last_repair_result"]["task_id"] == "task_1"

    @pytest.mark.asyncio
    async def test_execute_adapter_returns_failed_verification(
        self, dag_engine, scheduler, event_bus, state_machine, checkpoint_manager
    ):
        """Test repair compatibility adapter reports verification failures."""
        sandbox = MockWorkerSandbox(verify_fails=True)
        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
        )

        result = await executor.execute("task_1", "x = 1")

        assert result["success"] is False
        assert result["error"] == "Verification failed"
        assert (
            executor.get_execution_context("task_1").metadata["repair_verification_failed"] is True
        )

    @pytest.mark.asyncio
    async def test_execute_adapter_propagates_sandbox_exception(
        self, dag_engine, scheduler, event_bus, state_machine, checkpoint_manager
    ):
        """Test repair compatibility adapter lets sandbox exceptions surface."""
        sandbox = MockWorkerSandbox(should_fail=True)
        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
        )

        with pytest.raises(Exception, match="Execution failed"):
            await executor.execute("task_1", "x = 1")


class TestStateTransitions:
    """Test state transitions during execution."""

    @pytest.mark.asyncio
    async def test_state_transitions_on_success(self, task_executor, sample_task):
        """Test state transitions on successful execution."""
        await task_executor.run_task(sample_task)

        history = task_executor.state_machine.get_history("task_1")
        states = [t.to_state for t in history]

        # Should transition through IMPLEMENTING, VERIFYING, COMPLETED
        assert TaskState.IMPLEMENTING in states
        assert TaskState.VERIFYING in states
        assert TaskState.COMPLETED in states

    @pytest.mark.asyncio
    async def test_state_transitions_on_failure(
        self, dag_engine, scheduler, event_bus, state_machine, checkpoint_manager
    ):
        """Test state transitions on failure."""
        sandbox = MockWorkerSandbox(should_fail=True)

        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
            max_retries=0,
        )

        task = DAGNode(
            node_id="task_1",
            task_type="test_task",
            metadata={"workflow_id": "workflow_1"},
        )

        with pytest.raises(Exception):
            await executor.run_task(task)

        history = executor.state_machine.get_history("task_1")
        states = [t.to_state for t in history]

        # Should transition through IMPLEMENTING, VERIFYING, FAILED
        assert TaskState.IMPLEMENTING in states
        assert TaskState.VERIFYING in states
        assert TaskState.FAILED in states


class TestEventPublishing:
    """Test event publishing."""

    @pytest.mark.asyncio
    async def test_task_started_event(self, task_executor, sample_task):
        """Test TASK_STARTED event is published."""
        await task_executor.run_task(sample_task)

        events = await task_executor.event_bus.get_events(event_type=EventType.TASK_STARTED)
        assert len(events) == 1
        assert events[0].payload["task_id"] == "task_1"

    @pytest.mark.asyncio
    async def test_task_completed_event(self, task_executor, sample_task):
        """Test TASK_COMPLETED event is published."""
        await task_executor.run_task(sample_task)

        events = await task_executor.event_bus.get_events(event_type=EventType.TASK_COMPLETED)
        assert len(events) == 1
        assert events[0].payload["task_id"] == "task_1"
        assert events[0].payload["status"] == "completed"

    @pytest.mark.asyncio
    async def test_task_failed_event(
        self, dag_engine, scheduler, event_bus, state_machine, checkpoint_manager
    ):
        """Test TASK_FAILED event is published."""
        sandbox = MockWorkerSandbox(should_fail=True)

        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
            max_retries=0,
        )

        task = DAGNode(
            node_id="task_1",
            task_type="test_task",
            metadata={"workflow_id": "workflow_1"},
        )

        with pytest.raises(Exception):
            await executor.run_task(task)

        events = await executor.event_bus.get_events(event_type=EventType.TASK_FAILED)
        assert len(events) == 1
        assert events[0].payload["task_id"] == "task_1"
        assert events[0].payload["status"] == "failed"


class TestCheckpointManagement:
    """Test checkpoint management."""

    @pytest.mark.asyncio
    async def test_checkpoint_saved_on_success(self, task_executor, sample_task):
        """Test checkpoint is saved on successful execution."""
        await task_executor.run_task(sample_task)

        checkpoint = await task_executor.checkpoint_manager.load_checkpoint("task_1")
        assert checkpoint is not None
        assert checkpoint.task_id == "task_1"
        assert checkpoint.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_checkpoint_saved_on_failure(
        self, dag_engine, scheduler, event_bus, state_machine, checkpoint_manager
    ):
        """Test checkpoint is saved on failure."""
        sandbox = MockWorkerSandbox(should_fail=True)

        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
            max_retries=0,
        )

        task = DAGNode(
            node_id="task_1",
            task_type="test_task",
            metadata={"workflow_id": "workflow_1"},
        )

        with pytest.raises(Exception):
            await executor.run_task(task)

        checkpoint = await executor.checkpoint_manager.load_checkpoint("task_1")
        assert checkpoint is not None
        assert checkpoint.status == ExecutionStatus.FAILED

    @pytest.mark.asyncio
    async def test_checkpoint_contains_metadata(self, task_executor, sample_task):
        """Test checkpoint contains execution metadata."""
        await task_executor.run_task(sample_task)

        checkpoint = await task_executor.checkpoint_manager.load_checkpoint("task_1")
        assert checkpoint.workflow_id == "workflow_1"
        assert checkpoint.metadata["param1"] == "value1"
        assert checkpoint.start_time is not None
        assert checkpoint.end_time is not None


class TestExecutionContextManagement:
    """Test execution context management."""

    @pytest.mark.asyncio
    async def test_get_execution_context(self, task_executor, sample_task):
        """Test retrieving execution context."""
        await task_executor.run_task(sample_task)

        context = task_executor.get_execution_context("task_1")
        assert context is not None
        assert context.task_id == "task_1"
        assert context.status == ExecutionStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_get_all_contexts(
        self, dag_engine, scheduler, worker_sandbox, event_bus, state_machine, checkpoint_manager
    ):
        """Test retrieving all execution contexts."""
        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=worker_sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
        )

        task1 = DAGNode(
            node_id="task_1",
            task_type="test_task",
            metadata={"workflow_id": "workflow_1"},
        )
        task2 = DAGNode(
            node_id="task_2",
            task_type="test_task",
            metadata={"workflow_id": "workflow_1"},
        )

        await executor.run_task(task1)
        await executor.run_task(task2)

        contexts = executor.get_all_contexts()
        assert len(contexts) == 2
        assert "task_1" in contexts
        assert "task_2" in contexts

    @pytest.mark.asyncio
    async def test_cleanup_execution_context(self, task_executor, sample_task):
        """Test cleaning up execution context."""
        await task_executor.run_task(sample_task)

        assert task_executor.get_execution_context("task_1") is not None

        await task_executor.cleanup("task_1")

        assert task_executor.get_execution_context("task_1") is None


class TestVerificationFailure:
    """Test verification failure handling."""

    @pytest.mark.asyncio
    async def test_verification_failure_triggers_retry(
        self, dag_engine, scheduler, event_bus, state_machine, checkpoint_manager
    ):
        """Test that verification failure triggers retry."""
        sandbox = MockWorkerSandbox(verify_fails=True)

        executor = TaskExecutor(
            dag_engine=dag_engine,
            scheduler=scheduler,
            worker_sandbox=sandbox,
            event_bus=event_bus,
            state_machine=state_machine,
            checkpoint_manager=checkpoint_manager,
            max_retries=2,
        )

        task = DAGNode(
            node_id="task_1",
            task_type="test_task",
            metadata={"workflow_id": "workflow_1"},
        )

        with pytest.raises(Exception):
            await executor.run_task(task)

        # Should have attempted execution 3 times (initial + 2 retries)
        assert sandbox.execute_count == 3
        assert sandbox.verify_count == 3


class TestExecutionContextData:
    """Test ExecutionContext data class."""

    def test_execution_context_initialization(self):
        """Test ExecutionContext initialization."""
        context = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
        )
        assert context.task_id == "task_1"
        assert context.workflow_id == "workflow_1"
        assert context.status == ExecutionStatus.PENDING
        assert context.retry_count == 0

    def test_mark_started(self):
        """Test marking context as started."""
        context = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
        )
        context.mark_started()
        assert context.status == ExecutionStatus.IMPLEMENTING
        assert context.start_time is not None

    def test_mark_completed(self):
        """Test marking context as completed."""
        context = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
        )
        result = {"output": "test"}
        context.mark_completed(result)
        assert context.status == ExecutionStatus.COMPLETED
        assert context.result == result
        assert context.end_time is not None

    def test_mark_failed(self):
        """Test marking context as failed."""
        context = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
        )
        context.mark_failed("Test error")
        assert context.status == ExecutionStatus.FAILED
        assert context.error == "Test error"
        assert context.end_time is not None

    def test_increment_retry(self):
        """Test incrementing retry counter."""
        context = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
        )
        assert context.retry_count == 0
        context.increment_retry()
        assert context.retry_count == 1
        context.increment_retry()
        assert context.retry_count == 2

    def test_get_duration(self):
        """Test getting execution duration."""
        context = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
        )
        context.mark_started()
        duration = context.get_duration()
        assert duration is not None
        assert duration >= 0

    def test_to_dict(self):
        """Test converting context to dictionary."""
        context = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={"key": "value"},
        )
        context.mark_started()
        context.mark_completed({"result": "success"})

        data = context.to_dict()
        assert data["task_id"] == "task_1"
        assert data["workflow_id"] == "workflow_1"
        assert data["status"] == "completed"
        assert data["result"] == {"result": "success"}
        assert data["duration"] is not None
