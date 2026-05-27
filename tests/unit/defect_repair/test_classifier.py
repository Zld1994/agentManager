"""
Unit tests for DefectClassifier - error classification and severity assessment.

Tests cover:
- Severity level enum and properties
- Defect pattern dataclass and matching
- Error classification for all repair levels
- Severity calculation based on impact scope
- Repair priority calculation
- Custom pattern registration
"""

import pytest

from agentManager.defect_repair.classifier import (
    DefectClassifier,
    DefectPattern,
    SeverityLevel,
)
from agentManager.defect_repair.repair_engine import RepairLevel


@pytest.fixture
def classifier():
    """Create a DefectClassifier instance."""
    return DefectClassifier()


class TestSeverityLevelEnum:
    """Test SeverityLevel enum and properties."""

    def test_severity_level_trivial(self):
        """Test TRIVIAL severity level."""
        assert SeverityLevel.TRIVIAL.level == 1
        assert SeverityLevel.TRIVIAL.description == "代码风格"

    def test_severity_level_low(self):
        """Test LOW severity level."""
        assert SeverityLevel.LOW.level == 2
        assert SeverityLevel.LOW.description == "性能下降"

    def test_severity_level_medium(self):
        """Test MEDIUM severity level."""
        assert SeverityLevel.MEDIUM.level == 3
        assert SeverityLevel.MEDIUM.description == "部分功能异常"

    def test_severity_level_high(self):
        """Test HIGH severity level."""
        assert SeverityLevel.HIGH.level == 4
        assert SeverityLevel.HIGH.description == "功能失效"

    def test_severity_level_critical(self):
        """Test CRITICAL severity level."""
        assert SeverityLevel.CRITICAL.level == 5
        assert SeverityLevel.CRITICAL.description == "系统崩溃"

    def test_severity_level_ordering(self):
        """Test severity level ordering."""
        levels = [
            SeverityLevel.TRIVIAL,
            SeverityLevel.LOW,
            SeverityLevel.MEDIUM,
            SeverityLevel.HIGH,
            SeverityLevel.CRITICAL,
        ]
        for i in range(len(levels) - 1):
            assert levels[i].level < levels[i + 1].level


class TestDefectPatternDataclass:
    """Test DefectPattern dataclass."""

    def test_defect_pattern_creation(self):
        """Test DefectPattern creation."""
        pattern = DefectPattern(
            pattern_name="TestError",
            regex_pattern=r"TestError|test error",
            repair_level=RepairLevel.L1_SYNTAX,
            severity=SeverityLevel.HIGH,
            description="Test error pattern",
        )

        assert pattern.pattern_name == "TestError"
        assert pattern.regex_pattern == r"TestError|test error"
        assert pattern.repair_level == RepairLevel.L1_SYNTAX
        assert pattern.severity == SeverityLevel.HIGH
        assert pattern.description == "Test error pattern"

    def test_defect_pattern_matches_basic(self):
        """Test basic pattern matching."""
        pattern = DefectPattern(
            pattern_name="SyntaxError",
            regex_pattern=r"SyntaxError|syntax error",
            repair_level=RepairLevel.L1_SYNTAX,
            severity=SeverityLevel.HIGH,
            description="Syntax error",
        )

        assert pattern.matches("SyntaxError: invalid syntax") is True
        assert pattern.matches("syntax error at line 10") is True
        assert pattern.matches("TypeError: type error") is False

    def test_defect_pattern_matches_case_insensitive(self):
        """Test case-insensitive pattern matching."""
        pattern = DefectPattern(
            pattern_name="Error",
            regex_pattern=r"error",
            repair_level=RepairLevel.L2_LOGIC,
            severity=SeverityLevel.MEDIUM,
            description="Generic error",
        )

        assert pattern.matches("ERROR") is True
        assert pattern.matches("Error") is True
        assert pattern.matches("error") is True

    def test_defect_pattern_matches_invalid_regex(self):
        """Test pattern matching with invalid regex."""
        pattern = DefectPattern(
            pattern_name="Invalid",
            regex_pattern=r"[invalid(regex",  # Invalid regex
            repair_level=RepairLevel.L1_SYNTAX,
            severity=SeverityLevel.MEDIUM,
            description="Invalid pattern",
        )

        # Should return False for invalid regex instead of raising
        assert pattern.matches("test") is False


