"""
Tests for performance report generation module
"""

from datetime import datetime

import pytest

from tests.benchmarks.generate_reports import ReportGenerator


@pytest.fixture
def report_generator(tmp_path):
    """Create report generator with temporary output directory"""
    return ReportGenerator(output_dir=str(tmp_path))


@pytest.fixture
def sample_metrics():
    """Sample benchmark metrics for testing"""
    return [
        {
            "test_name": "test_throughput_basic",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": 10.0,
            "task_count": 1000,
            "completed_tasks": 950,
            "failed_tasks": 50,
            "throughput": 95.0,
            "latency_p50": 10.5,
            "latency_p95": 25.3,
            "latency_p99": 45.2,
            "latency_avg": 15.2,
            "latency_min": 5.1,
            "latency_max": 50.0,
            "memory_peak": 256.5,
            "memory_avg": 200.3,
            "cpu_peak": 45.2,
            "cpu_avg": 35.1,
            "error_rate": 5.0,
        },
        {
            "test_name": "test_latency_optimization",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": 15.0,
            "task_count": 1500,
            "completed_tasks": 1450,
            "failed_tasks": 50,
            "throughput": 96.7,
            "latency_p50": 9.2,
            "latency_p95": 22.1,
            "latency_p99": 38.5,
            "latency_avg": 13.8,
            "latency_min": 4.2,
            "latency_max": 42.0,
            "memory_peak": 280.2,
            "memory_avg": 215.5,
            "cpu_peak": 48.5,
            "cpu_avg": 38.2,
            "error_rate": 3.3,
        },
    ]


class TestReportGenerator:
    """Tests for ReportGenerator class"""

    def test_initialization(self, tmp_path):
        """Test report generator initialization"""
        gen = ReportGenerator(output_dir=str(tmp_path))
        assert gen.output_dir == tmp_path
        assert gen.system_info is not None

    def test_system_info_capture(self, report_generator):
        """Test system information capture"""
        info = report_generator.system_info
        assert info.os_name is not None
        assert info.python_version is not None
        assert info.processor_count > 0
        assert info.total_memory_gb > 0

    def test_generate_html_report(self, report_generator, sample_metrics):
        """Test HTML report generation"""
        output_path = report_generator.generate_html_report(sample_metrics)

        assert output_path.exists()
        assert output_path.suffix == ".html"

        content = output_path.read_text()
        assert "<!DOCTYPE html>" in content
        assert "Performance Benchmark Report" in content
        assert "test_throughput_basic" in content
        assert "chart" in content.lower()

    def test_generate_markdown_report(self, report_generator, sample_metrics):
        """Test Markdown report generation"""
        output_path = report_generator.generate_markdown_report(sample_metrics)

        assert output_path.exists()
        assert output_path.suffix == ".md"

        content = output_path.read_text()
        assert "# Performance Benchmark Report" in content
        assert "System Information" in content
        assert "test_throughput_basic" in content
        assert "| Test Name |" in content

    def test_generate_summary_report(self, report_generator, sample_metrics):
        """Test summary report generation"""
        summary = report_generator.generate_summary_report(sample_metrics)

        assert "timestamp" in summary
        assert "system_info" in summary
        assert "summary_metrics" in summary
        assert "test_count" in summary
        assert "tests" in summary
        assert "recommendations" in summary

        assert summary["test_count"] == 2
        assert summary["system_info"]["os"] is not None
        assert summary["summary_metrics"]["avg_throughput"] > 0

    def test_calculate_summary(self, report_generator, sample_metrics):
        """Test summary calculation"""
        summary = report_generator._calculate_summary(sample_metrics)

        assert "avg_throughput" in summary
        assert "avg_latency_p95" in summary
        assert "max_memory_peak" in summary
        assert "avg_cpu_peak" in summary
        assert "avg_error_rate" in summary

        assert summary["avg_throughput"] > 0
        assert summary["avg_latency_p95"] > 0

    def test_generate_recommendations(self, report_generator, sample_metrics):
        """Test recommendation generation"""
        summary = report_generator._calculate_summary(sample_metrics)
        recommendations = report_generator._generate_recommendations(sample_metrics, summary)

        assert isinstance(recommendations, list)
        assert len(recommendations) > 0

    def test_html_report_contains_metrics(self, report_generator, sample_metrics):
        """Test that HTML report contains all metrics"""
        output_path = report_generator.generate_html_report(sample_metrics)
        content = output_path.read_text()

        # Check for metric values
        assert "95.00" in content  # throughput
        assert "25.30" in content  # latency_p95
        assert "256.50" in content  # memory_peak
        assert "45.20" in content  # cpu_peak

    def test_markdown_report_contains_tables(self, report_generator, sample_metrics):
        """Test that Markdown report contains tables"""
        output_path = report_generator.generate_markdown_report(sample_metrics)
        content = output_path.read_text()

        # Check for table markers
        assert "|" in content
        assert "---" in content
        assert "Detailed Results" in content
        assert "Latency Distribution" in content
        assert "Resource Usage Summary" in content

    def test_custom_output_path(self, report_generator, sample_metrics, tmp_path):
        """Test custom output path"""
        custom_path = tmp_path / "custom_report.html"
        output_path = report_generator.generate_html_report(sample_metrics, str(custom_path))

        assert output_path == custom_path
        assert output_path.exists()

    def test_empty_metrics(self, report_generator):
        """Test handling of empty metrics"""
        summary = report_generator._calculate_summary([])
        assert summary == {}

    def test_chart_script_generation(self, report_generator, sample_metrics):
        """Test chart script generation"""
        script = report_generator._generate_chart_scripts(sample_metrics)

        assert "Chart" in script
        assert "throughputChart" in script
        assert "latencyChart" in script
        assert "resourceChart" in script
