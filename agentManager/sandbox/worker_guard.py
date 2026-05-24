"""
WorkerGuard - Monitoring and safety guard for worker execution.

Provides:
- Action tracking and repetition detection
- Token usage monitoring with thresholds
- Output hallucination detection via text similarity
- Error tracking and repetition detection
- Comprehensive guard status reporting
"""

from datetime import datetime
from collections import deque
from typing import Any, Dict


def compute_text_similarity(text1: str, text2: str) -> float:
    """
    Compute text similarity using word-based comparison.

    Args:
        text1: First text
        text2: Second text

    Returns:
        Similarity ratio between 0.0 and 1.0
    """
    if not text1 or not text2:
        return 0.0

    words1 = set(text1.split())
    words2 = set(text2.split())

    if not words1 or not words2:
        return 0.0

    common_words = words1 & words2
    total_words = words1 | words2

    return len(common_words) / len(total_words) if total_words else 0.0


def is_repeated_action(actions: deque) -> bool:
    """
    Check if last 3 actions are identical.

    Args:
        actions: Deque of action dictionaries

    Returns:
        True if last 3 actions are identical, False otherwise
    """
    if len(actions) < 3:
        return False

    last_three = list(actions)[-3:]
    return (last_three[0] == last_three[1] == last_three[2])


def is_repeated_error(errors: deque) -> bool:
    """
    Check if last 2 errors are identical.

    Args:
        errors: Deque of error dictionaries

    Returns:
        True if last 2 errors are identical, False otherwise
    """
    if len(errors) < 2:
        return False

    last_two = list(errors)[-2:]
    return (last_two[0] == last_two[1])


class WorkerGuard:
    """
    Safety guard for worker execution.

    Monitors:
    - Repeated actions (infinite loops)
    - Token usage (cost control)
    - Output hallucination (repetitive outputs)
    - Error repetition (stuck states)
    """

    # Constants
    TOKEN_LIMIT = 100000
    TOKEN_WARNING_THRESHOLD = 32000
    HALLUCINATION_THRESHOLD = 0.9

    def __init__(self):
        """Initialize WorkerGuard with empty tracking structures."""
        self._actions: deque = deque(maxlen=100)
        self._outputs: deque = deque(maxlen=50)
        self._errors: deque = deque(maxlen=50)
        self._total_tokens: int = 0
        self._warned_tokens: bool = False

    def track_action(
        self,
        action_type: str,
        action_params: Dict[str, Any],
        timestamp: datetime
    ) -> None:
        """
        Track an action.

        Args:
            action_type: Type of action (e.g., "code_execution")
            action_params: Parameters of the action
            timestamp: When the action occurred
        """
        self._actions.append({
            "action_type": action_type,
            "action_params": action_params,
            "timestamp": timestamp,
        })

    def check_repeated_actions(self) -> bool:
        """
        Check if last 3 actions are identical (infinite loop detection).

        Returns:
            True if repeated actions detected, False otherwise
        """
        return is_repeated_action(self._actions)

    def track_token_usage(self, tokens: int) -> bool:
        """
        Track token usage and enforce limits.

        Args:
            tokens: Number of tokens used

        Returns:
            True if within limit, False if limit exceeded
        """
        self._total_tokens = tokens

        if tokens >= self.TOKEN_WARNING_THRESHOLD:
            self._warned_tokens = True

        if tokens >= self.TOKEN_LIMIT:
            return False

        return True

    def track_output(self, output: str) -> bool:
        """
        Track output and detect hallucination.

        Args:
            output: Output text

        Returns:
            True if output is unique, False if hallucination detected
        """
        # Check similarity with previous outputs
        for prev_output in self._outputs:
            similarity = compute_text_similarity(output, prev_output["text"])
            if similarity > self.HALLUCINATION_THRESHOLD:
                self._outputs.append({"text": output, "timestamp": datetime.now()})
                return False

        self._outputs.append({"text": output, "timestamp": datetime.now()})
        return True

    def track_error(self, error_type: str, error_msg: str) -> bool:
        """
        Track error and detect repetition.

        Args:
            error_type: Type of error
            error_msg: Error message

        Returns:
            True if error is new, False if repeated
        """
        error_dict = {
            "error_type": error_type,
            "error_msg": error_msg,
        }

        self._errors.append(error_dict)

        return not is_repeated_error(self._errors)

    def get_guard_status(self) -> Dict[str, Any]:
        """
        Get comprehensive guard status.

        Returns:
            Dictionary with guard status information
        """
        return {
            "total_tokens": self._total_tokens,
            "token_limit": self.TOKEN_LIMIT,
            "token_warning_threshold": self.TOKEN_WARNING_THRESHOLD,
            "token_warned": self._warned_tokens,
            "actions_tracked": len(self._actions),
            "outputs_tracked": len(self._outputs),
            "errors_tracked": len(self._errors),
            "repeated_actions": self.check_repeated_actions(),
            "repeated_errors": is_repeated_error(self._errors),
            "timestamp": datetime.now().isoformat(),
        }
