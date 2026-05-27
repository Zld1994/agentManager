"""
Unit tests for DefectRepairEngine - multi-level code defect repair engine.

Tests cover:
- Engine initialization with managers
- Defect analysis for all repair levels
- Repair execution for L1-L4 levels
- Repair history tracking
- Event publishing and error handling
"""

from collections import defaultdict
from datetime import datetime
from unittest.mock import Mock

import pytest

from agentManager.defect_repair.repair_engine import (
    DefectInfo,
    DefectRepairEngine,
    RepairLevel,
)


@pytest.fixture
def mock_checkpoint_manager():
    """Create a mock checkpoint manager."""
    return Mock()


@pytest.fixture
def mock_event_bus():
    """Create a mock event bus."""
    return Mock()


@pytest.fixture
def mock_state_manager():
    """Create a mock state manager."""
    return Mock()


@pytest.fixture
def repair_engine(mock_checkpoint_manager, mock_event_bus, mock_state_manager):
    """Create a DefectRepairEngine instance with mocked dependencies."""
    return DefectRepairEngine(
        checkpoint_manager=mock_checkpoint_manager,
        event_bus=mock_event_bus,
        state_manager=mock_state_manager,
    )


class TestDefectRepairEngineInit:
    """Test DefectRepairEngine initialization."""

    def test_init_with_managers(self, mock_checkpoint_manager, mock_event_bus, mock_state_manager):
        """Test engine initialization with all required managers."""
        engine = DefectRepairEngine(
            checkpoint_manager=mock_checkpoint_manager,
            event_bus=mock_event_bus,
            state_manager=mock_state_manager,
        )

        assert engine.checkpoint_manager is mock_checkpoint_manager
        assert engine.event_bus is mock_event_bus
        assert engine.state_manager is mock_state_manager
        assert isinstance(engine._repair_history, defaultdict)
        assert len(engine._repair_history) == 0


class TestDefectAnalysis:
    """Test defect analysis and classification."""

    def test_analyze_defect_syntax_error(self, repair_engine):
        """Test analysis of syntax errors."""
        error_msg = "SyntaxError: invalid syntax at line 10"
        code_context = "if x = 5:"
        execution_trace = "File 'test.py', line 10"

        result = repair_engine.analyze_defect(error_msg, code_context, execution_trace)

        assert result == RepairLevel.L1_SYNTAX

    def test_analyze_defect_type_error(self, repair_engine):
        """Test analysis of type errors."""
        error_msg = "TypeError: unsupported operand type(s)"
        code_context = "result = '5' + 10"
        execution_trace = "TypeError at line 5"

        result = repair_engine.analyze_defect(error_msg, code_context, execution_trace)

        assert result == RepairLevel.L1_SYNTAX

    def test_analyze_defect_logic_error(self, repair_engine):
        """Test analysis of logic errors."""
        error_msg = "AssertionError: expected True but got False"
        code_context = "assert result == expected"
        execution_trace = "AssertionError at line 20"

        result = repair_engine.analyze_defect(error_msg, code_context, execution_trace)

        assert result == RepairLevel.L2_LOGIC

    def test_analyze_defect_performance_error(self, repair_engine):
        """Test analysis of performance issues."""
        error_msg = "TimeoutError: execution timeout after 30s"
        code_context = "while True: pass"
        execution_trace = "Timeout at line 15"

        result = repair_engine.analyze_defect(error_msg, code_context, execution_trace)

        assert result == RepairLevel.L3_PERFORMANCE

    def test_analyze_defect_architecture_error(self, repair_engine):
        """Test analysis of architecture problems."""
        error_msg = "Architecture: circular dependency detected"
        code_context = "from module_a import func"
        execution_trace = "Import error at line 1"

        result = repair_engine.analyze_defect(error_msg, code_context, execution_trace)

        assert result == RepairLevel.L4_ARCHITECTURE

    def test_analyze_defect_default_to_logic(self, repair_engine):
        """Test that unknown errors default to logic error."""
        error_msg = "SomeUnknownError: something went wrong"
        code_context = "x = 5"
        execution_trace = "Unknown error"

        result = repair_engine.analyze_defect(error_msg, code_context, execution_trace)

        assert result == RepairLevel.L2_LOGIC


class TestL1SyntaxRepair:
    """Test L1 syntax and type error repair."""

    def test_repair_l1_syntax_basic(self, repair_engine):
        """Test basic L1 syntax repair."""
        code = "def foo():\n    x = 5\n    return x"
        error_msg = "SyntaxError: invalid syntax"

        result = repair_engine.repair_l1_syntax(code, error_msg)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_repair_l1_syntax_indentation(self, repair_engine):
        """Test L1 repair for indentation errors."""
        code = "def foo():\nx = 5"
        error_msg = "IndentationError: expected an indented block"

        result = repair_engine.repair_l1_syntax(code, error_msg)

        assert isinstance(result, str)
        # Should attempt to fix indentation
        assert "def foo():" in result

    def test_repair_l1_syntax_type_error(self, repair_engine):
        """Test L1 repair for type errors."""
        code = "result = '5' + 10"
        error_msg = "TypeError: unsupported operand type(s) for +: 'str' and 'int'"

        result = repair_engine.repair_l1_syntax(code, error_msg)

        assert isinstance(result, str)
        assert len(result) > 0


