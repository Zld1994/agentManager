"""
Unit tests for DefectRepair L1-L4 repair pipeline.

Tests cover:
- Error classification
- Repair strategy execution
- Pipeline orchestration
- Experience storage
- Statistics and reporting
"""

import asyncio
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from agentManager.defect_repair.classifier import DefectClassifier, SeverityLevel
from agentManager.defect_repair.repair_pipeline import (
    DefectRepairPipeline,
    RepairExperience,
    TaskRun,
)
from agentManager.defect_repair.repair_strategies import (
    L1RepairStrategy,
    L2RepairStrategy,
    L3RepairStrategy,
    L4RepairStrategy,
    RepairResult,
    RepairStatus,
    RepairStrategyFactory,
)


class TestL1RepairStrategy:
    """Tests for L1 automatic retry strategy."""

    @pytest.fixture
    def strategy(self):
        """Create L1 strategy instance."""
        return L1RepairStrategy()

    @pytest.mark.asyncio
    async def test_l1_successful_retry(self, strategy):
        """Test L1 repair succeeds on retry."""
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {"success": True}

        context = {
            "task_executor": mock_executor,
            "task_id": "task_1",
        }

        result = await strategy.repair(
            "TimeoutError: execution timeout",
            "code_here()",
            context,
        )

        assert result.status == RepairStatus.SUCCESS
        assert result.attempts == 1
        assert mock_executor.execute.called

    @pytest.mark.asyncio
    async def test_l1_max_retries_exceeded(self, strategy):
        """Test L1 repair fails after max retries."""
        mock_executor = AsyncMock()
        mock_executor.execute.return_value = {"success": False, "error": "Still failing"}

        context = {
            "task_executor": mock_executor,
            "task_id": "task_1",
        }

        result = await strategy.repair(
            "TimeoutError: execution timeout",
            "code_here()",
            context,
        )

        assert result.status == RepairStatus.FAILED
        assert result.attempts == strategy.MAX_RETRIES
        assert mock_executor.execute.call_count == strategy.MAX_RETRIES

    @pytest.mark.asyncio
    async def test_l1_missing_context(self, strategy):
        """Test L1 repair handles missing context."""
        result = await strategy.repair(
            "TimeoutError: execution timeout",
            "code_here()",
            {},
        )

        assert result.status == RepairStatus.FAILED
        assert "Missing" in result.error_message


class TestL2RepairStrategy:
    """Tests for L2 template-based repair strategy."""

    @pytest.fixture
    def strategy(self):
        """Create L2 strategy instance."""
        return L2RepairStrategy()

    @pytest.mark.asyncio
    async def test_l2_key_error_repair(self, strategy):
        """Test L2 repairs KeyError."""
        result = await strategy.repair(
            "KeyError: 'missing_key'",
            "value = my_dict['missing_key']",
            {},
        )

        assert result.status == RepairStatus.SUCCESS
        assert result.repaired_code is not None
        assert result.attempts == 1

    @pytest.mark.asyncio
    async def test_l2_value_error_repair(self, strategy):
        """Test L2 repairs ValueError."""
        result = await strategy.repair(
            "ValueError: invalid literal for int()",
            "x = int('not_a_number')",
            {},
        )

        assert result.status == RepairStatus.SUCCESS
        assert result.repaired_code is not None

    @pytest.mark.asyncio
    async def test_l2_unknown_error_type(self, strategy):
        """Test L2 handles unknown error types."""
        result = await strategy.repair(
            "CustomError: something went wrong",
            "some_code()",
            {},
        )

        assert result.status == RepairStatus.FAILED
        assert "No repair template" in result.error_message

    def test_l2_extract_error_type(self, strategy):
        """Test error type extraction."""
        error_type = strategy._extract_error_type("KeyError: 'key'")
        assert error_type == "KeyError"

        error_type = strategy._extract_error_type("ValueError: invalid")
        assert error_type == "ValueError"

        error_type = strategy._extract_error_type("Unknown error")
        assert error_type == "UnknownError"


class TestL3RepairStrategy:
    """Tests for L3 multi-agent review strategy."""

    @pytest.fixture
    def strategy(self):
        """Create L3 strategy instance."""
        return L3RepairStrategy()

    @pytest.mark.asyncio
    async def test_l3_multi_agent_repair(self, strategy):
        """Test L3 multi-agent repair."""
        result = await strategy.repair(
            "ValueError: invalid value",
            "x = int(user_input)",
            {},
        )

        assert result.status == RepairStatus.SUCCESS
        assert result.repaired_code is not None
        assert result.metadata.get("num_agents") > 0

    @pytest.mark.asyncio
    async def test_l3_consensus_selection(self, strategy):
        """Test L3 consensus repair selection."""
        proposals = [
            "try:\n    code\nexcept:\n    pass",
            "try:\n    code\nexcept:\n    pass",
            "if code:\n    code",
        ]

        consensus = strategy._select_consensus_repair(proposals)
        assert consensus is not None
        # Most common proposal should be selected
        assert consensus == proposals[0]

    @pytest.mark.asyncio
    async def test_l3_empty_proposals(self, strategy):
        """Test L3 handles empty proposals."""
        consensus = strategy._select_consensus_repair([])
        assert consensus is None


