"""Error classifier for categorizing task failures.

This module provides the ErrorClassifier class that analyzes exceptions
and classifies them into failure types, recommending appropriate recovery strategies.
"""

import logging
from typing import Tuple
from agentManager.recovery.recovery_context import FailureType, RecoveryStrategy

logger = logging.getLogger(__name__)


class ErrorClassifier:
    """Classifies errors and recommends recovery strategies.

    Analyzes exception types and messages to determine the failure type
    and recommend the most appropriate recovery strategy.
    """

    # Error patterns for classification
    TIMEOUT_PATTERNS = [
        "timeout",
        "timed out",
        "deadline exceeded",
        "time limit",
    ]

    NETWORK_PATTERNS = [
        "connection",
        "network",
        "socket",
        "refused",
        "unreachable",
        "dns",
        "http error",
        "request failed",
    ]

    SYNTAX_PATTERNS = [
        "syntax error",
        "invalid syntax",
        "parse error",
        "unexpected token",
        "indentation error",
    ]

    RUNTIME_PATTERNS = [
        "runtime error",
        "attribute error",
        "type error",
        "value error",
        "key error",
        "index error",
        "zero division",
        "failed",
    ]

    # Strategy recommendations per failure type
    STRATEGY_RECOMMENDATIONS = {
        FailureType.TIMEOUT: RecoveryStrategy.RETRY,
        FailureType.NETWORK: RecoveryStrategy.EVENT_REPLAY,
        FailureType.SYNTAX: RecoveryStrategy.HITL,
        FailureType.RUNTIME: RecoveryStrategy.SNAPSHOT_RESTORE,
        FailureType.UNKNOWN: RecoveryStrategy.ESCALATE,
    }

    def classify(self, error: Exception) -> Tuple[FailureType, RecoveryStrategy]:
        """Classify an error and recommend recovery strategy.

        Args:
            error: Exception to classify

        Returns:
            Tuple of (FailureType, RecommendedRecoveryStrategy)
        """
        error_str = str(error).lower()
        error_type_name = type(error).__name__.lower()

        # Check timeout errors
        if self._matches_patterns(error_str, self.TIMEOUT_PATTERNS):
            logger.info(f"Classified error as TIMEOUT: {error}")
            return (
                FailureType.TIMEOUT,
                self.STRATEGY_RECOMMENDATIONS[FailureType.TIMEOUT],
            )

        # Check network errors
        if self._matches_patterns(error_str, self.NETWORK_PATTERNS):
            logger.info(f"Classified error as NETWORK: {error}")
            return (
                FailureType.NETWORK,
                self.STRATEGY_RECOMMENDATIONS[FailureType.NETWORK],
            )

        # Check syntax errors
        if (
            self._matches_patterns(error_str, self.SYNTAX_PATTERNS)
            or "syntaxerror" in error_type_name
        ):
            logger.info(f"Classified error as SYNTAX: {error}")
            return (
                FailureType.SYNTAX,
                self.STRATEGY_RECOMMENDATIONS[FailureType.SYNTAX],
            )

        # Check runtime errors
        if self._matches_patterns(error_str, self.RUNTIME_PATTERNS) or "error" in error_type_name:
            logger.info(f"Classified error as RUNTIME: {error}")
            return (
                FailureType.RUNTIME,
                self.STRATEGY_RECOMMENDATIONS[FailureType.RUNTIME],
            )

        # Default to unknown
        logger.warning(f"Classified error as UNKNOWN: {error}")
        return (
            FailureType.UNKNOWN,
            self.STRATEGY_RECOMMENDATIONS[FailureType.UNKNOWN],
        )

    @staticmethod
    def _matches_patterns(text: str, patterns: list) -> bool:
        """Check if text matches any of the given patterns.

        Args:
            text: Text to check
            patterns: List of patterns to match

        Returns:
            True if any pattern matches
        """
        return any(pattern in text for pattern in patterns)