class TestClassifyErrorSyntax:
    """Test error classification for syntax errors."""

    def test_classify_error_syntax(self, classifier):
        """Test classification of syntax errors."""
        error_msg = "SyntaxError: invalid syntax"
        code_context = "if x = 5:"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L1_SYNTAX
        assert severity == SeverityLevel.HIGH

    def test_classify_error_type_error(self, classifier):
        """Test classification of type errors."""
        error_msg = "TypeError: unsupported operand type(s)"
        code_context = "result = '5' + 10"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L1_SYNTAX
        assert severity == SeverityLevel.HIGH

    def test_classify_error_attribute_error(self, classifier):
        """Test classification of attribute errors."""
        error_msg = "AttributeError: 'str' object has no attribute 'foo'"
        code_context = "x = 'hello'\nx.foo()"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L1_SYNTAX
        assert severity == SeverityLevel.HIGH


class TestClassifyErrorLogic:
    """Test error classification for logic errors."""

    def test_classify_error_logic(self, classifier):
        """Test classification of logic errors."""
        error_msg = "AssertionError: assertion failed"
        code_context = "assert result == expected"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L2_LOGIC
        assert severity == SeverityLevel.MEDIUM

    def test_classify_error_value_error(self, classifier):
        """Test classification of value errors."""
        error_msg = "ValueError: invalid value"
        code_context = "int('not_a_number')"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L2_LOGIC
        assert severity == SeverityLevel.MEDIUM

    def test_classify_error_key_error(self, classifier):
        """Test classification of key errors."""
        error_msg = "KeyError: 'missing_key'"
        code_context = "data = {}\nvalue = data['missing_key']"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L2_LOGIC
        assert severity == SeverityLevel.MEDIUM


class TestClassifyErrorPerformance:
    """Test error classification for performance issues."""

    def test_classify_error_performance(self, classifier):
        """Test classification of performance errors."""
        error_msg = "TimeoutError: execution timeout"
        code_context = "while True: pass"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L3_PERFORMANCE
        assert severity == SeverityLevel.HIGH

    def test_classify_error_memory_error(self, classifier):
        """Test classification of memory errors."""
        error_msg = "MemoryError: out of memory"
        code_context = "data = [i for i in range(10**9)]"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L3_PERFORMANCE
        assert severity == SeverityLevel.CRITICAL


class TestClassifyErrorArchitecture:
    """Test error classification for architecture problems."""

    def test_classify_error_architecture(self, classifier):
        """Test classification of architecture errors."""
        error_msg = "ImportError: cannot import module"
        code_context = "from missing_module import func"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L4_ARCHITECTURE
        assert severity == SeverityLevel.HIGH

    def test_classify_error_circular_dependency(self, classifier):
        """Test classification of circular dependency errors."""
        error_msg = "circular import detected"
        code_context = "from module_a import func"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L4_ARCHITECTURE
        assert severity == SeverityLevel.CRITICAL


class TestExtractErrorType:
    """Test error type extraction."""

    def test_extract_error_type_syntax_error(self, classifier):
        """Test extraction of SyntaxError type."""
        error_msg = "SyntaxError: invalid syntax at line 10"

        error_type = classifier.extract_error_type(error_msg)

        assert error_type == "SyntaxError"

    def test_extract_error_type_type_error(self, classifier):
        """Test extraction of TypeError."""
        error_msg = "TypeError: unsupported operand type(s) for +: 'str' and 'int'"

        error_type = classifier.extract_error_type(error_msg)

        assert error_type == "TypeError"

    def test_extract_error_type_assertion_error(self, classifier):
        """Test extraction of AssertionError."""
        error_msg = "AssertionError: expected True but got False"

        error_type = classifier.extract_error_type(error_msg)

        assert error_type == "AssertionError"

    def test_extract_error_type_unknown(self, classifier):
        """Test extraction of unknown error type."""
        error_msg = "Some random error message without standard format"

        error_type = classifier.extract_error_type(error_msg)

        assert error_type == "unknown"


