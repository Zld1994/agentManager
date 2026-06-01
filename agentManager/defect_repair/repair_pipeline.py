"""
DefectRepairPipeline - Orchestrates L1-L4 multi-level defect repair process.

Manages the complete repair workflow from error classification through
repair execution, verification, and experience storage.
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .classifier import DefectClassifier
from .repair_strategies import (
    BaseRepairStrategy,
    RepairResult,
    RepairStatus,
    RepairStrategyFactory,
)
from agentManager.observability.tracing import create_span

logger = logging.getLogger(__name__)


def utc_now() -> datetime:
    """Return the current UTC time with timezone information."""
    return datetime.now(timezone.utc)


class RepairLevel(Enum):
    """Repair level classification."""

    L1 = "L1"
    L2 = "L2"
    L3 = "L3"
    L4 = "L4"


@dataclass
class TaskRun:
    """Represents a task execution run with error information."""

    task_id: str
    code: str
    error_msg: str
    execution_trace: str
    code_context: str = ""
    timestamp: datetime = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class RepairExperience:
    """Represents a repair experience for learning."""

    task_id: str
    error_type: str
    repair_level: str
    repair_status: RepairStatus
    original_code: str
    repaired_code: Optional[str]
    error_msg: str
    timestamp: datetime = field(default_factory=utc_now)
    metadata: Dict[str, Any] = field(default_factory=dict)


class DefectRepairPipeline:
    """
    Orchestrates the complete L1-L4 defect repair process.

    Manages error classification, repair strategy selection, execution,
    verification, and experience storage.
    """

    def __init__(
        self,
        task_executor: Any,
        recovery_engine: Any,
        memory_system: Any,
    ):
        """Initialize DefectRepairPipeline.

        Args:
            task_executor: Task executor for running tasks
            recovery_engine: Recovery engine for recovery operations
            memory_system: Memory system for storing experiences
        """
        self.task_executor = task_executor
        self.recovery_engine = recovery_engine
        self.memory_system = memory_system

        self.classifier = DefectClassifier()
        self.strategies = RepairStrategyFactory.get_all_strategies()

        self._repair_history: Dict[str, List[RepairResult]] = {}
        self._experiences: List[RepairExperience] = []

        logger.info("DefectRepairPipeline initialized")

    async def repair(self, task_run: TaskRun) -> Tuple[RepairStatus, Optional[str]]:
        task_id = task_run.task_id
        with create_span("defect_repair.pipeline", {"task.id": task_id}):
            return await self._repair_impl(task_run)

    async def _repair_impl(self, task_run: TaskRun) -> Tuple[RepairStatus, Optional[str]]:
        """Execute the complete repair pipeline.

        Args:
            task_run: Task run with error information

        Returns:
            Tuple of (repair_status, repaired_code)
        """
        task_id = task_run.task_id
        logger.info(f"Starting repair pipeline for task {task_id}")

        try:
            # Step 1: Classify error
            with create_span("defect_repair.classify", {"task.id": task_id}):
                repair_level, severity = self.classifier.classify_error(
                    task_run.error_msg,
                    task_run.code_context or task_run.code,
                )
            logger.info(f"Error classified as {repair_level.value} / {severity.name}")

            # Step 2: Select repair strategy
            strategy = self._select_strategy(repair_level)
            logger.info(f"Selected repair strategy: {strategy.name}")

            # Step 3: Execute repair
            context = {
                "task_id": task_id,
                "task_executor": self.task_executor,
                "recovery_engine": self.recovery_engine,
                "error_type": self.classifier.extract_error_type(task_run.error_msg),
                "severity": severity,
                "execution_trace": task_run.execution_trace,
            }

            with create_span(
                "defect_repair.execute",
                {"defect.type": context["error_type"], "repair.strategy": strategy.name},
            ):
                repair_result = await strategy.repair(
                    task_run.error_msg,
                    task_run.code,
                    context,
                )
            logger.info(f"Repair executed with status: {repair_result.status.value}")

            # Step 4: Verify repair result
            if repair_result.status == RepairStatus.SUCCESS:
                with create_span("defect_repair.verify", {"task.id": task_id}):
                    verified = await self._verify_repair(
                        task_id,
                        repair_result.repaired_code,
                        task_run,
                    )
                if not verified:
                    logger.warning(f"Repair verification failed for task {task_id}")
                    repair_result.status = RepairStatus.FAILED

            # Step 5: Store experience
            await self._store_experience(
                task_run,
                repair_level,
                repair_result,
            )

            # Step 6: Track repair history
            if task_id not in self._repair_history:
                self._repair_history[task_id] = []
            self._repair_history[task_id].append(repair_result)

            logger.info(
                f"Repair pipeline completed for task {task_id}: " f"{repair_result.status.value}"
            )
            return (repair_result.status, repair_result.repaired_code)

        except Exception as e:
            logger.error(f"Repair pipeline failed for task {task_id}: {str(e)}")
            return (RepairStatus.FAILED, None)

    def _select_strategy(self, repair_level) -> BaseRepairStrategy:
        """Select repair strategy based on repair level.

        Args:
            repair_level: Repair level from classifier

        Returns:
            Selected repair strategy
        """
        # Map classifier repair level to strategy level
        level_map = {
            "syntax_type_error": "L1",
            "logic_error": "L2",
            "performance_issue": "L3",
            "architecture_problem": "L4",
        }

        level_str = level_map.get(repair_level.value, "L2")
        return self.strategies.get(level_str, self.strategies["L2"])

    async def _verify_repair(
        self,
        task_id: str,
        repaired_code: Optional[str],
        task_run: TaskRun,
    ) -> bool:
        """Verify repair by re-executing the task.

        Args:
            task_id: Task identifier
            repaired_code: Repaired code to verify
            task_run: Original task run

        Returns:
            True if verification passed
        """
        if not repaired_code:
            return False

        try:
            logger.debug(f"Verifying repair for task {task_id}")

            # Re-execute with repaired code
            result = await self.task_executor.execute(task_id, repaired_code)

            if result.get("success"):
                logger.info(f"Repair verification passed for task {task_id}")
                return True
            else:
                logger.warning(f"Repair verification failed for task {task_id}")
                return False

        except Exception as e:
            logger.error(f"Repair verification error for task {task_id}: {str(e)}")
            return False

    async def _store_experience(
        self,
        task_run: TaskRun,
        repair_level,
        repair_result: RepairResult,
    ) -> None:
        """Store repair experience in memory system.

        Args:
            task_run: Original task run
            repair_level: Repair level used
            repair_result: Result of repair
        """
        try:
            error_type = self.classifier.extract_error_type(task_run.error_msg)

            experience = RepairExperience(
                task_id=task_run.task_id,
                error_type=error_type,
                repair_level=repair_level.value,
                repair_status=repair_result.status,
                original_code=task_run.code,
                repaired_code=repair_result.repaired_code,
                error_msg=task_run.error_msg,
                metadata={
                    "attempts": repair_result.attempts,
                    "execution_trace": task_run.execution_trace,
                },
            )

            self._experiences.append(experience)

            # Store in memory system if available
            if self.memory_system:
                await self._save_to_memory(experience)

            logger.debug(f"Repair experience stored for task {task_run.task_id}")

        except Exception as e:
            logger.error(f"Failed to store repair experience: {str(e)}")

    async def _save_to_memory(self, experience: RepairExperience) -> None:
        """Save repair experience to memory system.

        Args:
            experience: Repair experience to save
        """
        try:
            from agentManager.memory.memory_system import MemoryEntry, MemoryLayer

            entry = MemoryEntry(
                content=f"Repair: {experience.error_type} -> {experience.repair_status.value}",
                layer=MemoryLayer.MEDIUM_TERM,
                tags=["repair", experience.error_type, experience.repair_level],
                metadata={
                    "task_id": experience.task_id,
                    "error_type": experience.error_type,
                    "repair_level": experience.repair_level,
                    "status": experience.repair_status.value,
                    "attempts": experience.metadata.get("attempts", 0),
                },
            )

            self.memory_system.store(entry)
            logger.debug(f"Experience saved to memory for task {experience.task_id}")

        except Exception as e:
            logger.warning(f"Failed to save experience to memory: {str(e)}")

    def get_repair_history(self, task_id: str) -> List[RepairResult]:
        """Get repair history for a task.

        Args:
            task_id: Task identifier

        Returns:
            List of repair results
        """
        return self._repair_history.get(task_id, [])

    def get_experiences(self) -> List[RepairExperience]:
        """Get all stored repair experiences.

        Returns:
            List of repair experiences
        """
        return self._experiences.copy()

    def get_experience_stats(self) -> Dict[str, Any]:
        """Get statistics about repair experiences.

        Returns:
            Dictionary with repair statistics
        """
        if not self._experiences:
            return {
                "total_repairs": 0,
                "successful": 0,
                "failed": 0,
                "escalated": 0,
                "success_rate": 0.0,
            }

        total = len(self._experiences)
        successful = sum(1 for e in self._experiences if e.repair_status == RepairStatus.SUCCESS)
        failed = sum(1 for e in self._experiences if e.repair_status == RepairStatus.FAILED)
        escalated = sum(1 for e in self._experiences if e.repair_status == RepairStatus.ESCALATED)

        return {
            "total_repairs": total,
            "successful": successful,
            "failed": failed,
            "escalated": escalated,
            "success_rate": successful / total if total > 0 else 0.0,
            "by_level": self._get_stats_by_level(),
            "by_error_type": self._get_stats_by_error_type(),
        }

    def _get_stats_by_level(self) -> Dict[str, int]:
        """Get repair statistics by repair level.

        Returns:
            Dictionary with counts by level
        """
        stats = {}
        for experience in self._experiences:
            level = experience.repair_level
            stats[level] = stats.get(level, 0) + 1
        return stats

    def _get_stats_by_error_type(self) -> Dict[str, int]:
        """Get repair statistics by error type.

        Returns:
            Dictionary with counts by error type
        """
        stats = {}
        for experience in self._experiences:
            error_type = experience.error_type
            stats[error_type] = stats.get(error_type, 0) + 1
        return stats
