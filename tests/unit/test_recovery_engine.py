"""Unit tests for recovery module.

Comprehensive test suite covering error classification, recovery context,
and recovery engine with all 5 recovery strategies.
"""

import pytest
from unittest.mock import Mock, AsyncMock

from agentManager.recovery.recovery_context import (
    RecoveryContext,
    FailureType,
    RecoveryStrategy,
)
from agentManager.recovery.error_classifier import ErrorClassifier
from agentManager.recovery.recovery_engine import RecoveryEngine
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.engine.event_bus.base import Event, EventType
from agentManager.runtime.execution_context import (
    ExecutionContext,
    ExecutionStatus,
)
from agentManager.defect_repair.repair_strategies import RepairResult, RepairStatus


class TestRecoveryContext:
    """Tests for RecoveryContext data class."""

    def test_recovery_context_creation(self):
        """Test creating a valid recovery context."""
        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.TIMEOUT,
            error_msg="Task execution timed out",
        )

        assert ctx.task_id == "task_1"
        assert ctx.workflow_id == "workflow_1"
        assert ctx.failure_type == FailureType.TIMEOUT
        assert ctx.error_msg == "Task execution timed out"
        assert ctx.retry_count == 0
        assert ctx.recovery_strategy is None

    def test_recovery_context_with_checkpoint(self):
        """Test recovery context with checkpoint information."""
        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.RUNTIME,
            error_msg="Runtime error occurred",
            checkpoint_id="checkpoint_123",
            event_id="event_456",
        )

        assert ctx.checkpoint_id == "checkpoint_123"
        assert ctx.event_id == "event_456"

    def test_recovery_context_missing_task_id(self):
        """Test that recovery context requires task_id."""
        with pytest.raises(ValueError, match="task_id is required"):
            RecoveryContext(
                task_id="",
                workflow_id="workflow_1",
                failure_type=FailureType.TIMEOUT,
                error_msg="Error",
            )

    def test_recovery_context_missing_workflow_id(self):
        """Test that recovery context requires workflow_id."""
        with pytest.raises(ValueError, match="workflow_id is required"):
            RecoveryContext(
                task_id="task_1",
                workflow_id="",
                failure_type=FailureType.TIMEOUT,
                error_msg="Error",
            )

    def test_recovery_context_missing_error_msg(self):
        """Test that recovery context requires error_msg."""
        with pytest.raises(ValueError, match="error_msg is required"):
            RecoveryContext(
                task_id="task_1",
                workflow_id="workflow_1",
                failure_type=FailureType.TIMEOUT,
                error_msg="",
            )

    def test_recovery_context_to_dict(self):
        """Test converting recovery context to dictionary."""
        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.NETWORK,
            error_msg="Network error",
            checkpoint_id="cp_1",
            recovery_strategy=RecoveryStrategy.RETRY,
            retry_count=2,
        )

        ctx_dict = ctx.to_dict()

        assert ctx_dict["task_id"] == "task_1"
        assert ctx_dict["workflow_id"] == "workflow_1"
        assert ctx_dict["failure_type"] == "network"
        assert ctx_dict["error_msg"] == "Network error"
        assert ctx_dict["checkpoint_id"] == "cp_1"
        assert ctx_dict["recovery_strategy"] == "retry"
        assert ctx_dict["retry_count"] == 2

    def test_recovery_context_from_dict(self):
        """Test creating recovery context from dictionary."""
        data = {
            "task_id": "task_1",
            "workflow_id": "workflow_1",
            "failure_type": "timeout",
            "error_msg": "Timeout error",
            "checkpoint_id": "cp_1",
            "recovery_strategy": "event_replay",
            "retry_count": 1,
        }

        ctx = RecoveryContext.from_dict(data)

        assert ctx.task_id == "task_1"
        assert ctx.failure_type == FailureType.TIMEOUT
        assert ctx.recovery_strategy == RecoveryStrategy.EVENT_REPLAY


