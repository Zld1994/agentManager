"""Defect classifier for error classification and repair level selection."""

import logging
import re
from enum import Enum

logger = logging.getLogger(__name__)


class ErrorType(str, Enum):
    """Error types for classification."""

    TIMEOUT = "timeout"
    NETWORK = "network"
    SYNTAX = "syntax"
    RUNTIME = "runtime"
    RESOURCE = "resource"
    UNKNOWN = "unknown"


class RepairLevel(str, Enum):
    """Repair levels for defect repair."""

    L1 = "l1"
    L2 = "l2"
    L3 = "l3"
    L4 = "l4"


class DefectClassifier:
    """Classifies errors and recommends repair levels."""

    # Error patterns for classification
    TIMEOUT_PATTERNS = [
        r"timeout",
        r"timed out",
        r"deadline exceeded",
        r"time limit",
    ]

    NETWORK_PATTERNS = [
        r"connection refused",
        r"connection reset",
        r"network unreachable",
        r"dns resolution",
        r"socket error",
    ]

    SYNTAX_PATTERNS = [
        r"syntax error",
        r"invalid syntax",
        r"parse error",
        r"unexpected token",
    ]

    RUNTIME_PATTERNS = [
        r"runtime error",
        r"exception",
        r"traceback",
        r"error:",
    ]

    RESOURCE_PATTERNS = [
        r"out of memory",
        r"memory error",
        r"disk full",
        r"resource exhausted",
    ]

    def __init__(self):
        """Initialize classifier."""
        self.error_history = {}

    def classify(self, error: Exception) -> str:
        """Classify error type.

        Args:
            error: Exception to classify

        Returns:
            Error type classification as string
        """
        error_str = str(error).lower()
        error_type = error.__class__.__name__

        # Check timeout patterns
        for pattern in self.TIMEOUT_PATTERNS:
            if re.search(pattern, error_str):
                logger.info(f"Classified as TIMEOUT: {error_type}")
                return "timeout"

        # Check network patterns
        for pattern in self.NETWORK_PATTERNS:
            if re.search(pattern, error_str):
                logger.info(f"Classified as NETWORK: {error_type}")
                return "network"

        # Check syntax patterns
        for pattern in self.SYNTAX_PATTERNS:
            if re.search(pattern, error_str):
                logger.info(f"Classified as SYNTAX: {error_type}")
                return "syntax"

        # Check resource patterns
        for pattern in self.RESOURCE_PATTERNS:
            if re.search(pattern, error_str):
                logger.info(f"Classified as RESOURCE: {error_type}")
                return "resource"

        # Check runtime patterns
        for pattern in self.RUNTIME_PATTERNS:
            if re.search(pattern, error_str):
                logger.info(f"Classified as RUNTIME: {error_type}")
                return "runtime"

        # Default to unknown
        logger.info(f"Classified as UNKNOWN: {error_type}")
        return "unknown"

    def recommend_repair_level(self, error_type: str) -> RepairLevel:
        """Recommend repair level based on error type.

        Args:
            error_type: Type of error (string)

        Returns:
            Recommended repair level
        """
        if error_type == "timeout":
            return RepairLevel.L1
        elif error_type == "network":
            return RepairLevel.L1
        elif error_type == "syntax":
            return RepairLevel.L2
        elif error_type == "resource":
            return RepairLevel.L2
        elif error_type == "runtime":
            return RepairLevel.L3
        else:
            return RepairLevel.L4

    def get_repair_level(self, error: Exception) -> RepairLevel:
        """Get repair level for error.

        Args:
            error: Exception to analyze

        Returns:
            Recommended repair level
        """
        error_type = self.classify(error)
        return self.recommend_repair_level(error_type)