class TestCalculateSeverity:
    """Test severity calculation."""

    def test_calculate_severity_critical(self, classifier):
        """Test severity calculation for critical errors."""
        severity = classifier.calculate_severity("MemoryError", "system")

        assert severity == SeverityLevel.CRITICAL

    def test_calculate_severity_high(self, classifier):
        """Test severity calculation for high severity errors."""
        severity = classifier.calculate_severity("SyntaxError", "module")

        assert severity == SeverityLevel.HIGH

    def test_calculate_severity_medium(self, classifier):
        """Test severity calculation for medium severity errors."""
        severity = classifier.calculate_severity("ValueError", "local")

        assert severity == SeverityLevel.MEDIUM

    def test_calculate_severity_low(self, classifier):
        """Test severity calculation for low severity errors."""
        severity = classifier.calculate_severity("UnknownError", "local")

        assert severity == SeverityLevel.MEDIUM

    def test_calculate_severity_system_escalation(self, classifier):
        """Test severity escalation for system-wide impact."""
        # LOW severity error with system impact should escalate to HIGH
        severity = classifier.calculate_severity("UnknownError", "system")

        assert severity.level >= SeverityLevel.HIGH.level


class TestGetRepairPriority:
    """Test repair priority calculation."""

    def test_get_repair_priority_l1_critical(self, classifier):
        """Test priority for L1 syntax error with critical severity."""
        priority = classifier.get_repair_priority(RepairLevel.L1_SYNTAX, SeverityLevel.CRITICAL)

        assert 100 <= priority <= 120  # 80 * 1.5 = 120
        assert priority > 50

    def test_get_repair_priority_l1_medium(self, classifier):
        """Test priority for L1 syntax error with medium severity."""
        priority = classifier.get_repair_priority(RepairLevel.L1_SYNTAX, SeverityLevel.MEDIUM)

        assert priority == 80  # 80 * 1.0 = 80

    def test_get_repair_priority_l2_high(self, classifier):
        """Test priority for L2 logic error with high severity."""
        priority = classifier.get_repair_priority(RepairLevel.L2_LOGIC, SeverityLevel.HIGH)

        assert priority == 78  # 60 * 1.3 = 78

    def test_get_repair_priority_l3_low(self, classifier):
        """Test priority for L3 performance issue with low severity."""
        priority = classifier.get_repair_priority(RepairLevel.L3_PERFORMANCE, SeverityLevel.LOW)

        assert priority == 28  # 40 * 0.7 = 28

    def test_get_repair_priority_l4_critical(self, classifier):
        """Test priority for L4 architecture problem with critical severity."""
        priority = classifier.get_repair_priority(
            RepairLevel.L4_ARCHITECTURE, SeverityLevel.CRITICAL
        )

        assert priority == 75  # 50 * 1.5 = 75

    def test_get_repair_priority_clamped_to_100(self, classifier):
        """Test that priority is clamped to maximum 100."""
        # Create a scenario that would exceed 100
        priority = classifier.get_repair_priority(RepairLevel.L1_SYNTAX, SeverityLevel.CRITICAL)

        assert priority <= 100

    def test_get_repair_priority_clamped_to_1(self, classifier):
        """Test that priority is clamped to minimum 1."""
        # Create a scenario that would be below 1
        priority = classifier.get_repair_priority(RepairLevel.L3_PERFORMANCE, SeverityLevel.TRIVIAL)

        assert priority >= 1


