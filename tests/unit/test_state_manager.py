"""Unit tests for State Machine."""

import pytest
from agentManager.engine.state_manager import StateMachine, StateTransition, TaskState
from agentManager.storage import AuditRecord, StateRepository


class RecordingStateRepository(StateRepository):
    """Repository fake that records state machine persistence calls."""

    def __init__(self):
        self.states = {}
        self.transitions = []
        self.audit_records = []

    def save_task_state(self, task_id, state):
        self.states[task_id] = state

    def load_task_state(self, task_id):
        return self.states.get(task_id)

    def save_transition(self, transition):
        self.transitions.append(transition)

    def load_transitions(self, task_id):
        return [
            transition
            for transition in self.transitions
            if transition.task_id == task_id
        ]

    def append_audit_record(self, record):
        self.audit_records.append(record)

    def save_workflow(self, workflow):
        raise NotImplementedError

    def load_workflow(self, workflow_id):
        raise NotImplementedError

    def save_task_run(self, task_run):
        raise NotImplementedError

    def load_task_run(self, run_id):
        raise NotImplementedError


class TestStateMachine:
    """Test StateMachine class."""

    def test_initialize_task(self):
        """Test initializing task state."""
        sm = StateMachine()
        sm.initialize("task_1")
        assert sm.get_state("task_1") == TaskState.PENDING

    def test_initialize_with_custom_state(self):
        """Test initializing with custom state."""
        sm = StateMachine()
        sm.initialize("task_1", TaskState.READY)
        assert sm.get_state("task_1") == TaskState.READY

    def test_initialize_duplicate_fails(self):
        """Test that initializing duplicate task fails."""
        sm = StateMachine()
        sm.initialize("task_1")
        with pytest.raises(ValueError, match="already initialized"):
            sm.initialize("task_1")

    def test_valid_transition(self):
        """Test valid state transition."""
        sm = StateMachine()
        sm.initialize("task_1", TaskState.PENDING)
        sm.transition("task_1", TaskState.READY)
        assert sm.get_state("task_1") == TaskState.READY

    def test_invalid_transition_fails(self):
        """Test that invalid transition fails."""
        sm = StateMachine()
        sm.initialize("task_1", TaskState.PENDING)
        # PENDING -> VERIFYING is invalid (not in VALID_TRANSITIONS)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition("task_1", TaskState.VERIFYING)

    def test_emergency_hitl_from_any_state(self):
        """Test emergency HITL transition from any non-terminal state."""
        sm = StateMachine()

        # Test from PENDING
        sm.initialize("task_1", TaskState.PENDING)
        sm.transition("task_1", TaskState.BLOCKED_HITL)
        assert sm.get_state("task_1") == TaskState.BLOCKED_HITL

        # Test from IMPLEMENTING
        sm.initialize("task_2", TaskState.IMPLEMENTING)
        sm.transition("task_2", TaskState.BLOCKED_HITL)
        assert sm.get_state("task_2") == TaskState.BLOCKED_HITL

        # Test from FAILED
        sm.initialize("task_3", TaskState.FAILED)
        sm.transition("task_3", TaskState.BLOCKED_HITL)
        assert sm.get_state("task_3") == TaskState.BLOCKED_HITL

    def test_cannot_transition_from_terminal_state(self):
        """Test that terminal states cannot transition."""
        sm = StateMachine()
        sm.initialize("task_1", TaskState.COMPLETED)
        with pytest.raises(ValueError, match="Invalid transition"):
            sm.transition("task_1", TaskState.READY)

    def test_transition_with_reason(self):
        """Test transition with reason."""
        sm = StateMachine()
        sm.initialize("task_1", TaskState.PENDING)
        sm.transition("task_1", TaskState.READY, reason="dependency met")

        history = sm.get_history("task_1")
        assert len(history) == 1
        assert history[0].reason == "dependency met"

    def test_get_history(self):
        """Test getting transition history."""
        sm = StateMachine()
        sm.initialize("task_1", TaskState.PENDING)
        sm.transition("task_1", TaskState.READY)
        sm.transition("task_1", TaskState.IMPLEMENTING)

        history = sm.get_history("task_1")
        assert len(history) == 2
        assert history[0].from_state == TaskState.PENDING
        assert history[0].to_state == TaskState.READY
        assert history[1].from_state == TaskState.READY
        assert history[1].to_state == TaskState.IMPLEMENTING

    def test_is_terminal(self):
        """Test terminal state detection."""
        sm = StateMachine()
        sm.initialize("task_1", TaskState.PENDING)
        assert not sm.is_terminal("task_1")

        sm.transition("task_1", TaskState.READY)
        sm.transition("task_1", TaskState.IMPLEMENTING)
        sm.transition("task_1", TaskState.VERIFYING)
        sm.transition("task_1", TaskState.COMPLETED)
        assert sm.is_terminal("task_1")

    def test_is_failed(self):
        """Test failed state detection."""
        sm = StateMachine()
        sm.initialize("task_1", TaskState.PENDING)
        assert not sm.is_failed("task_1")

        sm.transition("task_1", TaskState.READY)
        sm.transition("task_1", TaskState.IMPLEMENTING)
        sm.transition("task_1", TaskState.FAILED)
        assert sm.is_failed("task_1")

    def test_transition_uninitialized_task_fails(self):
        """Test that transitioning uninitialized task fails."""
        sm = StateMachine()
        with pytest.raises(ValueError, match="not initialized"):
            sm.transition("task_999", TaskState.READY)

    def test_state_machine_persists_state_and_audit_records(self):
        """StateMachine should persist state changes through optional repository."""
        repository = RecordingStateRepository()
        sm = StateMachine(repository=repository)

        sm.initialize("task_1")
        sm.transition("task_1", TaskState.READY, reason="dependency met")

        assert repository.states["task_1"] == TaskState.READY
        assert len(repository.transitions) == 1
        assert isinstance(repository.transitions[0], StateTransition)
        assert repository.transitions[0].reason == "dependency met"
        assert [record.action for record in repository.audit_records] == [
            "task_state_initialized",
            "task_state_transitioned",
        ]
        assert all(isinstance(record, AuditRecord) for record in repository.audit_records)

    def test_state_machine_hydrates_existing_repository_state(self):
        """StateMachine should read existing repository state before in-memory state."""
        repository = RecordingStateRepository()
        repository.save_task_state("task_1", TaskState.IMPLEMENTING)
        repository.save_transition(
            StateTransition(
                task_id="task_1",
                from_state=TaskState.READY,
                to_state=TaskState.IMPLEMENTING,
                reason="worker claimed",
            )
        )

        sm = StateMachine(repository=repository)

        assert sm.get_state("task_1") == TaskState.IMPLEMENTING
        assert sm.get_history("task_1")[0].reason == "worker claimed"

    def test_state_machine_can_transition_hydrated_repository_state(self):
        """A fresh StateMachine should transition tasks loaded from repository."""
        repository = RecordingStateRepository()
        repository.save_task_state("task_1", TaskState.READY)
        sm = StateMachine(repository=repository)

        sm.transition("task_1", TaskState.IMPLEMENTING, reason="worker claimed")

        assert sm.get_state("task_1") == TaskState.IMPLEMENTING
        assert repository.transitions[0].from_state == TaskState.READY
