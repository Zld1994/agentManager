"""
Unit tests for benchmark runner and performance metrics.

Tests cover:
1. PerformanceMetrics class functionality
2. BenchmarkRunner metrics collection
3. Export functionality (CSV, JSON, HTML)
4. Report generation
"""

import json
import csv
from tests.benchmarks.benchmark_runner import BenchmarkRunner, PerformanceMetrics, MetricUnit


class TestPerformanceMetrics:
    """Test PerformanceMetrics class"""

    def test_metrics_initialization(self):
        """Test metrics object initialization"""
        metrics = PerformanceMetrics(test_name="test_init")

        assert metrics.test_name == "test_init"
        assert metrics.task_count == 0
        assert metrics.completed_tasks == 0
        assert metrics.failed_tasks == 0
        assert metrics.throughput == 0.0
        assert metrics.latency_p95 == 0.0
        assert metrics.memory_peak == 0.0
        assert metrics.cpu_peak == 0.0
        assert metrics.error_rate == 0.0

    def test_metrics_to_dict(self):
        """Test conversion to dictionary"""
        metrics = PerformanceMetrics(test_name="test_dict")
        metrics.throughput = 100.0
        metrics.latency_p95 = 50.0

        data = metrics.to_dict()

        assert isinstance(data, dict)
        assert data["test_name"] == "test_dict"
        assert data["throughput"] == 100.0
        assert data["latency_p95"] == 50.0
        assert "latencies" not in data
        assert "memory_samples" not in data
        assert "cpu_samples" not in data

    def test_calculate_percentiles(self):
        """Test latency percentile calculation"""
        metrics = PerformanceMetrics(test_name="test_percentiles")

        # Add 100 latency samples (in seconds)
        metrics.latencies = [0.001 + (i * 0.0001) for i in range(100)]
        metrics.calculate_percentiles()

        assert metrics.latency_p50 > 0
        assert metrics.latency_p95 > metrics.latency_p50
        assert metrics.latency_p99 > metrics.latency_p95
        assert metrics.latency_avg > 0
        assert metrics.latency_min > 0
        assert metrics.latency_max > 0

    def test_calculate_resource_metrics(self):
        """Test resource metric calculations"""
        metrics = PerformanceMetrics(test_name="test_resources")

        # Add memory samples (in MB)
        metrics.memory_samples = [100 + i for i in range(50)]

        # Add CPU samples (in %)
        metrics.cpu_samples = [20 + (i * 0.5) for i in range(50)]

        metrics.calculate_resource_metrics()

        assert metrics.memory_peak == 149
        assert metrics.memory_avg > 100
        assert metrics.cpu_peak > 20
        assert metrics.cpu_avg > 20

    def test_calculate_error_rate(self):
        """Test error rate calculation"""
        metrics = PerformanceMetrics(test_name="test_errors")
        metrics.completed_tasks = 95
        metrics.failed_tasks = 5

        metrics.calculate_error_rate()

        assert metrics.error_rate == 5.0

    def test_finalize_metrics(self):
        """Test finalize method"""
        metrics = PerformanceMetrics(test_name="test_finalize")
        metrics.task_count = 100
        metrics.completed_tasks = 90
        metrics.failed_tasks = 10
        metrics.duration_seconds = 10.0
        metrics.latencies = [0.01 + (i * 0.0001) for i in range(90)]
        metrics.memory_samples = [100 + i for i in range(50)]
        metrics.cpu_samples = [25 + (i * 0.1) for i in range(50)]

        metrics.finalize()

        assert metrics.throughput == 9.0  # 90 tasks / 10 seconds
        assert metrics.latency_p95 > 0
        assert metrics.memory_peak > 0
        assert metrics.cpu_peak > 0
        assert metrics.error_rate == 10.0