class TestErrorClassifier:
    """Tests for ErrorClassifier."""

    def test_classify_timeout_error(self):
        """Test classifying timeout errors."""
        classifier = ErrorClassifier()
        error = TimeoutError("Request timed out")

        failure_type, strategy = classifier.classify(error)

        assert failure_type == FailureType.TIMEOUT
        assert strategy == RecoveryStrategy.RETRY

    def test_classify_network_error(self):
        """Test classifying network errors."""
        classifier = ErrorClassifier()
        error = ConnectionError("Connection refused")

        failure_type, strategy = classifier.classify(error)

        assert failure_type == FailureType.NETWORK
        assert strategy == RecoveryStrategy.EVENT_REPLAY

    def test_classify_syntax_error(self):
        """Test classifying syntax errors."""
        classifier = ErrorClassifier()
        error = SyntaxError("Invalid syntax")

        failure_type, strategy = classifier.classify(error)

        assert failure_type == FailureType.SYNTAX
        assert strategy == RecoveryStrategy.HITL

    def test_classify_runtime_error(self):
        """Test classifying runtime errors."""
        classifier = ErrorClassifier()
        error = RuntimeError("Runtime error occurred")

        failure_type, strategy = classifier.classify(error)

        assert failure_type == FailureType.RUNTIME
        assert strategy == RecoveryStrategy.SNAPSHOT_RESTORE

    def test_classify_attribute_error(self):
        """Test classifying attribute errors as runtime."""
        classifier = ErrorClassifier()
        error = AttributeError("'NoneType' object has no attribute 'x'")

        failure_type, strategy = classifier.classify(error)

        assert failure_type == FailureType.RUNTIME
        assert strategy == RecoveryStrategy.SNAPSHOT_RESTORE

    def test_classify_unknown_error(self):
        """Test classifying unknown errors."""
        classifier = ErrorClassifier()
        error = Exception("Some unknown error")

        failure_type, strategy = classifier.classify(error)

        assert failure_type == FailureType.UNKNOWN
        assert strategy == RecoveryStrategy.ESCALATE

    def test_classify_network_error_by_message(self):
        """Test classifying network errors by message content."""
        classifier = ErrorClassifier()
        error = Exception("DNS resolution failed")

        failure_type, strategy = classifier.classify(error)

        assert failure_type == FailureType.NETWORK
        assert strategy == RecoveryStrategy.EVENT_REPLAY


