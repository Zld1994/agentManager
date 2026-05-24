"""
DefectClassifier - Error classification and severity assessment for defect repair.

Classifies errors into repair levels and severity categories using pattern matching
and contextual analysis.
"""

import logging
import re
from enum import Enum
from dataclasses import dataclass, field
from typing import List, Tuple, Dict, Optional

from .repair_engine import RepairLevel

logger = logging.getLogger(__name__)


class SeverityLevel(Enum):
    """Severity levels for defects (1-5 scale)."""
    TRIVIAL = (1, "代码风格")  # Code style issues
    LOW = (2, "性能下降")  # Performance degradation
    MEDIUM = (3, "部分功能异常")  # Partial functionality issues
    HIGH = (4, "功能失效")  # Function failure
    CRITICAL = (5, "系统崩溃")  # System crash

    @property
    def level(self) -> int:
        """Get numeric severity level (1-5)."""
        return self.value[0]

    @property
    def description(self) -> str:
        """Get severity description."""
        return self.value[1]


@dataclass
class DefectPattern:
    """Pattern definition for error classification."""
    pattern_name: str
    regex_pattern: str
    repair_level: RepairLevel
    severity: SeverityLevel
    description: str

    def matches(self, text: str) -> bool:
        """Check if pattern matches the given text."""
        try:
            return bool(re.search(self.regex_pattern, text, re.IGNORECASE))
        except re.error as e:
            logger.warning(f"Invalid regex pattern '{self.regex_pattern}': {e}")
            return False


