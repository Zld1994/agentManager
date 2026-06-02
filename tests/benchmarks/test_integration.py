"""
Integration tests for performance benchmarking and reporting system
"""

from datetime import datetime

import pytest

from tests.benchmarks.generate_reports import ReportGenerator
from tests.benchmarks.performance_analysis import PerformanceAnalyzer


@pytest.fixture
def integration_metrics():
    """Comprehensive metrics for integration testing"""
    return [
        {
            "test_name": "test_worker_throughput",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": 30.0,
            "task_count": 3000,
            "completed_tasks": 2850,
            "failed_tasks": 150,
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
            "test_name": "test_memory_efficiency",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": 25.0,
            "task_count": 2500,
            "completed_tasks": 2450,
            "failed_tasks": 50,
            "throughput": 98.0,
            "latency_p50": 9.2,
            "latency_p95": 22.1,
            "latency_p99": 38.5,
            "latency_avg": 13.8,
            "latency_min": 4.2,
            "latency_max": 42.0,
            "memory_peak": 180.2,
            "memory_avg": 150.5,
            "cpu_peak": 42.5,
            "cpu_avg": 32.2,
            "error_rate": 2.0,
        },
        {
            "test_name": "test_concurrent_load",
            "timestamp": datetime.now().isoformat(),
            "duration_seconds": 40.0,
            "task_count": 4000,
            "completed_tasks": 3600,
            "failed_tasks": 400,
            "throughput": 90.0,
            "latency_p50": 12.0,
            "latency_p95": 35.0,
            "latency_p99": 60.0,
            "latency_avg": 18.5,
            "latency_min": 6.0,
            "latency_max": 75.0,
            "memory_peak": 450.0,
            "memory_avg": 350.0,
            "cpu_peak": 75.0,
            "cpu_avg": 60.0,
            "error_rate": 10.0,
        },
    ]


class TestIntegration:
    """Integration tests for the complete benchmarking system"""

    def test_end_to_end_report_generation(self, integration_metrics, tmp_path):
        """Test complete workflow from metrics to reports"""
        # Generate reports
        gen = ReportGenerator(output_dir=str(tmp_path))

        html_path = gen.generate_html_report(integration_metrics)
        md_path = gen.generate_markdown_report(integration_metrics)
        summary = gen.generate_summary_report(integration_metrics)

        # Verify all outputs exist
        assert html_path.exists()
        assert md_path.exists()
        assert summary is not None

        # Verify content
        html_content = html_path.read_text()
        md_content = md_path.read_text()

        assert "test_worker_throughput" in html_content
        assert "test_memory_efficiency" in md_content
        assert summary["test_count"] == 3

    def test_analysis_with_reports(self, integration_metrics, tmp_path):
        """Test analysis generation alongside reports"""
        gen = ReportGenerator(output_dir=str(tmp_path))
        analyzer = PerformanceAnalyzer()

        # Generate analysis
        analysis = analyzer.generate_analysis_report(integration_metrics)

        # Generate reports
        gen.generate_html_report(integration_metrics)
        gen.generate_markdown_report(integration_metrics)

        # Verify analysis
        assert analysis["metrics_analyzed"] == 3
        assert "insights" in analysis
        assert "bottlenecks" in analysis

    def test_bottleneck_identification(self, integration_metrics):
        """Test bottleneck identification across metrics"""
        analyzer = PerformanceAnalyzer()
        bottlenecks = analyzer.identify_bottlenecks(integration_metrics)

        # Verify bottleneck structure
        assert len(bottlenecks["throughput_bottlenecks"]) > 0
        assert len(bottlenecks["latency_bottlenecks"]) > 0
        assert len(bottlenecks["memory_bottlenecks"]) > 0
        assert len(bottlenecks["cpu_bottlenecks"]) > 0

        # Verify ranking
        for category in ["throughput_bottlenecks", "latency_bottlenecks"]:
            if bottlenecks[category]:
                assert bottlenecks[category][0]["rank"] == 1

    def test_baseline_workflow(self, integration_metrics, tmp_path):
        """Test baseline creation and comparison workflow"""
        baseline_file = tmp_path / "baselines.json"

        # Create initial analyzer and save baselines
        analyzer1 = PerformanceAnalyzer()
        for metric in integration_metrics:
            from tests.benchmarks.performance_analysis import PerformanceBaseline

            analyzer1.baselines[metric["test_name"]] = PerformanceBaseline(
                test_name=metric["test_name"],
                throughput=metric["throughput"],
                latency_p95=metric["latency_p95"],
                memory_peak=metric["memory_peak"],
                cpu_peak=metric["cpu_peak"],
                error_rate=metric["error_rate"],
                timestamp=metric["timestamp"],
            )
        analyzer1.save_baselines(str(baseline_file))

        # Load baselines and compare
        analyzer2 = PerformanceAnalyzer(str(baseline_file))
        comparison = analyzer2.compare_with_baseline(integration_metrics)

        assert comparison["tests_compared"] > 0
        assert "summary" in comparison

    def test_insights_generation(self, integration_metrics):
        """Test insight generation for various scenarios"""
        analyzer = PerformanceAnalyzer()
        insights = analyzer.analyze_metrics(integration_metrics)

        # Should detect high error rate in test_concurrent_load
        error_insights = [i for i in insights if i.category == "error"]
        assert len(error_insights) > 0

        # Should have some insights generated
        assert len(insights) > 0

        # Verify insight structure
        for insight in insights:
            assert hasattr(insight, "category")
            assert hasattr(insight, "severity")
            assert hasattr(insight, "message")

    def test_report_consistency(self, integration_metrics, tmp_path):
        """Test that reports contain consistent data"""
        gen = ReportGenerator(output_dir=str(tmp_path))

        html_path = gen.generate_html_report(integration_metrics)
        summary = gen.generate_summary_report(integration_metrics)

        html_content = html_path.read_text()

        # Verify key metrics appear in both
        assert (
            str(round(summary["summary_metrics"]["avg_throughput"], 2)) in html_content
            or str(int(summary["summary_metrics"]["avg_throughput"])) in html_content
        )
