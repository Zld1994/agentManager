"""Defect repair pipeline for orchestrating L1-L4 repair strategies."""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional

from agentManager.defect_repair.defect_classifier import DefectClassifier
from agentManager.defect_repair.repair_strategies import (
    RepairResult,
    RepairStatus,
    RepairStrategyFactory,
)

logger = logging.getLogger(__name__)


@dataclass
class TaskRun:
    """Represents a task run with error information."""

    task_id: str
    workflow_id: str
    error: Optional[Exception] = None
    retry_count: int = 0
    status: str = "pending"
    result: Optional[Any] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)


@dataclass
class RepairExperience:
    """Stores repair experience for knowledge base."""

    task_id: str
    error_type: str
    repair_level: str
    repair_status: str
    message: str
    details: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "error_type": self.error_type,
            "repair_level": self.repair_level,
            "repair_status": self.repair_status,
            "message": self.message,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


class DefectRepairPipeline:
    """Orchestrates L1-L4 defect repair strategies."""

    def __init__(
        self,
        task_executor: Optional[Any] = None,
        recovery_engine: Optional[Any] = None,
        memory_system: Optional[Any] = None,
    ):
        """Initialize repair pipeline.

        Args:
            task_executor: TaskExecutor instance
            recovery_engine: RecoveryEngine instance
            memory_system: MemorySystem instance
        """
        self.task_executor = task_executor
        self.recovery_engine = recovery_engine
        self.memory_system = memory_system
        self.classifier = DefectClassifier()
        self.repair_history: List[RepairExperience] = []
        self.statistics = {
            "total_repairs": 0,
            "successful_repairs": 0,
            "failed_repairs": 0,
            "escalated_repairs": 0,
        }

    async def repair(self, task_run: TaskRun) -> RepairResult:
        """Execute repair pipeline.

        Args:
            task_run: Task run to repair

        Returns:
            Repair result
        """
        logger.info(f"Starting repair pipeline for task {task_run.task_id}")

        if not task_run.error:
            return RepairResult(
                status=RepairStatus.FAILED,
                level="UNKNOWN",
                message="No error to repair",
            )

        # Classify error
        error_type = self.classifier.classify(task_run.error)
        repair_level = self.classifier.recommend_repair_level(error_type)

        logger.info(
            f"Error classified as {error_type}, "
            f"recommended repair level: {repair_level}"
        )

        # Execute repair strategy
        strategy = RepairStrategyFactory.create_strategy(repair_level.value.upper())
        repair_result = await strategy.repair(task_run)

        # Update statistics
        self.statistics["total_repairs"] += 1
        if repair_result.status == RepairStatus.SUCCESS:
            self.statistics["successful_repairs"] += 1
        elif repair_result.status == RepairStatus.ESCALATED:
            self.statistics["escalated_repairs"] += 1
        else:
            self.statistics["failed_repairs"] += 1

        # Store experience
        await self._store_experience(
            task_run, error_type.value, repair_level.value, repair_result
        )

        logger.info(
            f"Repair completed with status: {repair_result.status}, "
            f"level: {repair_result.level}"
        )

        return repair_result

    async def _verify_repair(self, task_run: TaskRun) -> bool:
        """Verify repair success.

        Args:
            task_run: Task run to verify

        Returns:
            True if repair successful
        """
        logger.info(f"Verifying repair for task {task_run.task_id}")

        # In real implementation, would re-execute task
        return task_run.status == "completed"

    async def _store_experience(
        self,
        task_run: TaskRun,
        error_type: str,
        repair_level: str,
        repair_result: RepairResult,
    ) -> None:
        """Store repair experience in memory.

        Args:
            task_run: Task run
            error_type: Error type
            repair_level: Repair level
            repair_result: Repair result
        """
        experience = RepairExperience(
            task_id=task_run.task_id,
            error_type=error_type,
            repair_level=repair_level,
            repair_status=repair_result.status.value,
            message=repair_result.message,
            details=repair_result.details,
        )

        self.repair_history.append(experience)

        # Store in memory if available
        if self.memory_system:
            try:
                await self.memory_system.put(
                    namespace="engineering:repairs",
                    key=f"repair_{task_run.task_id}",
                    value=experience.to_dict(),
                )
                logger.info(f"Repair experience stored for task {task_run.task_id}")
            except Exception as e:
                logger.error(f"Failed to store repair experience: {e}")

    def get_statistics(self) -> Dict[str, int]:
        """Get repair statistics.

        Returns:
            Statistics dictionary
        """
        return self.statistics.copy()

    def get_history(self) -> List[RepairExperience]:
        """Get repair history.

        Returns:
            List of repair experiences
        """
        return self.repair_history.copy()