class TestRegisterCustomPattern:
    """Test custom pattern registration."""

    def test_register_custom_pattern(self, classifier):
        """Test registering a custom defect pattern."""
        custom_pattern = DefectPattern(
            pattern_name="CustomError",
            regex_pattern=r"CustomError|custom error",
            repair_level=RepairLevel.L2_LOGIC,
            severity=SeverityLevel.MEDIUM,
            description="Custom error pattern",
        )

        initial_count = len(classifier.get_all_patterns())
        classifier.register_pattern(custom_pattern)

        assert len(classifier.get_all_patterns()) == initial_count + 1
        assert custom_pattern in classifier.get_all_patterns()

    def test_register_multiple_custom_patterns(self, classifier):
        """Test registering multiple custom patterns."""
        patterns = [
            DefectPattern(
                pattern_name=f"Custom{i}",
                regex_pattern=rf"custom{i}",
                repair_level=RepairLevel.L2_LOGIC,
                severity=SeverityLevel.MEDIUM,
                description=f"Custom pattern {i}",
            )
            for i in range(3)
        ]

        initial_count = len(classifier.get_all_patterns())
        for pattern in patterns:
            classifier.register_pattern(pattern)

        assert len(classifier.get_all_patterns()) == initial_count + 3

    def test_register_pattern_overwrites_existing(self, classifier):
        """Test that registering pattern with same name overwrites."""
        pattern1 = DefectPattern(
            pattern_name="TestPattern",
            regex_pattern=r"test1",
            repair_level=RepairLevel.L1_SYNTAX,
            severity=SeverityLevel.HIGH,
            description="Test pattern 1",
        )
        pattern2 = DefectPattern(
            pattern_name="TestPattern",
            regex_pattern=r"test2",
            repair_level=RepairLevel.L2_LOGIC,
            severity=SeverityLevel.MEDIUM,
            description="Test pattern 2",
        )

        classifier.register_pattern(pattern1)
        initial_count = len(classifier.get_all_patterns())
        classifier.register_pattern(pattern2)

        # Count should increase by 1 (new pattern added)
        assert len(classifier.get_all_patterns()) == initial_count + 1


class TestGetAllPatterns:
    """Test pattern retrieval."""

    def test_get_all_patterns_returns_list(self, classifier):
        """Test that get_all_patterns returns a list."""
        patterns = classifier.get_all_patterns()

        assert isinstance(patterns, list)
        assert len(patterns) > 0

    def test_get_all_patterns_includes_builtins(self, classifier):
        """Test that built-in patterns are included."""
        patterns = classifier.get_all_patterns()
        pattern_names = [p.pattern_name for p in patterns]

        assert "SyntaxError" in pattern_names
        assert "TypeError" in pattern_names
        assert "AssertionError" in pattern_names
        assert "MemoryError" in pattern_names
        assert "ImportError" in pattern_names

    def test_get_all_patterns_returns_copy(self, classifier):
        """Test that get_all_patterns returns a copy, not reference."""
        patterns1 = classifier.get_all_patterns()
        patterns2 = classifier.get_all_patterns()

        assert patterns1 is not patterns2
        assert patterns1 == patterns2


class TestPatternMatching:
    """Test pattern matching functionality."""

    def test_pattern_matching_exact(self, classifier):
        """Test exact pattern matching."""
        error_msg = "SyntaxError: invalid syntax"

        error_type = classifier.extract_error_type(error_msg)

        assert error_type == "SyntaxError"

    def test_pattern_matching_partial(self, classifier):
        """Test partial pattern matching."""
        error_msg = "This is a syntax error in the code"

        error_type = classifier.extract_error_type(error_msg)

        assert error_type == "SyntaxError"

    def test_pattern_matching_case_insensitive(self, classifier):
        """Test case-insensitive pattern matching."""
        error_msg = "TYPEERROR: unsupported operand"

        error_type = classifier.extract_error_type(error_msg)

        assert error_type == "TypeError"

    def test_pattern_matching_multiple_matches(self, classifier):
        """Test that first matching pattern is returned."""
        # Create error message that could match multiple patterns
        error_msg = "SyntaxError: invalid syntax"

        error_type = classifier.extract_error_type(error_msg)

        # Should match SyntaxError first
        assert error_type == "SyntaxError"

    def test_pattern_matching_no_match(self, classifier):
        """Test pattern matching with no matches."""
        error_msg = "SomeCompletelyUnknownError: something happened"

        error_type = classifier.extract_error_type(error_msg)

        assert error_type == "unknown"

    def test_classify_with_custom_pattern(self, classifier):
        """Test classification with custom registered pattern."""
        custom_pattern = DefectPattern(
            pattern_name="CustomLogicError",
            regex_pattern=r"custom logic error",
            repair_level=RepairLevel.L2_LOGIC,
            severity=SeverityLevel.HIGH,
            description="Custom logic error",
        )

        classifier.register_pattern(custom_pattern)
        error_msg = "custom logic error detected"
        code_context = "x = 5"

        repair_level, severity = classifier.classify_error(error_msg, code_context)

        assert repair_level == RepairLevel.L2_LOGIC
        assert severity == SeverityLevel.HIGH
