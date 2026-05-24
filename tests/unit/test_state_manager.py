"""Unit tests for State Machine."""

import pytest
from agentManager.engine.state_manager import StateMachine, TaskState


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