class TestRecoveryEngine:
    """Tests for RecoveryEngine."""

    @pytest.fixture
    def mock_dependencies(self):
        """Create mock dependencies for RecoveryEngine."""
        task_executor = AsyncMock()
        task_executor.get_execution_context = Mock(return_value=Mock())
        task_executor.execution_contexts = {}

        event_bus = AsyncMock()
        event_bus.get_events = AsyncMock(return_value=[])
        event_bus.publish = AsyncMock()

        state_machine = Mock(spec=StateMachine)
        state_machine.transition = Mock()

        checkpoint_manager = AsyncMock()
        checkpoint_manager.load_checkpoint = AsyncMock(return_value=None)
        checkpoint_manager.save_checkpoint = AsyncMock()

        return {
            "task_executor": task_executor,
            "event_bus": event_bus,
            "state_machine": state_machine,
            "checkpoint_manager": checkpoint_manager,
        }

    def test_recovery_engine_initialization(self, mock_dependencies):
        """Test RecoveryEngine initialization."""
        engine = RecoveryEngine(**mock_dependencies)

        assert engine.task_executor == mock_dependencies["task_executor"]
        assert engine.event_bus == mock_dependencies["event_bus"]
        assert engine.state_machine == mock_dependencies["state_machine"]
        assert engine.checkpoint_manager == mock_dependencies["checkpoint_manager"]
        assert isinstance(engine.error_classifier, ErrorClassifier)
        assert engine.recovery_history == {}

    def test_select_recovery_strategy_timeout(self, mock_dependencies):
        """Test strategy selection for timeout failures."""
        engine = RecoveryEngine(**mock_dependencies)

        strategy = engine.select_recovery_strategy(FailureType.TIMEOUT)

        assert strategy == RecoveryStrategy.RETRY

    def test_select_recovery_strategy_network(self, mock_dependencies):
        """Test strategy selection for network failures."""
        engine = RecoveryEngine(**mock_dependencies)

        strategy = engine.select_recovery_strategy(FailureType.NETWORK)

        assert strategy == RecoveryStrategy.EVENT_REPLAY

    def test_select_recovery_strategy_syntax(self, mock_dependencies):
        """Test strategy selection for syntax failures."""
        engine = RecoveryEngine(**mock_dependencies)

        strategy = engine.select_recovery_strategy(FailureType.SYNTAX)

        assert strategy == RecoveryStrategy.HITL

    def test_select_recovery_strategy_runtime(self, mock_dependencies):
        """Test strategy selection for runtime failures."""
        engine = RecoveryEngine(**mock_dependencies)

        strategy = engine.select_recovery_strategy(FailureType.RUNTIME)

        assert strategy == RecoveryStrategy.SNAPSHOT_RESTORE

    def test_select_recovery_strategy_unknown(self, mock_dependencies):
        """Test strategy selection for unknown failures."""
        engine = RecoveryEngine(**mock_dependencies)

        strategy = engine.select_recovery_strategy(FailureType.UNKNOWN)

        assert strategy == RecoveryStrategy.ESCALATE

    @pytest.mark.asyncio
    async def test_execute_recovery_with_none_context(self, mock_dependencies):
        """Test that execute_recovery raises error for None context."""
        engine = RecoveryEngine(**mock_dependencies)

        with pytest.raises(ValueError, match="Recovery context is required"):
            await engine.execute_recovery(None)

    @pytest.mark.asyncio
    async def test_execute_retry_strategy(self, mock_dependencies):
        """Test RETRY recovery strategy execution."""
        engine = RecoveryEngine(**mock_dependencies)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.TIMEOUT,
            error_msg="Timeout",
            recovery_strategy=RecoveryStrategy.RETRY,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        mock_dependencies["state_machine"].transition.assert_called()

    @pytest.mark.asyncio
    async def test_execute_recovery_traces_recovery_operation(
        self, mock_dependencies, monkeypatch
    ):
        """Recovery execution should create an observability span."""
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
            "agentManager.recovery.recovery_engine.trace_operation",
            lambda name, **attributes: RecordingSpan(name, **attributes),
        )
        engine = RecoveryEngine(**mock_dependencies)
        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.TIMEOUT,
            error_msg="Timeout",
            recovery_strategy=RecoveryStrategy.RETRY,
        )

        await engine.execute_recovery(ctx)

        assert spans[0].name == "recovery.execute"
        assert spans[0].attributes["task_id"] == "task_1"
        assert spans[0].attributes["workflow_id"] == "workflow_1"

    @pytest.mark.asyncio
    async def test_execute_escalate_strategy_records_audit_event(
        self, mock_dependencies, monkeypatch
    ):
        """Successful escalation should still be audited."""
        recorded = []
        monkeypatch.setattr(
            "agentManager.recovery.recovery_engine.audit_recovery_escalated",
            lambda workflow_id, task_id, reason: recorded.append(
                (workflow_id, task_id, reason)
            ),
        )
        engine = RecoveryEngine(**mock_dependencies)
        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.UNKNOWN,
            error_msg="Unknown failure",
            recovery_strategy=RecoveryStrategy.ESCALATE,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        assert recorded == [("workflow_1", "task_1", "Unknown failure")]

    @pytest.mark.asyncio
    async def test_execute_event_replay_strategy(self, mock_dependencies):
        """Test EVENT_REPLAY recovery strategy execution."""
        engine = RecoveryEngine(**mock_dependencies)

        # Mock event bus to return events
        mock_event = Mock(spec=Event)
        mock_event.event_id = "event_1"
        mock_event.event_type = EventType.TASK_STARTED
        mock_dependencies["event_bus"].get_events = AsyncMock(
            return_value=[mock_event]
        )

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.NETWORK,
            error_msg="Network error",
            event_id="event_1",
            recovery_strategy=RecoveryStrategy.EVENT_REPLAY,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        mock_dependencies["event_bus"].get_events.assert_called()

    @pytest.mark.asyncio
    async def test_execute_snapshot_restore_strategy(self, mock_dependencies):
        """Test SNAPSHOT_RESTORE recovery strategy execution."""
        engine = RecoveryEngine(**mock_dependencies)

        # Mock checkpoint manager to return a checkpoint
        mock_checkpoint = Mock()
        mock_dependencies["checkpoint_manager"].load_checkpoint = AsyncMock(
            return_value=mock_checkpoint
        )

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.RUNTIME,
            error_msg="Runtime error",
            checkpoint_id="cp_1",
            recovery_strategy=RecoveryStrategy.SNAPSHOT_RESTORE,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        mock_dependencies["checkpoint_manager"].load_checkpoint.assert_called()

    @pytest.mark.asyncio
    async def test_execute_hitl_strategy(self, mock_dependencies):
        """Test HITL recovery strategy execution."""
        engine = RecoveryEngine(**mock_dependencies)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.SYNTAX,
            error_msg="Syntax error",
            recovery_strategy=RecoveryStrategy.HITL,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        mock_dependencies["state_machine"].transition.assert_called_with(
            "task_1",
            TaskState.BLOCKED_HITL,
            "Awaiting human intervention for error: Syntax error",
        )

    @pytest.mark.asyncio
    async def test_execute_escalate_strategy(self, mock_dependencies):
        """Test ESCALATE recovery strategy execution."""
        engine = RecoveryEngine(**mock_dependencies)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.UNKNOWN,
            error_msg="Unknown error",
            recovery_strategy=RecoveryStrategy.ESCALATE,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        mock_dependencies["state_machine"].transition.assert_called()

    @pytest.mark.asyncio
    async def test_recovery_history_tracking(self, mock_dependencies):
        """Test that recovery attempts are tracked in history."""
        engine = RecoveryEngine(**mock_dependencies)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.TIMEOUT,
            error_msg="Timeout",
            recovery_strategy=RecoveryStrategy.RETRY,
        )

        await engine.execute_recovery(ctx)

        assert "task_1" in engine.recovery_history
        assert len(engine.recovery_history["task_1"]) > 0
        assert engine.recovery_history["task_1"][0]["failure_type"] == "timeout"

    @pytest.mark.asyncio
    async def test_recovery_event_publication(self, mock_dependencies):
        """Test that recovery events are published."""
        engine = RecoveryEngine(**mock_dependencies)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.TIMEOUT,
            error_msg="Timeout",
            recovery_strategy=RecoveryStrategy.RETRY,
        )

        await engine.execute_recovery(ctx)

        mock_dependencies["event_bus"].publish.assert_called()

    @pytest.mark.asyncio
    async def test_retry_strategy_max_attempts(self, mock_dependencies):
        """Test RETRY strategy respects max retry attempts."""
        engine = RecoveryEngine(**mock_dependencies)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.TIMEOUT,
            error_msg="Timeout",
            retry_count=RecoveryEngine.MAX_RETRY_ATTEMPTS,
            recovery_strategy=RecoveryStrategy.RETRY,
        )

        result = await engine.execute_recovery(ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_event_replay_without_event_id(self, mock_dependencies):
        """Test EVENT_REPLAY strategy fails without event_id."""
        engine = RecoveryEngine(**mock_dependencies)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.NETWORK,
            error_msg="Network error",
            recovery_strategy=RecoveryStrategy.EVENT_REPLAY,
        )

        result = await engine.execute_recovery(ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_snapshot_restore_without_checkpoint(self, mock_dependencies):
        """Test SNAPSHOT_RESTORE strategy fails without checkpoint_id."""
        engine = RecoveryEngine(**mock_dependencies)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.RUNTIME,
            error_msg="Runtime error",
            recovery_strategy=RecoveryStrategy.SNAPSHOT_RESTORE,
        )

        result = await engine.execute_recovery(ctx)

        assert result is False

    @pytest.mark.asyncio
    async def test_retry_strategy_reruns_task_when_available(
        self, mock_dependencies
    ):
        """Test RETRY re-executes task when the task object is available."""
        engine = RecoveryEngine(**mock_dependencies)

        task = Mock()
        task.node_id = "task_1"
        task.metadata = {"workflow_id": "workflow_1"}
        mock_dependencies["task_executor"].get_task = Mock(return_value=task)
        mock_dependencies["task_executor"].run_task = AsyncMock()

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.TIMEOUT,
            error_msg="Timeout",
            recovery_strategy=RecoveryStrategy.RETRY,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        mock_dependencies["task_executor"].run_task.assert_awaited_once_with(
            task
        )
        assert ctx.retry_count == 1

    @pytest.mark.asyncio
    async def test_retry_strategy_marks_retry_ready_without_task(
        self, mock_dependencies
    ):
        """Test RETRY marks retry-ready context when task object is unavailable."""
        engine = RecoveryEngine(**mock_dependencies)

        exec_ctx = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={},
        )
        mock_dependencies["task_executor"].get_execution_context = Mock(
            return_value=exec_ctx
        )
        mock_dependencies["task_executor"].get_task = Mock(return_value=None)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.TIMEOUT,
            error_msg="Timeout",
            recovery_strategy=RecoveryStrategy.RETRY,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        assert exec_ctx.metadata["recovery_retry_ready"] is True
        assert (
            exec_ctx.metadata["recovery_retry_reason"]
            == "Task object unavailable for immediate re-run"
        )

    @pytest.mark.asyncio
    async def test_event_replay_rehydrates_execution_context(
        self, mock_dependencies
    ):
        """Test EVENT_REPLAY applies replayed events into task execution context."""
        engine = RecoveryEngine(**mock_dependencies)

        exec_ctx = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={},
        )
        mock_dependencies["task_executor"].get_execution_context = Mock(
            return_value=exec_ctx
        )
        start_event = Event(
            event_type=EventType.TASK_STARTED,
            workflow_id="workflow_1",
            payload={"task_id": "task_1"},
            event_id="ev-1",
        )
        complete_event = Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="workflow_1",
            payload={"task_id": "task_1", "result": {"ok": True}},
            event_id="ev-2",
        )
        mock_dependencies["event_bus"].get_events = AsyncMock(
            return_value=[start_event, complete_event]
        )

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.NETWORK,
            error_msg="Network error",
            event_id="ev-1",
            recovery_strategy=RecoveryStrategy.EVENT_REPLAY,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        assert exec_ctx.status == ExecutionStatus.COMPLETED
        assert exec_ctx.result == {"ok": True}
        assert exec_ctx.metadata["replayed_event_ids"] == ["ev-1", "ev-2"]
        assert exec_ctx.metadata["last_replayed_event_id"] == "ev-2"

    @pytest.mark.asyncio
    async def test_snapshot_restore_validates_checkpoint_id_when_present(
        self, mock_dependencies
    ):
        """Test SNAPSHOT_RESTORE fails when checkpoint_id does not match."""
        engine = RecoveryEngine(**mock_dependencies)

        checkpoint_ctx = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={"checkpoint_id": "cp_actual"},
        )
        mock_dependencies["checkpoint_manager"].load_checkpoint = AsyncMock(
            return_value=checkpoint_ctx
        )

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.RUNTIME,
            error_msg="Runtime error",
            checkpoint_id="cp_expected",
            recovery_strategy=RecoveryStrategy.SNAPSHOT_RESTORE,
        )

        result = await engine.execute_recovery(ctx)

        assert result is False
        assert "task_1" not in mock_dependencies["task_executor"].execution_contexts

    @pytest.mark.asyncio
    async def test_hitl_stores_manual_intervention_context(
        self, mock_dependencies
    ):
        """Test HITL stores manual intervention details on execution context."""
        engine = RecoveryEngine(**mock_dependencies)

        exec_ctx = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={},
        )
        mock_dependencies["task_executor"].get_execution_context = Mock(
            return_value=exec_ctx
        )

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.SYNTAX,
            error_msg="Syntax error",
            recovery_strategy=RecoveryStrategy.HITL,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        interventions = exec_ctx.metadata["manual_intervention"]
        assert len(interventions) == 1
        assert interventions[0]["strategy"] == RecoveryStrategy.HITL.value
        assert interventions[0]["failure_type"] == FailureType.SYNTAX.value
        assert interventions[0]["error_msg"] == "Syntax error"

    @pytest.mark.asyncio
    async def test_escalate_stores_manual_intervention_context(
        self, mock_dependencies
    ):
        """Test ESCALATE stores manual intervention details on execution context."""
        engine = RecoveryEngine(**mock_dependencies)

        exec_ctx = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={},
        )
        mock_dependencies["task_executor"].get_execution_context = Mock(
            return_value=exec_ctx
        )

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.UNKNOWN,
            error_msg="Unknown error",
            recovery_strategy=RecoveryStrategy.ESCALATE,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        interventions = exec_ctx.metadata["manual_intervention"]
        assert len(interventions) == 1
        assert interventions[0]["strategy"] == RecoveryStrategy.ESCALATE.value
        assert interventions[0]["failure_type"] == FailureType.UNKNOWN.value
        assert interventions[0]["error_msg"] == "Unknown error"

    @pytest.mark.asyncio
    async def test_defect_repair_succeeds_with_injected_pipeline(
        self, mock_dependencies
    ):
        """Test DEFECT_REPAIR succeeds when a configured pipeline repairs code."""
        exec_ctx = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={},
        )
        exec_ctx.mark_failed("ValueError: invalid value")
        task = Mock()
        task.node_id = "task_1"
        task.metadata = {"workflow_id": "workflow_1", "code": "x = int(raw)"}
        pipeline = Mock()
        pipeline.repair = AsyncMock(return_value=(RepairStatus.SUCCESS, "x = 1"))
        pipeline.get_repair_history = Mock(
            return_value=[
                RepairResult(
                    status=RepairStatus.SUCCESS,
                    repaired_code="x = 1",
                    attempts=1,
                )
            ]
        )
        mock_dependencies["task_executor"].get_execution_context = Mock(
            return_value=exec_ctx
        )
        mock_dependencies["task_executor"].get_task = Mock(return_value=task)
        mock_dependencies["state_machine"].get_state = Mock(
            return_value=TaskState.COMPLETED
        )
        engine = RecoveryEngine(
            **mock_dependencies,
            defect_repair_pipeline=pipeline,
        )

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.RUNTIME,
            error_msg="ValueError: invalid value",
            recovery_strategy=RecoveryStrategy.DEFECT_REPAIR,
        )

        result = await engine.execute_recovery(ctx)

        assert result is True
        pipeline.repair.assert_awaited_once()
        assert exec_ctx.status == ExecutionStatus.COMPLETED
        assert exec_ctx.metadata["defect_repair"]["status"] == "success"
        assert exec_ctx.metadata["defect_repair"]["repaired_code_present"] is True

    @pytest.mark.asyncio
    async def test_defect_repair_fails_without_pipeline(self, mock_dependencies):
        """Test DEFECT_REPAIR records unavailable metadata when not configured."""
        exec_ctx = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={},
        )
        mock_dependencies["task_executor"].get_execution_context = Mock(
            return_value=exec_ctx
        )
        mock_dependencies["state_machine"].get_state = Mock(
            return_value=TaskState.FAILED
        )
        engine = RecoveryEngine(**mock_dependencies)

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.RUNTIME,
            error_msg="Runtime error",
            recovery_strategy=RecoveryStrategy.DEFECT_REPAIR,
        )

        result = await engine.execute_recovery(ctx)

        assert result is False
        assert exec_ctx.metadata["defect_repair"]["status"] == "unavailable"
        assert (
            exec_ctx.metadata["defect_repair"]["failure_reason"]
            == "Defect repair pipeline is not configured"
        )

    @pytest.mark.asyncio
    async def test_defect_repair_missing_code_blocks_for_human_review(
        self, mock_dependencies
    ):
        """Test DEFECT_REPAIR skips tasks without repairable code metadata."""
        exec_ctx = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={},
        )
        task = Mock()
        task.node_id = "task_1"
        task.metadata = {"workflow_id": "workflow_1"}
        pipeline = Mock()
        mock_dependencies["task_executor"].get_execution_context = Mock(
            return_value=exec_ctx
        )
        mock_dependencies["task_executor"].get_task = Mock(return_value=task)
        mock_dependencies["state_machine"].get_state = Mock(
            return_value=TaskState.FAILED
        )
        engine = RecoveryEngine(
            **mock_dependencies,
            defect_repair_pipeline=pipeline,
        )

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.RUNTIME,
            error_msg="Runtime error",
            recovery_strategy=RecoveryStrategy.DEFECT_REPAIR,
        )

        result = await engine.execute_recovery(ctx)

        assert result is False
        assert exec_ctx.metadata["defect_repair"]["status"] == "skipped"
        assert "No repairable code" in exec_ctx.metadata["defect_repair"]["failure_reason"]

    @pytest.mark.asyncio
    async def test_defect_repair_escalation_records_manual_intervention(
        self, mock_dependencies
    ):
        """Test escalated defect repair stores manual-intervention metadata."""
        exec_ctx = ExecutionContext(
            task_id="task_1",
            workflow_id="workflow_1",
            metadata={},
        )
        task = Mock()
        task.node_id = "task_1"
        task.metadata = {"workflow_id": "workflow_1", "code": "broken()"}
        pipeline = Mock()
        pipeline.repair = AsyncMock(return_value=(RepairStatus.ESCALATED, None))
        pipeline.get_repair_history = Mock(
            return_value=[
                RepairResult(
                    status=RepairStatus.ESCALATED,
                    error_message="Escalated to human review",
                    attempts=1,
                )
            ]
        )
        mock_dependencies["task_executor"].get_execution_context = Mock(
            return_value=exec_ctx
        )
        mock_dependencies["task_executor"].get_task = Mock(return_value=task)
        mock_dependencies["state_machine"].get_state = Mock(
            return_value=TaskState.BLOCKED_HITL
        )
        engine = RecoveryEngine(
            **mock_dependencies,
            defect_repair_pipeline=pipeline,
        )

        ctx = RecoveryContext(
            task_id="task_1",
            workflow_id="workflow_1",
            failure_type=FailureType.RUNTIME,
            error_msg="Runtime error",
            recovery_strategy=RecoveryStrategy.DEFECT_REPAIR,
        )

        result = await engine.execute_recovery(ctx)

        assert result is False
        assert exec_ctx.metadata["defect_repair"]["status"] == "escalated"
        assert exec_ctx.metadata["manual_intervention"][0]["strategy"] == "defect_repair"