class TestL2LogicRepair:
    """Test L2 logic error repair."""

    def test_repair_l2_logic_with_test_cases(self, repair_engine):
        """Test L2 logic repair with test cases."""
        code = "def add(a, b):\n    return a - b"
        test_cases = ["add(2, 3) == 5", "add(10, 5) == 15"]
        error_msg = "AssertionError: expected 5 but got -1"

        result = repair_engine.repair_l2_logic(code, test_cases, error_msg)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_repair_l2_logic_empty_test_cases(self, repair_engine):
        """Test L2 repair with no test cases."""
        code = "def process(data):\n    return data"
        test_cases = []
        error_msg = "ValueError: invalid input"

        result = repair_engine.repair_l2_logic(code, test_cases, error_msg)

        assert isinstance(result, str)

    def test_repair_l2_logic_multiple_test_cases(self, repair_engine):
        """Test L2 repair with multiple test cases."""
        code = "def multiply(a, b):\n    return a + b"
        test_cases = [
            "multiply(2, 3) == 6",
            "multiply(5, 4) == 20",
            "multiply(0, 10) == 0",
        ]
        error_msg = "Logic error in multiplication"

        result = repair_engine.repair_l2_logic(code, test_cases, error_msg)

        assert isinstance(result, str)


class TestL3PerformanceRepair:
    """Test L3 performance issue repair."""

    def test_repair_l3_performance_optimization(self, repair_engine):
        """Test L3 performance optimization."""
        code = "for i in range(1000000):\n    x = i * 2"
        metrics = {"execution_time": 5.2, "memory_usage": 512}

        result = repair_engine.repair_l3_performance(code, metrics)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_repair_l3_performance_with_memory_metrics(self, repair_engine):
        """Test L3 repair with memory metrics."""
        code = "data = [i for i in range(1000000)]"
        metrics = {"memory_usage": 2048, "peak_memory": 2500}

        result = repair_engine.repair_l3_performance(code, metrics)

        assert isinstance(result, str)

    def test_repair_l3_performance_empty_metrics(self, repair_engine):
        """Test L3 repair with empty metrics."""
        code = "x = sum(range(1000))"
        metrics = {}

        result = repair_engine.repair_l3_performance(code, metrics)

        assert isinstance(result, str)


class TestL4ArchitectureRepair:
    """Test L4 architecture problem repair."""

    def test_repair_l4_architecture_refactoring(self, repair_engine):
        """Test L4 architecture refactoring."""
        code = "class A:\n    pass\nclass B:\n    pass"
        design_issues = ["Tight coupling", "Missing abstraction"]

        result = repair_engine.repair_l4_architecture(code, design_issues)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_repair_l4_architecture_single_issue(self, repair_engine):
        """Test L4 repair with single design issue."""
        code = "def process():\n    pass"
        design_issues = ["Circular dependency"]

        result = repair_engine.repair_l4_architecture(code, design_issues)

        assert isinstance(result, str)

    def test_repair_l4_architecture_no_issues(self, repair_engine):
        """Test L4 repair with no design issues."""
        code = "class Service:\n    pass"
        design_issues = []

        result = repair_engine.repair_l4_architecture(code, design_issues)

        assert isinstance(result, str)


