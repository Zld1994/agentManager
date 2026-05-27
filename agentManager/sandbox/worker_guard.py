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


def compute_word_jaccard_similarity(text1: str, text2: str) -> float:
    """
    Compute word-level Jaccard similarity.

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


def compute_text_similarity(text1: str, text2: str) -> float:
    """
    Backward-compatible alias for word-level Jaccard similarity.
    """
    return compute_word_jaccard_similarity(text1, text2)


def _repeat_ratio(items: list) -> float:
    """
    Compute the fraction of the most common value in a window.
    """
    if not items:
        return 0.0

    best_count = 1
    for candidate in items:
        count = sum(1 for item in items if item == candidate)
        if count > best_count:
            best_count = count

    return best_count / len(items)


def is_repeated_action(
    actions: deque,
    window_size: int = 3,
    repeat_threshold: float = 1.0,
) -> bool:
    """
    Check whether the most recent actions repeat within a window.

    Args:
        actions: Deque of action dictionaries
        window_size: Number of recent actions to inspect
        repeat_threshold: Minimum fraction of identical actions required

    Returns:
        True if the configured window contains a repeated action pattern
    """
    if window_size < 2 or len(actions) < window_size:
        return False

    recent_actions = list(actions)[-window_size:]
    return _repeat_ratio(recent_actions) >= repeat_threshold


def is_repeated_error(
    errors: deque,
    window_size: int = 2,
    repeat_threshold: float = 1.0,
) -> bool:
    """
    Check whether the most recent errors repeat within a window.

    Args:
        errors: Deque of error dictionaries
        window_size: Number of recent errors to inspect
        repeat_threshold: Minimum fraction of identical errors required

    Returns:
        True if the configured window contains a repeated error pattern
    """
    if window_size < 2 or len(errors) < window_size:
        return False

    recent_errors = list(errors)[-window_size:]
    return _repeat_ratio(recent_errors) >= repeat_threshold


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

    def __init__(
        self,
        *,
        action_window_size: int = 3,
        action_repeat_threshold: float = 1.0,
        error_window_size: int = 2,
        error_repeat_threshold: float = 1.0,
        output_window_size: int = 50,
        output_similarity_threshold: float = 0.9,
    ):
        """Initialize WorkerGuard with empty tracking structures."""
        self._actions: deque = deque(maxlen=max(100, action_window_size))
        self._outputs: deque = deque(maxlen=max(50, output_window_size))
        self._errors: deque = deque(maxlen=max(50, error_window_size))
        self._total_tokens: int = 0
        self._warned_tokens: bool = False
        self._action_window_size = action_window_size
        self._action_repeat_threshold = action_repeat_threshold
        self._error_window_size = error_window_size
        self._error_repeat_threshold = error_repeat_threshold
        self._output_window_size = output_window_size
        self._output_similarity_threshold = output_similarity_threshold

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
        Check if recent actions repeat enough to indicate a loop.

        Returns:
            True if repeated actions detected, False otherwise
        """
        return is_repeated_action(
            self._actions,
            window_size=self._action_window_size,
            repeat_threshold=self._action_repeat_threshold,
        )

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
        # Check similarity with the configured recent output window.
        recent_window_size = max(1, self._output_window_size)
        recent_outputs = list(self._outputs)[-recent_window_size:]
        for prev_output in recent_outputs:
            similarity = compute_text_similarity(output, prev_output["text"])
            if similarity >= self._output_similarity_threshold:
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

        return not is_repeated_error(
            self._errors,
            window_size=self._error_window_size,
            repeat_threshold=self._error_repeat_threshold,
        )

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
            "repeated_errors": is_repeated_error(
                self._errors,
                window_size=self._error_window_size,
                repeat_threshold=self._error_repeat_threshold,
            ),
            "timestamp": datetime.now().isoformat(),
        }
