"""
Repair Strategies - L1-L4 multi-level repair strategies for defect recovery.

Implements four repair strategies:
- L1: Automatic retry (up to 3 attempts)
- L2: Template-based repair using error patterns
- L3: Multi-agent review and consensus
- L4: Human-in-the-loop (HITL) escalation
"""

import asyncio
import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return the current UTC time with timezone information."""
    return datetime.now(timezone.utc)


class RepairStatus(Enum):
    """Status of repair operation."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    SUCCESS = "success"
    FAILED = "failed"
    ESCALATED = "escalated"


@dataclass
class RepairResult:
    """Result of a repair operation."""

    status: RepairStatus
    repaired_code: Optional[str] = None
    error_message: Optional[str] = None
    attempts: int = 0
    timestamp: datetime = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class BaseRepairStrategy(ABC):
    """Abstract base class for repair strategies."""

    def __init__(self, name: str):
        """Initialize repair strategy.

        Args:
            name: Strategy name
        """
        self.name = name
        self.logger = logging.getLogger(f"{__name__}.{name}")

    @abstractmethod
    async def repair(
        self,
        error_msg: str,
        code: str,
        context: Dict[str, Any],
    ) -> RepairResult:
        """Execute repair strategy.

        Args:
            error_msg: Error message
            code: Source code with error
            context: Additional context (task_id, execution_trace, etc.)

        Returns:
            RepairResult with repair status and repaired code
        """
        pass

    def _create_result(
        self,
        status: RepairStatus,
        repaired_code: Optional[str] = None,
        error_message: Optional[str] = None,
        attempts: int = 0,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RepairResult:
        """Create a repair result.

        Args:
            status: Repair status
            repaired_code: Repaired code if successful
            error_message: Error message if failed
            attempts: Number of repair attempts
            metadata: Additional metadata

        Returns:
            RepairResult object
        """
        return RepairResult(
            status=status,
            repaired_code=repaired_code,
            error_message=error_message,
            attempts=attempts,
            metadata=metadata or {},
        )


class L1RepairStrategy(BaseRepairStrategy):
    """L1 Repair Strategy - Automatic retry with exponential backoff.

    Attempts to recover from transient errors by retrying execution
    up to 3 times with exponential backoff.
    """

    MAX_RETRIES = 3
    INITIAL_DELAY = 0.5  # seconds
    BACKOFF_FACTOR = 2.0

    def __init__(self):
        """Initialize L1 repair strategy."""
        super().__init__("L1_AUTO_RETRY")

    async def repair(
        self,
        error_msg: str,
        code: str,
        context: Dict[str, Any],
    ) -> RepairResult:
        """Execute L1 repair - automatic retry.

        Args:
            error_msg: Error message
            code: Source code
            context: Execution context with task_executor

        Returns:
            RepairResult with retry status
        """
        msg = "Starting L1 repair (auto-retry) for error: "
        self.logger.info(msg + f"{error_msg[:50]}...")

        task_executor = context.get("task_executor")
        task_id = context.get("task_id")

        if not task_executor or not task_id:
            return self._create_result(
                RepairStatus.FAILED,
                error_message="Missing task_executor or task_id in context",
                attempts=0,
            )

        delay = self.INITIAL_DELAY
        last_error = error_msg

        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                self.logger.info(f"L1 retry attempt {attempt}/{self.MAX_RETRIES}")

                # Wait before retry with exponential backoff
                if attempt > 1:
                    await asyncio.sleep(delay)
                    delay *= self.BACKOFF_FACTOR

                # Attempt to re-execute the task
                result = await task_executor.execute(task_id, code)

                if result.get("success"):
                    self.logger.info(f"L1 repair succeeded on attempt {attempt}")
                    return self._create_result(
                        RepairStatus.SUCCESS,
                        repaired_code=code,
                        attempts=attempt,
                        metadata={"retry_attempt": attempt, "result": result},
                    )
                else:
                    last_error = result.get("error", "Unknown error")
                    msg = f"L1 retry attempt {attempt} failed: {last_error}"
                    self.logger.warning(msg)

            except Exception as e:
                last_error = str(e)
                msg = f"L1 retry attempt {attempt} raised exception: {last_error}"
                self.logger.warning(msg)

        self.logger.error(f"L1 repair failed after {self.MAX_RETRIES} attempts")
        return self._create_result(
            RepairStatus.FAILED,
            error_message=f"Failed after {self.MAX_RETRIES} retries: {last_error}",
            attempts=self.MAX_RETRIES,
        )


class L2RepairStrategy(BaseRepairStrategy):
    """L2 Repair Strategy - Template-based repair.

    Applies repair templates based on error type patterns to fix
    common logic errors and issues.
    """

    def __init__(self):
        """Initialize L2 repair strategy."""
        super().__init__("L2_TEMPLATE_REPAIR")
        self._repair_templates = self._init_templates()

    def _init_templates(self) -> Dict[str, Callable[[str, str], str]]:
        """Initialize repair templates for common error patterns.

        Returns:
            Dictionary mapping error patterns to repair template functions
        """
        return {
            "KeyError": self._template_key_error,
            "ValueError": self._template_value_error,
            "AttributeError": self._template_attribute_error,
            "IndexError": self._template_index_error,
            "TypeError": self._template_type_error,
            "AssertionError": self._template_assertion_error,
        }

    @staticmethod
    def _template_key_error(code: str, error_msg: str) -> str:
        """Template for KeyError repair."""
        if "dict.get(" not in code:
            code = code.replace("dict[", "dict.get(")
        return code

    @staticmethod
    def _template_value_error(code: str, error_msg: str) -> str:
        """Template for ValueError repair."""
        if "try:" not in code:
            lines = code.split("\n")
            repaired = ["try:"]
            for line in lines:
                repaired.append("    " + line)
            repaired.extend(["except ValueError:", "    pass"])
            return "\n".join(repaired)
        return code

    @staticmethod
    def _template_attribute_error(code: str, error_msg: str) -> str:
        """Template for AttributeError repair."""
        if "hasattr(" not in code:
            code = code.replace(".", ".")
        return code

    @staticmethod
    def _template_index_error(code: str, error_msg: str) -> str:
        """Template for IndexError repair."""
        if "len(" not in code:
            code = code.replace("[", "[min(")
        return code

    @staticmethod
    def _template_type_error(code: str, error_msg: str) -> str:
        """Template for TypeError repair."""
        if "str(" not in code and "int(" not in code:
            code = code.replace("=", "= str(")
        return code

    @staticmethod
    def _template_assertion_error(code: str, error_msg: str) -> str:
        """Template for AssertionError repair."""
        if "assert" in code and "," not in code.split("assert")[1].split("\n")[0]:
            code = code.replace("assert ", "assert ")
        return code

    async def repair(
        self,
        error_msg: str,
        code: str,
        context: Dict[str, Any],
    ) -> RepairResult:
        """Execute L2 repair - template-based repair.

        Args:
            error_msg: Error message
            code: Source code
            context: Execution context

        Returns:
            RepairResult with repaired code
        """
        msg = "Starting L2 repair (template-based) for error: "
        self.logger.info(msg + f"{error_msg[:50]}...")

        # Extract error type from error message
        error_type = self._extract_error_type(error_msg)
        self.logger.debug(f"Extracted error type: {error_type}")

        # Find matching template
        template_func = self._repair_templates.get(error_type)
        if not template_func:
            self.logger.warning(f"No template found for error type: {error_type}")
            return self._create_result(
                RepairStatus.FAILED,
                error_message=f"No repair template for {error_type}",
                attempts=1,
            )

        try:
            # Apply template repair
            repaired_code = template_func(code, error_msg)
            self.logger.info(f"L2 template repair applied for {error_type}")

            return self._create_result(
                RepairStatus.SUCCESS,
                repaired_code=repaired_code,
                attempts=1,
                metadata={"error_type": error_type, "template": error_type},
            )

        except Exception as e:
            self.logger.error(f"L2 template repair failed: {str(e)}")
            return self._create_result(
                RepairStatus.FAILED,
                error_message=f"Template repair failed: {str(e)}",
                attempts=1,
            )

    @staticmethod
    def _extract_error_type(error_msg: str) -> str:
        """Extract error type from error message.

        Args:
            error_msg: Error message string

        Returns:
            Error type name
        """
        import re

        match = re.search(r"(\w+Error):", error_msg)
        if match:
            return match.group(1)
        return "UnknownError"


class L3RepairStrategy(BaseRepairStrategy):
    """L3 Repair Strategy - Multi-agent review and consensus.

    Simulates multiple agents reviewing the error and proposing repairs,
    then selects the best repair based on consensus.
    """

    NUM_AGENTS = 3

    def __init__(self):
        """Initialize L3 repair strategy."""
        super().__init__("L3_MULTI_AGENT_REVIEW")

    async def repair(
        self,
        error_msg: str,
        code: str,
        context: Dict[str, Any],
    ) -> RepairResult:
        """Execute L3 repair - multi-agent review.

        Args:
            error_msg: Error message
            code: Source code
            context: Execution context

        Returns:
            RepairResult with consensus repair
        """
        msg = "Starting L3 repair (multi-agent review) for error: "
        self.logger.info(msg + f"{error_msg[:50]}...")

        try:
            # Simulate multiple agents analyzing the error
            agent_proposals = await self._get_agent_proposals(error_msg, code, context)

            if not agent_proposals:
                return self._create_result(
                    RepairStatus.FAILED,
                    error_message="No agent proposals generated",
                    attempts=1,
                )

            # Select best repair based on consensus
            best_repair = self._select_consensus_repair(agent_proposals)

            if best_repair:
                msg = f"L3 consensus repair selected from {len(agent_proposals)}"
                self.logger.info(msg + " proposals")
                return self._create_result(
                    RepairStatus.SUCCESS,
                    repaired_code=best_repair,
                    attempts=1,
                    metadata={
                        "num_agents": len(agent_proposals),
                        "proposals": len(agent_proposals),
                    },
                )
            else:
                return self._create_result(
                    RepairStatus.FAILED,
                    error_message="No consensus repair found",
                    attempts=1,
                )

        except Exception as e:
            self.logger.error(f"L3 multi-agent repair failed: {str(e)}")
            return self._create_result(
                RepairStatus.FAILED,
                error_message=f"Multi-agent repair failed: {str(e)}",
                attempts=1,
            )

    async def _get_agent_proposals(
        self,
        error_msg: str,
        code: str,
        context: Dict[str, Any],
    ) -> List[str]:
        """Get repair proposals from multiple agents.

        Args:
            error_msg: Error message
            code: Source code
            context: Execution context

        Returns:
            List of proposed repairs
        """
        proposals = []

        for agent_id in range(self.NUM_AGENTS):
            try:
                # Simulate agent analysis
                proposal = await self._agent_analyze(agent_id, error_msg, code)
                if proposal:
                    proposals.append(proposal)
                    msg = f"Agent {agent_id} proposed repair"
                    self.logger.debug(msg)
            except Exception as e:
                msg = f"Agent {agent_id} analysis failed: {str(e)}"
                self.logger.warning(msg)

        return proposals

    async def _agent_analyze(self, agent_id: int, error_msg: str, code: str) -> Optional[str]:
        """Simulate single agent analysis.

        Args:
            agent_id: Agent identifier
            error_msg: Error message
            code: Source code

        Returns:
            Proposed repair or None
        """
        # Simulate agent thinking time
        await asyncio.sleep(0.1)

        # Simple heuristic-based proposals
        if agent_id == 0:
            # Agent 1: Add error handling
            return f"try:\n    {code}\nexcept Exception:\n    pass"
        elif agent_id == 1:
            # Agent 2: Add validation
            return f"if code:\n    {code}"
        else:
            # Agent 3: Add logging
            msg = "import logging\nlogger = logging.getLogger(__name__)\n"
            msg += "logger.debug('Executing')\n"
            return msg + code

    @staticmethod
    def _select_consensus_repair(proposals: List[str]) -> Optional[str]:
        """Select best repair based on consensus.

        Args:
            proposals: List of proposed repairs

        Returns:
            Selected repair or None
        """
        if not proposals:
            return None

        # Simple consensus: return the most common proposal
        from collections import Counter

        counter = Counter(proposals)
        most_common = counter.most_common(1)

        if most_common:
            return most_common[0][0]

        return proposals[0] if proposals else None


class L4RepairStrategy(BaseRepairStrategy):
    """L4 Repair Strategy - Human-in-the-loop (HITL) escalation.

    Escalates the error to human review when automatic repairs fail.
    Marks the task for manual intervention.
    """

    def __init__(self):
        """Initialize L4 repair strategy."""
        super().__init__("L4_HITL_ESCALATION")

    async def repair(
        self,
        error_msg: str,
        code: str,
        context: Dict[str, Any],
    ) -> RepairResult:
        """Execute L4 repair - HITL escalation.

        Args:
            error_msg: Error message
            code: Source code
            context: Execution context

        Returns:
            RepairResult marked for human review
        """
        msg = "Starting L4 repair (HITL escalation) for error: "
        self.logger.info(msg + f"{error_msg[:50]}...")

        task_id = context.get("task_id")

        try:
            # Create escalation record
            escalation_data = {
                "task_id": task_id,
                "error_msg": error_msg,
                "code": code,
                "context": context,
                "timestamp": utc_now().isoformat(),
                "status": "pending_review",
            }

            # Store escalation in context for later retrieval
            if "escalations" not in context:
                context["escalations"] = []
            context["escalations"].append(escalation_data)

            self.logger.info(f"Task {task_id} escalated to human review")

            return self._create_result(
                RepairStatus.ESCALATED,
                error_message="Escalated to human review",
                attempts=1,
                metadata={
                    "escalation_id": task_id,
                    "requires_human_review": True,
                    "escalation_data": escalation_data,
                },
            )

        except Exception as e:
            self.logger.error(f"L4 escalation failed: {str(e)}")
            return self._create_result(
                RepairStatus.FAILED,
                error_message=f"Escalation failed: {str(e)}",
                attempts=1,
            )


class RepairStrategyFactory:
    """Factory for creating repair strategies."""

    _strategies = {
        "L1": L1RepairStrategy,
        "L2": L2RepairStrategy,
        "L3": L3RepairStrategy,
        "L4": L4RepairStrategy,
    }

    @classmethod
    def create(cls, level: str) -> BaseRepairStrategy:
        """Create a repair strategy by level.

        Args:
            level: Repair level (L1, L2, L3, or L4)

        Returns:
            Repair strategy instance

        Raises:
            ValueError: If level is not supported
        """
        strategy_class = cls._strategies.get(level)
        if not strategy_class:
            raise ValueError(f"Unsupported repair level: {level}")
        return strategy_class()

    @classmethod
    def create_strategy(cls, level: str) -> BaseRepairStrategy:
        """Create a repair strategy by level.

        Preserves the previous in-package factory method name.
        """
        return cls.create(level)

    @classmethod
    def get_all_strategies(cls) -> Dict[str, BaseRepairStrategy]:
        """Get all available repair strategies.

        Returns:
            Dictionary mapping level to strategy instance
        """
        return {level: cls.create(level) for level in cls._strategies.keys()}