class TestBenchmarkRunner:
    """Test BenchmarkRunner class"""

    def test_runner_initialization(self, tmp_path):
        """Test benchmark runner initialization"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))

        assert runner.output_dir == tmp_path
        assert runner.metrics == []
        assert runner.monitoring_active is False

    def test_collect_metrics(self, tmp_path):
        """Test metrics collection"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))

        def sample_test():
            """Sample test function"""
            completed = 10
            failed = 0
            latencies = [0.01 for _ in range(10)]
            return 10, completed, failed, latencies

        metrics = runner.collect_metrics("sample_test", sample_test)

        assert metrics.test_name == "sample_test"
        assert metrics.task_count == 10
        assert metrics.completed_tasks == 10
        assert metrics.failed_tasks == 0
        assert metrics.throughput > 0

    def test_run_all_benchmarks(self, tmp_path):
        """Test running multiple benchmarks"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))

        def test1():
            return 5, 5, 0, [0.01] * 5

        def test2():
            return 10, 10, 0, [0.02] * 10

        benchmarks = [
            ("test1", test1),
            ("test2", test2),
        ]

        results = runner.run_all_benchmarks(benchmarks)

        assert len(results) == 2
        assert results[0].test_name == "test1"
        assert results[1].test_name == "test2"
        assert len(runner.metrics) == 2

    def test_generate_report(self, tmp_path, sample_metrics):
        """Test report generation"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))
        runner.metrics = [sample_metrics]

        report = runner.generate_report()

        assert "timestamp" in report
        assert "total_tests" in report
        assert "tests" in report
        assert "summary" in report
        assert report["total_tests"] == 1
        assert len(report["tests"]) == 1

    def test_generate_summary(self, tmp_path):
        """Test summary generation"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))

        # Add multiple metrics
        for i in range(3):
            metrics = PerformanceMetrics(test_name=f"test_{i}")
            metrics.throughput = 100.0 + (i * 10)
            metrics.latency_p95 = 50.0 + (i * 5)
            metrics.memory_peak = 200.0 + (i * 20)
            metrics.cpu_peak = 50.0 + (i * 5)
            metrics.error_rate = 1.0 + (i * 0.5)
            runner.metrics.append(metrics)

        summary = runner._generate_summary()

        assert "avg_throughput" in summary
        assert "avg_latency_p95" in summary
        assert "max_memory_peak" in summary
        assert "max_cpu_peak" in summary
        assert "avg_error_rate" in summary
        assert summary["avg_throughput"] > 0


class TestExportFunctionality:
    """Test export functionality"""

    def test_export_to_csv(self, tmp_path, sample_metrics):
        """Test CSV export"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))
        runner.metrics = [sample_metrics]

        csv_path = runner.export_to_csv("test_export.csv")

        assert csv_path is not None
        assert csv_path.exists()
        assert csv_path.suffix == ".csv"

        # Verify CSV content
        with open(csv_path, "r") as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            assert len(rows) == 1
            assert rows[0]["test_name"] == "sample_test"
            assert float(rows[0]["throughput"]) > 0

    def test_export_to_json(self, tmp_path, sample_metrics):
        """Test JSON export"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))
        runner.metrics = [sample_metrics]

        json_path = runner.export_to_json("test_export.json")

        assert json_path is not None
        assert json_path.exists()
        assert json_path.suffix == ".json"

        # Verify JSON content
        with open(json_path, "r") as f:
            data = json.load(f)
            assert "timestamp" in data
            assert "total_tests" in data
            assert "tests" in data
            assert len(data["tests"]) == 1

    def test_export_to_html(self, tmp_path, sample_metrics):
        """Test HTML export"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))
        runner.metrics = [sample_metrics]

        html_path = runner.export_to_html("test_export.html")

        assert html_path is not None
        assert html_path.exists()
        assert html_path.suffix == ".html"

        # Verify HTML content
        with open(html_path, "r") as f:
            content = f.read()
            assert "Performance Benchmark Report" in content
            assert "Chart" in content
            assert "sample_test" in content

    def test_export_with_default_filename(self, tmp_path, sample_metrics):
        """Test export with auto-generated filename"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))
        runner.metrics = [sample_metrics]

        csv_path = runner.export_to_csv()
        json_path = runner.export_to_json()
        html_path = runner.export_to_html()

        assert csv_path is not None
        assert json_path is not None
        assert html_path is not None
        assert csv_path.exists()
        assert json_path.exists()
        assert html_path.exists()

    def test_export_empty_metrics(self, tmp_path):
        """Test export with no metrics"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))

        csv_path = runner.export_to_csv()
        json_path = runner.export_to_json()
        html_path = runner.export_to_html()

        assert csv_path is None
        assert json_path is None
        assert html_path is None


class TestMetricUnit:
    """Test MetricUnit enum"""

    def test_metric_units(self):
        """Test metric unit values"""
        assert MetricUnit.TASKS_PER_SECOND.value == "tasks/sec"
        assert MetricUnit.MILLISECONDS.value == "ms"
        assert MetricUnit.MEGABYTES.value == "MB"
        assert MetricUnit.PERCENT.value == "%"


class TestBenchmarkIntegration:
    """Integration tests for benchmark system"""

    def test_full_benchmark_workflow(self, tmp_path):
        """Test complete benchmark workflow"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))

        def benchmark_task():
            completed = 20
            failed = 0
            latencies = [0.01 + (i * 0.0001) for i in range(20)]
            return 20, completed, failed, latencies

        # Run benchmark
        metrics = runner.collect_metrics("integration_test", benchmark_task)
        runner.metrics.append(metrics)  # Add to runner's metrics list

        # Verify metrics
        assert metrics.test_name == "integration_test"
        assert metrics.completed_tasks == 20
        assert metrics.throughput > 0

        # Generate report
        report = runner.generate_report()
        assert report["total_tests"] == 1

        # Export to all formats
        csv_path = runner.export_to_csv()
        json_path = runner.export_to_json()
        html_path = runner.export_to_html()

        assert csv_path.exists()
        assert json_path.exists()
        assert html_path.exists()

    def test_multiple_benchmarks_workflow(self, tmp_path):
        """Test workflow with multiple benchmarks"""
        runner = BenchmarkRunner(output_dir=str(tmp_path))

        benchmarks = [
            ("bench_1", lambda: (10, 10, 0, [0.01] * 10)),
            ("bench_2", lambda: (20, 20, 0, [0.02] * 20)),
            ("bench_3", lambda: (15, 14, 1, [0.015] * 14)),
        ]

        results = runner.run_all_benchmarks(benchmarks)

        assert len(results) == 3
        assert all(r.throughput > 0 for r in results)

        # Generate comprehensive report
        report = runner.generate_report()
        assert report["total_tests"] == 3

        summary = report["summary"]
        assert summary["avg_throughput"] > 0
        assert summary["avg_error_rate"] >= 0