class TestExecuteRepair:
    """Test repair execution workflow."""

    def test_execute_repair_success(self, repair_engine, mock_event_bus, mock_checkpoint_manager):
        """Test successful repair execution."""
        task_id = "task_001"
        defect_info = DefectInfo(
            task_id=task_id,
            error_msg="SyntaxError: invalid syntax",
            code_context="if x = 5:",
            execution_trace="File 'test.py', line 10",
            repair_level=RepairLevel.L1_SYNTAX,
            severity=4,
        )

        result = repair_engine.execute_repair(task_id, defect_info)

        assert result is True
        assert defect_info.repair_attempts == 1
        assert defect_info.last_repair_result is not None
        mock_event_bus.publish.assert_any_call(
            "repair_started",
            {
                "task_id": task_id,
                "level": "syntax_type_error",
                "severity": 4,
            },
        )
        mock_event_bus.publish.assert_any_call(
            "repair_completed",
            {
                "task_id": task_id,
                "level": "syntax_type_error",
                "attempts": 1,
            },
        )
        mock_checkpoint_manager.save.assert_called_once()

    def test_execute_repair_failure(self, repair_engine, mock_event_bus):
        """Test repair execution failure handling."""
        task_id = "task_002"
        defect_info = DefectInfo(
            task_id=task_id,
            error_msg="Unknown error",
            code_context="x = 5",
            execution_trace="Unknown",
            repair_level=RepairLevel.L2_LOGIC,
            severity=3,
        )

        # Mock checkpoint_manager to raise exception
        repair_engine.checkpoint_manager.save.side_effect = Exception("Save failed")

        result = repair_engine.execute_repair(task_id, defect_info)

        assert result is False
        mock_event_bus.publish.assert_any_call(
            "repair_failed",
            {
                "task_id": task_id,
                "error": "Save failed",
            },
        )

    def test_execute_repair_all_levels(self, repair_engine):
        """Test repair execution for all repair levels."""
        task_id = "task_003"

        for level in RepairLevel:
            defect_info = DefectInfo(
                task_id=f"{task_id}_{level.value}",
                error_msg="Test error",
                code_context="x = 5",
                execution_trace="Test trace",
                repair_level=level,
                severity=3,
            )

            result = repair_engine.execute_repair(f"{task_id}_{level.value}", defect_info)

            assert result is True
            assert defect_info.repair_attempts == 1


class TestRepairHistory:
    """Test repair history tracking."""

    def test_get_repair_history_empty(self, repair_engine):
        """Test getting repair history for task with no repairs."""
        task_id = "task_empty"

        history = repair_engine.get_repair_history(task_id)

        assert isinstance(history, list)
        assert len(history) == 0

    def test_get_repair_history_single(self, repair_engine):
        """Test getting repair history with single repair."""
        task_id = "task_single"
        defect_info = DefectInfo(
            task_id=task_id,
            error_msg="SyntaxError",
            code_context="code",
            execution_trace="trace",
            repair_level=RepairLevel.L1_SYNTAX,
            severity=4,
        )

        repair_engine.execute_repair(task_id, defect_info)
        history = repair_engine.get_repair_history(task_id)

        assert len(history) == 1
        assert history[0].task_id == task_id

    def test_get_repair_history_multiple(self, repair_engine):
        """Test getting repair history with multiple repairs."""
        task_id = "task_multiple"

        for i in range(3):
            defect_info = DefectInfo(
                task_id=task_id,
                error_msg=f"Error {i}",
                code_context=f"code_{i}",
                execution_trace=f"trace_{i}",
                repair_level=RepairLevel.L1_SYNTAX,
                severity=i + 1,
            )
            repair_engine.execute_repair(task_id, defect_info)

        history = repair_engine.get_repair_history(task_id)

        assert len(history) == 3
        assert all(h.task_id == task_id for h in history)


class TestDefectInfoDataclass:
    """Test DefectInfo dataclass."""

    def test_defect_info_creation(self):
        """Test DefectInfo creation with all fields."""
        task_id = "task_001"
        error_msg = "Test error"
        code_context = "x = 5"
        execution_trace = "trace"
        repair_level = RepairLevel.L1_SYNTAX
        severity = 4

        defect_info = DefectInfo(
            task_id=task_id,
            error_msg=error_msg,
            code_context=code_context,
            execution_trace=execution_trace,
            repair_level=repair_level,
            severity=severity,
        )

        assert defect_info.task_id == task_id
        assert defect_info.error_msg == error_msg
        assert defect_info.code_context == code_context
        assert defect_info.execution_trace == execution_trace
        assert defect_info.repair_level == repair_level
        assert defect_info.severity == severity
        assert defect_info.repair_attempts == 0
        assert defect_info.last_repair_result is None
        assert isinstance(defect_info.timestamp, datetime)

    def test_defect_info_with_custom_timestamp(self):
        """Test DefectInfo with custom timestamp."""
        custom_time = datetime(2026, 5, 23, 10, 0, 0)
        defect_info = DefectInfo(
            task_id="task_001",
            error_msg="Error",
            code_context="code",
            execution_trace="trace",
            repair_level=RepairLevel.L2_LOGIC,
            severity=3,
            timestamp=custom_time,
        )

        assert defect_info.timestamp == custom_time

    def test_defect_info_repair_tracking(self):
        """Test DefectInfo repair attempt tracking."""
        defect_info = DefectInfo(
            task_id="task_001",
            error_msg="Error",
            code_context="code",
            execution_trace="trace",
            repair_level=RepairLevel.L1_SYNTAX,
            severity=4,
        )

        assert defect_info.repair_attempts == 0
        defect_info.repair_attempts += 1
        assert defect_info.repair_attempts == 1

        defect_info.last_repair_result = "repaired code"
        assert defect_info.last_repair_result == "repaired code"