class DefectClassifier:
    """
    Classifies code defects into repair levels and severity categories.
    
    Uses pattern matching and contextual analysis to determine appropriate
    repair strategies and priority levels.
    """

    def __init__(self) -> None:
        """Initialize DefectClassifier with built-in patterns."""
        self._patterns: List[DefectPattern] = []
        self._pattern_map: Dict[str, DefectPattern] = {}
        self._init_builtin_patterns()
        logger.info("DefectClassifier initialized with built-in patterns")

    def _init_builtin_patterns(self) -> None:
        """Initialize built-in error patterns."""
        builtin_patterns = [
            # L1: Syntax and Type Errors
            DefectPattern(
                pattern_name="SyntaxError",
                regex_pattern=r"SyntaxError|syntax error|invalid syntax",
                repair_level=RepairLevel.L1_SYNTAX,
                severity=SeverityLevel.HIGH,
                description="Python syntax error - invalid code structure"
            ),
            DefectPattern(
                pattern_name="TypeError",
                regex_pattern=r"TypeError|type error|unsupported operand",
                repair_level=RepairLevel.L1_SYNTAX,
                severity=SeverityLevel.HIGH,
                description="Type mismatch or invalid type operation"
            ),
            DefectPattern(
                pattern_name="AttributeError",
                regex_pattern=r"AttributeError|has no attribute|attribute error",
                repair_level=RepairLevel.L1_SYNTAX,
                severity=SeverityLevel.HIGH,
                description="Missing or invalid attribute access"
            ),
            # L2: Logic Errors
            DefectPattern(
                pattern_name="AssertionError",
                regex_pattern=r"AssertionError|assertion failed",
                repair_level=RepairLevel.L2_LOGIC,
                severity=SeverityLevel.MEDIUM,
                description="Assertion condition failed - logic error"
            ),
            DefectPattern(
                pattern_name="ValueError",
                regex_pattern=r"ValueError|invalid value|value error",
                repair_level=RepairLevel.L2_LOGIC,
                severity=SeverityLevel.MEDIUM,
                description="Invalid value provided to function"
            ),
            DefectPattern(
                pattern_name="KeyError",
                regex_pattern=r"KeyError|key error|key not found",
                repair_level=RepairLevel.L2_LOGIC,
                severity=SeverityLevel.MEDIUM,
                description="Dictionary key not found"
            ),
            # L3: Performance Issues
            DefectPattern(
                pattern_name="MemoryError",
                regex_pattern=r"MemoryError|out of memory|memory exhausted",
                repair_level=RepairLevel.L3_PERFORMANCE,
                severity=SeverityLevel.CRITICAL,
                description="Memory allocation failure"
            ),
            DefectPattern(
                pattern_name="TimeoutError",
                regex_pattern=r"TimeoutError|timeout|timed out|execution timeout",
                repair_level=RepairLevel.L3_PERFORMANCE,
                severity=SeverityLevel.HIGH,
                description="Operation exceeded time limit"
            ),
            # L4: Architecture Problems
            DefectPattern(
                pattern_name="ImportError",
                regex_pattern=r"ImportError|ModuleNotFoundError|cannot import",
                repair_level=RepairLevel.L4_ARCHITECTURE,
                severity=SeverityLevel.HIGH,
                description="Module or dependency import failure"
            ),
            DefectPattern(
                pattern_name="CircularDependency",
                regex_pattern=r"circular import|circular dependency|import cycle",
                repair_level=RepairLevel.L4_ARCHITECTURE,
                severity=SeverityLevel.CRITICAL,
                description="Circular dependency detected in imports"
            ),
        ]

        for pattern in builtin_patterns:
            self.register_pattern(pattern)

    def register_pattern(self, pattern: DefectPattern) -> None:
        """
        Register a custom defect pattern.
        
        Args:
            pattern: DefectPattern to register
        """
        self._patterns.append(pattern)
        self._pattern_map[pattern.pattern_name] = pattern
        logger.debug(f"Registered pattern: {pattern.pattern_name}")

    def get_all_patterns(self) -> List[DefectPattern]:
        """
        Get all registered patterns.
        
        Returns:
            List of all DefectPattern objects
        """
        return self._patterns.copy()

    def extract_error_type(self, error_msg: str) -> str:
        """
        Extract error type from error message.
        
        Args:
            error_msg: Error message string
            
        Returns:
            Extracted error type name
        """
        # Try to match against registered patterns
        for pattern in self._patterns:
            if pattern.matches(error_msg):
                return pattern.pattern_name

        # Fallback: extract from common error format
        match = re.search(r"(\w+Error):", error_msg)
        if match:
            return match.group(1)

        return "UnknownError"

    def calculate_severity(self, error_type: str, impact_scope: str) -> SeverityLevel:
        """
        Calculate severity level based on error type and impact scope.
        
        Args:
            error_type: Type of error detected
            impact_scope: Scope of impact (e.g., "local", "module", "system")
            
        Returns:
            SeverityLevel indicating severity
        """
        # Find pattern for error type
        pattern = self._pattern_map.get(error_type)
        if pattern:
            base_severity = pattern.severity
        else:
            base_severity = SeverityLevel.MEDIUM

        # Adjust severity based on impact scope
        if impact_scope.lower() == "system":
            # Escalate to at least HIGH for system-wide impact
            if base_severity.level < SeverityLevel.HIGH.level:
                return SeverityLevel.HIGH
            return base_severity
        elif impact_scope.lower() == "module":
            # Keep as-is for module-level impact
            return base_severity
        elif impact_scope.lower() == "local":
            # For local impact, only downgrade TRIVIAL/LOW, keep others as-is
            if base_severity.level <= SeverityLevel.LOW.level:
                return base_severity
            return base_severity

        return base_severity

    def classify_error(
        self, error_msg: str, code_context: str
    ) -> Tuple[RepairLevel, SeverityLevel]:
        """
        Classify error and determine repair level and severity.
        
        Args:
            error_msg: Error message from execution
            code_context: Relevant code snippet
            
        Returns:
            Tuple of (RepairLevel, SeverityLevel)
        """
        logger.debug(f"Classifying error: {error_msg[:50]}...")

        # Extract error type
        error_type = self.extract_error_type(error_msg)

        # Find matching pattern
        for pattern in self._patterns:
            if pattern.matches(error_msg):
                # Determine impact scope from code context
                impact_scope = self._determine_impact_scope(code_context)
                severity = self.calculate_severity(error_type, impact_scope)
                logger.debug(
                    f"Classified as {pattern.repair_level.value} / {severity.name}"
                )
                return (pattern.repair_level, severity)

        # Default classification
        logger.warning(f"No pattern matched for error type: {error_type}")
        return (RepairLevel.L2_LOGIC, SeverityLevel.MEDIUM)

    def _determine_impact_scope(self, code_context: str) -> str:
        """
        Determine impact scope from code context.
        
        Args:
            code_context: Code snippet to analyze
            
        Returns:
            Impact scope: "local", "module", or "system"
        """
        # Check for system-level indicators
        if re.search(r"(import|from|__init__|setup|config)", code_context):
            return "system"

        # Check for module-level indicators
        if re.search(r"(class|def)\s+\w+", code_context):
            return "module"

        # Default to local
        return "local"

    def get_repair_priority(
        self, repair_level: RepairLevel, severity: SeverityLevel
    ) -> int:
        """
        Calculate repair priority based on repair level and severity.
        
        Priority scale: 1-100 (higher = more urgent)
        
        Args:
            repair_level: Repair level classification
            severity: Severity level classification
            
        Returns:
            Priority score (1-100)
        """
        # Base priority from repair level
        level_priority = {
            RepairLevel.L1_SYNTAX: 80,
            RepairLevel.L2_LOGIC: 60,
            RepairLevel.L3_PERFORMANCE: 40,
            RepairLevel.L4_ARCHITECTURE: 50,
        }

        base_priority = level_priority.get(repair_level, 50)

        # Adjust by severity
        severity_multiplier = {
            SeverityLevel.TRIVIAL: 0.5,
            SeverityLevel.LOW: 0.7,
            SeverityLevel.MEDIUM: 1.0,
            SeverityLevel.HIGH: 1.3,
            SeverityLevel.CRITICAL: 1.5,
        }

        multiplier = severity_multiplier.get(severity, 1.0)
        priority = int(base_priority * multiplier)

        # Clamp to 1-100 range
        return max(1, min(100, priority))
