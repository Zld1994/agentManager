"""
Unit tests for WorkerGuard - monitoring and safety guard for worker execution

Tests cover:
- Action tracking and repetition detection
- Token usage monitoring with thresholds
- Output hallucination detection via text similarity
- Error tracking and repetition detection
- Comprehensive guard status reporting
"""

import pytest
from datetime import datetime
from collections import deque

from agentManager.sandbox import worker_guard as worker_guard_module
from agentManager.sandbox.worker_guard import (
    WorkerGuard,
    compute_text_similarity,
    is_repeated_action,
    is_repeated_error,
)


@pytest.fixture
def guard():
    """Create a fresh WorkerGuard instance for each test."""
    return WorkerGuard()


class TestRepeatedActionDetection:
    """Test repeated action detection logic."""

    def test_track_action_basic(self, guard):
        """Test basic action tracking."""
        action_type = "code_execution"
        action_params = {"code": "print('hello')"}
        timestamp = datetime.now()

        guard.track_action(action_type, action_params, timestamp)

        assert len(guard._actions) == 1
        assert guard._actions[0]["action_type"] == action_type
        assert guard._actions[0]["action_params"] == action_params

    def test_check_repeated_actions_true(self, guard):
        """Test detection of 3 consecutive identical actions."""
        action_type = "api_call"
        action_params = {"endpoint": "/api/test", "method": "GET"}
        timestamp = datetime.now()

        for _ in range(3):
            guard.track_action(action_type, action_params, timestamp)

        assert guard.check_repeated_actions() is True

    def test_check_repeated_actions_false(self, guard):
        """Test that different actions are not flagged as repeated."""
        timestamp = datetime.now()

        guard.track_action("action_1", {"param": "value1"}, timestamp)
        guard.track_action("action_2", {"param": "value2"}, timestamp)
        guard.track_action("action_3", {"param": "value3"}, timestamp)

        assert guard.check_repeated_actions() is False


class TestTokenTracking:
    """Test token usage tracking and limits."""

    def test_track_token_usage_normal(self, guard):
        """Test normal token usage tracking."""
        result = guard.track_token_usage(1000)

        assert result is True
        assert guard._total_tokens == 1000
        assert guard._warned_tokens is False

    def test_track_token_usage_warning(self, guard):
        """Test token warning threshold at 32k."""
        result = guard.track_token_usage(32000)

        assert result is True
        assert guard._total_tokens == 32000
        assert guard._warned_tokens is True

    def test_track_token_usage_limit(self, guard):
        """Test token limit enforcement at 100k."""
        result = guard.track_token_usage(100000)

        assert result is False
        assert guard._total_tokens == 100000


class TestHallucinationDetection:
    """Test output hallucination detection."""

    def test_track_output_normal(self, guard):
        """Test normal output tracking."""
        output = "This is a normal output"
        result = guard.track_output(output)

        assert result is True
        assert len(guard._outputs) == 1
        assert guard._outputs[0]["text"] == output

    def test_track_output_hallucination(self, guard):
        """Test hallucination detection with >90% similarity."""
        output1 = "The quick brown fox jumps over the lazy dog"
        output2 = "The quick brown fox jumps over the lazy dog"

        guard.track_output(output1)
        result = guard.track_output(output2)

        assert result is False
        assert len(guard._outputs) == 2


class TestErrorTracking:
    """Test error tracking and repetition detection."""

    def test_track_error_single(self, guard):
        """Test tracking a single error."""
        error_type = "RuntimeError"
        error_msg = "Something went wrong"

        result = guard.track_error(error_type, error_msg)

        assert result is True
        assert len(guard._errors) == 1
        assert guard._errors[0]["error_type"] == error_type
        assert guard._errors[0]["error_msg"] == error_msg

    def test_track_error_repeated(self, guard):
        """Test detection of 2 consecutive identical errors."""
        error_type = "TimeoutError"
        error_msg = "Request timed out"

        guard.track_error(error_type, error_msg)
        result = guard.track_error(error_type, error_msg)

        assert result is False
        assert len(guard._errors) == 2