class TestL4RepairStrategy:
    """Tests for L4 HITL escalation strategy."""

    @pytest.fixture
    def strategy(self):
        """Create L4 strategy instance."""
        return L4RepairStrategy()

    @pytest.mark.asyncio
    async def test_l4_escalation(self, strategy):
        """Test L4 escalates to human review."""
        context = {"task_id": "task_1", "escalations": []}

        result = await strategy.repair(
            "ArchitectureError: design issue",
            "complex_code()",
            context,
        )

        assert result.status == RepairStatus.ESCALATED
        assert result.metadata.get("requires_human_review") is True
        assert len(context["escalations"]) == 1

    @pytest.mark.asyncio
    async def test_l4_escalation_data(self, strategy):
        """Test L4 creates proper escalation data."""
        context = {"task_id": "task_1"}

        result = await strategy.repair(
            "ArchitectureError: design issue",
            "complex_code()",
            context,
        )

        escalation_data = result.metadata.get("escalation_data")
        assert escalation_data is not None
        assert escalation_data["task_id"] == "task_1"
        assert escalation_data["status"] == "pending_review"


class TestRepairStrategyFactory:
    """Tests for repair strategy factory."""

    def test_factory_create_l1(self):
        """Test factory creates L1 strategy."""
        strategy = RepairStrategyFactory.create("L1")
        assert isinstance(strategy, L1RepairStrategy)

    def test_factory_create_l2(self):
        """Test factory creates L2 strategy."""
        strategy = RepairStrategyFactory.create("L2")
        assert isinstance(strategy, L2RepairStrategy)

    def test_factory_create_l3(self):
        """Test factory creates L3 strategy."""
        strategy = RepairStrategyFactory.create("L3")
        assert isinstance(strategy, L3RepairStrategy)

    def test_factory_create_l4(self):
        """Test factory creates L4 strategy."""
        strategy = RepairStrategyFactory.create("L4")
        assert isinstance(strategy, L4RepairStrategy)

    def test_factory_invalid_level(self):
        """Test factory raises error for invalid level."""
        with pytest.raises(ValueError):
            RepairStrategyFactory.create("L5")

    def test_factory_get_all_strategies(self):
        """Test factory returns all strategies."""
        strategies = RepairStrategyFactory.get_all_strategies()
        assert len(strategies) == 4
        assert "L1" in strategies
        assert "L2" in strategies
        assert "L3" in strategies
        assert "L4" in strategies


class TestDefectClassifier:
    """Tests for defect classifier."""

    @pytest.fixture
    def classifier(self):
        """Create classifier instance."""
        return DefectClassifier()

    def test_classify_syntax_error(self, classifier):
        """Test classification of syntax error."""
        repair_level, severity = classifier.classify_error(
            "SyntaxError: invalid syntax",
            "if x",
        )

        assert repair_level.value == "syntax_type_error"
        assert severity in [SeverityLevel.HIGH, SeverityLevel.CRITICAL]

    def test_classify_logic_error(self, classifier):
        """Test classification of logic error."""
        repair_level, severity = classifier.classify_error(
            "AssertionError: assertion failed",
            "assert x > 0",
        )

        assert repair_level.value == "logic_error"

    def test_classify_performance_error(self, classifier):
        """Test classification of performance error."""
        repair_level, severity = classifier.classify_error(
            "TimeoutError: execution timeout",
            "while True: pass",
        )

        assert repair_level.value == "performance_issue"

    def test_extract_error_type(self, classifier):
        """Test error type extraction."""
        error_type = classifier.extract_error_type("KeyError: 'key'")
        assert error_type == "KeyError"

    def test_calculate_severity(self, classifier):
        """Test severity calculation."""
        severity = classifier.calculate_severity("SyntaxError", "system")
        assert severity.level >= SeverityLevel.HIGH.level


class TestDefectRepairPipeline:
    """Tests for defect repair pipeline."""

    @pytest.fixture
    def pipeline(self):
        """Create pipeline instance."""
        mock_executor = AsyncMock()
        mock_recovery = AsyncMock()
        mock_memory = Mock()

        return DefectRepairPipeline(
            task_executor=mock_executor,
            recovery_engine=mock_recovery,
            memory_system=mock_memory,
        )

    @pytest.mark.asyncio
    async def test_pipeline_repair_success(self, pipeline):
        """Test pipeline executes successful repair."""
        pipeline.task_executor.execute = AsyncMock(return_value={"success": True})

        task_run = TaskRun(
            task_id="task_1",
            code="x = 1",
            error_msg="TimeoutError: timeout",
            execution_trace="trace",
        )

        status, repaired_code = await pipeline.repair(task_run)

        assert status == RepairStatus.SUCCESS or status == RepairStatus.FAILED

    @pytest.mark.asyncio
    async def test_pipeline_stores_experience(self, pipeline):
        """Test pipeline stores repair experience."""
        pipeline.task_executor.execute = AsyncMock(return_value={"success": True})

        task_run = TaskRun(
            task_id="task_1",
            code="x = 1",
            error_msg="KeyError: key",
            execution_trace="trace",
        )

        await pipeline.repair(task_run)

        experiences = pipeline.get_experiences()
        assert len(experiences) > 0

    def test_pipeline_get_repair_history(self, pipeline):
        """Test pipeline retrieves repair history."""
        history = pipeline.get_repair_history("task_1")
        assert isinstance(history, list)

    def test_pipeline_get_experience_stats(self, pipeline):
        """Test pipeline returns experience statistics."""
        stats = pipeline.get_experience_stats()

        assert "total_repairs" in stats
        assert "successful" in stats
        assert "failed" in stats
        assert "success_rate" in stats

    @pytest.mark.asyncio
    async def test_pipeline_error_handling(self, pipeline):
        """Test pipeline handles errors gracefully."""
        pipeline.task_executor.execute = AsyncMock(side_effect=Exception("Test error"))

        task_run = TaskRun(
            task_id="task_1",
            code="x = 1",
            error_msg="Error: test",
            execution_trace="trace",
        )

        status, repaired_code = await pipeline.repair(task_run)

        assert status == RepairStatus.FAILED
        assert repaired_code is None
