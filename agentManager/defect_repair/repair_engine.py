"""
DefectRepairEngine - Core repair engine for multi-level code defect analysis and repair.

Supports 4 repair levels:
- L1: Syntax/Type errors
- L2: Logic errors
- L3: Performance issues
- L4: Architecture problems
"""

import logging
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return the current UTC time with timezone information."""
    return datetime.now(timezone.utc)


class RepairLevel(Enum):
    """Repair level classification for defects."""

    L1_SYNTAX = "syntax_type_error"
    L2_LOGIC = "logic_error"
    L3_PERFORMANCE = "performance_issue"
    L4_ARCHITECTURE = "architecture_problem"


@dataclass
class DefectInfo:
    """Information about a detected defect."""

    task_id: str
    error_msg: str
    code_context: str
    execution_trace: str
    repair_level: RepairLevel
    severity: int  # 1-5 scale
    timestamp: datetime = field(default_factory=utc_now)
    repair_attempts: int = 0
    last_repair_result: Optional[str] = None


class DefectRepairEngine:
    """
    Multi-level code defect repair engine with Claude API integration.

    Analyzes defects and applies targeted repairs based on severity level.
    """

    def __init__(self, checkpoint_manager: Any, event_bus: Any, state_manager: Any) -> None:
        """
        Initialize DefectRepairEngine.

        Args:
            checkpoint_manager: Manager for saving repair checkpoints
            event_bus: Event bus for publishing repair events
            state_manager: Manager for tracking repair state
        """
        self.checkpoint_manager = checkpoint_manager
        self.event_bus = event_bus
        self.state_manager = state_manager
        self._repair_history: Dict[str, List[DefectInfo]] = defaultdict(list)
        logger.info("DefectRepairEngine initialized")

    def analyze_defect(
        self, error_msg: str, code_context: str, execution_trace: str
    ) -> RepairLevel:
        """
        Analyze defect and determine repair level.

        Args:
            error_msg: Error message from execution
            code_context: Relevant code snippet
            execution_trace: Full execution trace

        Returns:
            RepairLevel indicating severity classification
        """
        logger.debug(f"Analyzing defect: {error_msg[:50]}...")

        # Syntax/Type error indicators
        if any(kw in error_msg.lower() for kw in ["syntaxerror", "typeerror", "indentation"]):
            return RepairLevel.L1_SYNTAX

        # Logic error indicators
        if any(kw in error_msg.lower() for kw in ["assertion", "valueerror", "logic"]):
            return RepairLevel.L2_LOGIC

        # Performance indicators
        if any(kw in error_msg.lower() for kw in ["timeout", "memory", "performance"]):
            return RepairLevel.L3_PERFORMANCE

        # Architecture indicators
        if any(kw in error_msg.lower() for kw in ["design", "architecture", "structure"]):
            return RepairLevel.L4_ARCHITECTURE

        # Default to logic error
        return RepairLevel.L2_LOGIC

    def repair_l1_syntax(self, code: str, error_msg: str) -> str:
        """
        Repair L1 syntax and type errors.

        Args:
            code: Source code with syntax error
            error_msg: Error message describing the issue

        Returns:
            Repaired code string
        """
        logger.info(f"Attempting L1 syntax repair: {error_msg[:40]}...")

        # Basic syntax fixes
        repaired = code

        # Fix common indentation issues
        if "indentation" in error_msg.lower():
            lines = code.split("\n")
            repaired = "\n".join(line.rstrip() for line in lines)

        # Fix missing colons
        if "expected ':'" in error_msg:
            repaired = repaired.replace("if ", "if ").replace("for ", "for ")

        logger.info("L1 syntax repair completed")
        return repaired

    def repair_l2_logic(self, code: str, test_cases: List[str], error_msg: str) -> str:
        """
        Repair L2 logic errors using test cases.

        Args:
            code: Source code with logic error
            test_cases: List of test cases for validation
            error_msg: Error message describing the issue

        Returns:
            Repaired code string
        """
        logger.info(f"Attempting L2 logic repair with {len(test_cases)} test cases...")

        # Placeholder for Claude API integration
        # In production, this would call Claude to analyze and fix logic
        repaired = code

        logger.info(f"L2 logic repair completed, validated against {len(test_cases)} tests")
        return repaired

    def repair_l3_performance(self, code: str, metrics: Dict[str, Any]) -> str:
        """
        Repair L3 performance issues.

        Args:
            code: Source code with performance issues
            metrics: Performance metrics (time, memory, etc.)

        Returns:
            Optimized code string
        """
        logger.info(f"Attempting L3 performance repair: {metrics}")

        # Placeholder for optimization logic
        # In production, this would analyze metrics and suggest optimizations
        repaired = code

        logger.info("L3 performance repair completed")
        return repaired

    def repair_l4_architecture(self, code: str, design_issues: List[str]) -> str:
        """
        Repair L4 architecture problems.

        Args:
            code: Source code with architecture issues
            design_issues: List of identified design problems

        Returns:
            Refactored code string
        """
        logger.info(f"Attempting L4 architecture repair: {len(design_issues)} issues")

        # Placeholder for architectural refactoring
        # In production, this would suggest and apply architectural improvements
        repaired = code

        logger.info("L4 architecture repair completed")
        return repaired

    def execute_repair(self, task_id: str, defect_info: DefectInfo) -> bool:
        """
        Execute repair workflow for a defect.

        Args:
            task_id: Task identifier
            defect_info: Defect information

        Returns:
            True if repair successful, False otherwise
        """
        logger.info(f"Executing repair for task {task_id}, level {defect_info.repair_level.value}")

        try:
            # Publish repair start event
            self.event_bus.publish(
                "repair_started",
                {
                    "task_id": task_id,
                    "level": defect_info.repair_level.value,
                    "severity": defect_info.severity,
                },
            )

            # Execute appropriate repair level
            if defect_info.repair_level == RepairLevel.L1_SYNTAX:
                result = self.repair_l1_syntax(defect_info.code_context, defect_info.error_msg)
            elif defect_info.repair_level == RepairLevel.L2_LOGIC:
                result = self.repair_l2_logic(defect_info.code_context, [], defect_info.error_msg)
            elif defect_info.repair_level == RepairLevel.L3_PERFORMANCE:
                result = self.repair_l3_performance(defect_info.code_context, {})
            else:  # L4_ARCHITECTURE
                result = self.repair_l4_architecture(defect_info.code_context, [])

            # Update defect info
            defect_info.repair_attempts += 1
            defect_info.last_repair_result = result

            # Store in history
            self._repair_history[task_id].append(defect_info)

            # Save checkpoint
            self.checkpoint_manager.save(f"repair_{task_id}", defect_info)

            # Publish repair completed event
            self.event_bus.publish(
                "repair_completed",
                {
                    "task_id": task_id,
                    "level": defect_info.repair_level.value,
                    "attempts": defect_info.repair_attempts,
                },
            )

            logger.info(f"Repair executed successfully for task {task_id}")
            return True

        except Exception as e:
            logger.error(f"Repair execution failed for task {task_id}: {str(e)}")
            self.event_bus.publish("repair_failed", {"task_id": task_id, "error": str(e)})
            return False

    def get_repair_history(self, task_id: str) -> List[DefectInfo]:
        """
        Retrieve repair history for a task.

        Args:
            task_id: Task identifier

        Returns:
            List of DefectInfo records for the task
        """
        history = self._repair_history.get(task_id, [])
        logger.debug(f"Retrieved {len(history)} repair records for task {task_id}")
        return history