class TestGuardStatus:
    """Test comprehensive guard status reporting."""

    def test_get_guard_status(self, guard):
        """Test guard status with tracked data."""
        timestamp = datetime.now()

        guard.track_action("action", {"param": "value"}, timestamp)
        guard.track_token_usage(50000)
        guard.track_output("Some output")
        guard.track_error("RuntimeError", "Error message")

        status = guard.get_guard_status()

        assert status["total_tokens"] == 50000
        assert status["token_limit"] == 100000
        assert status["token_warning_threshold"] == 32000
        assert status["token_warned"] is True
        assert status["actions_tracked"] == 1
        assert status["outputs_tracked"] == 1
        assert status["errors_tracked"] == 1
        assert status["repeated_actions"] is False
        assert status["repeated_errors"] is False
        assert "timestamp" in status

    def test_get_guard_status_uses_configured_error_detection(self):
        """Test status reports repeated errors using configured thresholds."""
        guard = WorkerGuard(error_window_size=3, error_repeat_threshold=1.0)

        guard.track_error("TimeoutError", "Request timed out")
        guard.track_error("TimeoutError", "Request timed out")

        assert guard.get_guard_status()["repeated_errors"] is False

        guard.track_error("TimeoutError", "Request timed out")

        assert guard.get_guard_status()["repeated_errors"] is True


class TestHelperFunctions:
    """Test helper functions."""

    def test_is_repeated_action_with_deque(self):
        """Test is_repeated_action with deque."""
        actions = deque(maxlen=100)
        action = {"action_type": "test", "action_params": {"key": "value"}}

        actions.append(action)
        actions.append(action)
        actions.append(action)

        assert is_repeated_action(actions) is True

    def test_is_repeated_error_with_deque(self):
        """Test is_repeated_error with deque."""
        errors = deque(maxlen=50)
        error = {"error_type": "RuntimeError", "error_msg": "Test error"}

        errors.append(error)
        errors.append(error)

        assert is_repeated_error(errors) is True

    def test_compute_text_similarity_identical(self):
        """Test text similarity for identical texts."""
        text = "hello world test"
        assert compute_text_similarity(text, text) == 1.0

    def test_compute_text_similarity_empty(self):
        """Test text similarity for empty texts."""
        assert compute_text_similarity("", "") == 0.0

    def test_compute_text_similarity_different(self):
        """Test text similarity for completely different texts."""
        assert compute_text_similarity("hello world", "foo bar baz") == 0.0

    def test_compute_word_jaccard_similarity_alias(self):
        """Test the explicit word-level Jaccard alias."""
        text1 = "hello hello world"
        text2 = "world hello"

        assert worker_guard_module.compute_word_jaccard_similarity(text1, text2) == 1.0
        assert compute_text_similarity(text1, text2) == 1.0

    def test_compute_text_similarity_uses_word_set_overlap(self):
        """Test similarity ignores duplicate words and word order."""
        assert compute_text_similarity("alpha beta beta", "beta alpha") == 1.0


class TestConfigurableLoopDetection:
    """Test configurable loop detection windows and thresholds."""

    def test_is_repeated_action_with_window_threshold(self):
        """Test action repetition detection over a configurable window."""
        actions = deque(maxlen=10)
        repeated_action = {"action_type": "test", "action_params": {"key": "value"}}

        actions.append(repeated_action)
        actions.append({"action_type": "other", "action_params": {"key": "value"}})
        actions.append(repeated_action)
        actions.append(repeated_action)

        assert is_repeated_action(actions, window_size=4, repeat_threshold=0.75) is True

    def test_is_repeated_error_with_window_threshold(self):
        """Test error repetition detection over a configurable window."""
        errors = deque(maxlen=10)
        repeated_error = {"error_type": "RuntimeError", "error_msg": "Test error"}

        errors.append(repeated_error)
        errors.append({"error_type": "ValueError", "error_msg": "Other error"})
        errors.append(repeated_error)

        assert is_repeated_error(errors, window_size=3, repeat_threshold=2 / 3) is True

    def test_track_output_respects_configurable_window(self):
        """Test output loop detection only scans the configured window."""
        guard = WorkerGuard(output_window_size=2, output_similarity_threshold=0.9)

        assert guard.track_output("alpha beta gamma") is True
        assert guard.track_output("delta epsilon zeta") is True
        assert guard.track_output("eta theta iota") is True
        assert guard.track_output("alpha beta gamma") is True
