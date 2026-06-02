"""
Performance Benchmark Runner and Metrics Collection

Provides comprehensive performance testing, metrics collection, and reporting
for the agentManager system. Supports multiple export formats (CSV, JSON, HTML).
"""

import json
import csv
import time
import psutil
import statistics
import logging
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict, field
from enum import Enum
import threading

logger = logging.getLogger(__name__)


class MetricUnit(Enum):
    """Units for performance metrics"""

    TASKS_PER_SECOND = "tasks/sec"
    MILLISECONDS = "ms"
    MEGABYTES = "MB"
    PERCENT = "%"


@dataclass
class PerformanceMetrics:
    """
    Comprehensive performance metrics collection.

    Tracks:
    - throughput (tasks/sec)
    - latency percentiles (p50, p95, p99 in ms)
    - memory usage (peak and average in MB)
    - CPU usage (peak and average in %)
    - error rate (%)
    """

    test_name: str
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_seconds: float = 0.0
    task_count: int = 0
    completed_tasks: int = 0
    failed_tasks: int = 0

    # Throughput metrics
    throughput: float = 0.0  # tasks/sec

    # Latency metrics (in ms)
    latency_p50: float = 0.0
    latency_p95: float = 0.0
    latency_p99: float = 0.0
    latency_avg: float = 0.0
    latency_min: float = 0.0
    latency_max: float = 0.0

    # Memory metrics (in MB)
    memory_peak: float = 0.0
    memory_avg: float = 0.0

    # CPU metrics (in %)
    cpu_peak: float = 0.0
    cpu_avg: float = 0.0

    # Error metrics
    error_rate: float = 0.0

    # Raw data for analysis
    latencies: List[float] = field(default_factory=list)
    memory_samples: List[float] = field(default_factory=list)
    cpu_samples: List[float] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert metrics to dictionary, excluding raw data"""
        data = asdict(self)
        # Remove raw data lists from dict representation
        data.pop("latencies", None)
        data.pop("memory_samples", None)
        data.pop("cpu_samples", None)
        return data

    def calculate_percentiles(self):
        """Calculate latency percentiles from raw data"""
        if not self.latencies:
            return

        sorted_latencies = sorted(self.latencies)
        n = len(sorted_latencies)

        # Convert to milliseconds
        self.latency_min = min(self.latencies) * 1000
        self.latency_max = max(self.latencies) * 1000
        self.latency_avg = statistics.mean(self.latencies) * 1000

        # Calculate percentiles
        self.latency_p50 = sorted_latencies[int(n * 0.50)] * 1000
        self.latency_p95 = sorted_latencies[int(n * 0.95)] * 1000
        self.latency_p99 = sorted_latencies[int(n * 0.99)] * 1000

    def calculate_resource_metrics(self):
        """Calculate resource usage metrics"""
        if self.memory_samples:
            self.memory_peak = max(self.memory_samples)
            self.memory_avg = statistics.mean(self.memory_samples)

        if self.cpu_samples:
            self.cpu_peak = max(self.cpu_samples)
            self.cpu_avg = statistics.mean(self.cpu_samples)

    def calculate_error_rate(self):
        """Calculate error rate percentage"""
        total = self.completed_tasks + self.failed_tasks
        if total > 0:
            self.error_rate = (self.failed_tasks / total) * 100

    def finalize(self):
        """Finalize all metric calculations"""
        self.calculate_percentiles()
        self.calculate_resource_metrics()
        self.calculate_error_rate()

        # Calculate throughput
        if self.duration_seconds > 0:
            self.throughput = self.completed_tasks / self.duration_seconds


class BenchmarkRunner:
    """
    Main benchmark runner for performance testing.

    Orchestrates benchmark execution, metrics collection, and report generation.
    """

    def __init__(self, output_dir: str = "./benchmark_results"):
        """
        Initialize benchmark runner.

        Args:
            output_dir: Directory for benchmark results
        """
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        self.metrics: List[PerformanceMetrics] = []
        self.process = psutil.Process()
        self.monitoring_active = False
        self._monitor_thread: Optional[threading.Thread] = None

    def run_all_benchmarks(
        self, benchmark_tests: List[Tuple[str, callable]]
    ) -> List[PerformanceMetrics]:
        """
        Run all benchmark tests.

        Args:
            benchmark_tests: List of (test_name, test_function) tuples

        Returns:
            List of PerformanceMetrics for each test
        """
        logger.info(f"Starting benchmark suite with {len(benchmark_tests)} tests")
        results = []

        for test_name, test_func in benchmark_tests:
            try:
                logger.info(f"Running benchmark: {test_name}")
                metrics = self.collect_metrics(test_name, test_func)
                results.append(metrics)
                logger.info(
                    f"Completed: {test_name} - Throughput: {metrics.throughput:.2f} tasks/sec"
                )
            except Exception as e:
                logger.error(f"Benchmark {test_name} failed: {e}", exc_info=True)

        self.metrics.extend(results)
        return results

    def collect_metrics(self, test_name: str, test_func: callable) -> PerformanceMetrics:
        """
        Collect performance metrics for a single test.

        Args:
            test_name: Name of the test
            test_func: Callable that returns (task_count, completed_tasks, failed_tasks)

        Returns:
            PerformanceMetrics object with collected data
        """
        metrics = PerformanceMetrics(test_name=test_name)

        # Start monitoring
        self.monitoring_active = True
        self._monitor_thread = threading.Thread(
            target=self._monitor_resources, args=(metrics,), daemon=True
        )
        self._monitor_thread.start()

        # Run test
        start_time = time.perf_counter()
        try:
            task_count, completed, failed, latencies = test_func()
            metrics.task_count = task_count
            metrics.completed_tasks = completed
            metrics.failed_tasks = failed
            metrics.latencies = latencies
        finally:
            metrics.duration_seconds = max(time.perf_counter() - start_time, 1e-9)
            self.monitoring_active = False
            if self._monitor_thread:
                self._monitor_thread.join(timeout=2)

        # Finalize calculations
        metrics.finalize()

        return metrics

    def _monitor_resources(self, metrics: PerformanceMetrics):
        """Monitor system resources during test execution"""
        self.process.cpu_percent()  # Initialize CPU counter

        while self.monitoring_active:
            try:
                # Sample memory
                memory_mb = self.process.memory_info().rss / 1024 / 1024
                metrics.memory_samples.append(memory_mb)

                # Sample CPU
                cpu_percent = self.process.cpu_percent(interval=0.1)
                metrics.cpu_samples.append(cpu_percent)

                time.sleep(0.1)
            except Exception as e:
                logger.warning(f"Resource monitoring error: {e}")

    def generate_report(self) -> Dict[str, Any]:
        """
        Generate comprehensive benchmark report.

        Returns:
            Dictionary containing report data
        """
        if not self.metrics:
            logger.warning("No metrics available for report generation")
            return {}

        report = {
            "timestamp": datetime.now().isoformat(),
            "total_tests": len(self.metrics),
            "tests": [m.to_dict() for m in self.metrics],
            "summary": self._generate_summary(),
        }

        return report

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate summary statistics across all tests"""
        if not self.metrics:
            return {}

        throughputs = [m.throughput for m in self.metrics if m.throughput > 0]
        latencies_p95 = [m.latency_p95 for m in self.metrics if m.latency_p95 > 0]
        memory_peaks = [m.memory_peak for m in self.metrics if m.memory_peak > 0]
        cpu_peaks = [m.cpu_peak for m in self.metrics if m.cpu_peak > 0]
        error_rates = [m.error_rate for m in self.metrics]

        return {
            "avg_throughput": statistics.mean(throughputs) if throughputs else 0,
            "min_throughput": min(throughputs) if throughputs else 0,
            "max_throughput": max(throughputs) if throughputs else 0,
            "avg_latency_p95": statistics.mean(latencies_p95) if latencies_p95 else 0,
            "max_latency_p95": max(latencies_p95) if latencies_p95 else 0,
            "avg_memory_peak": statistics.mean(memory_peaks) if memory_peaks else 0,
            "max_memory_peak": max(memory_peaks) if memory_peaks else 0,
            "avg_cpu_peak": statistics.mean(cpu_peaks) if cpu_peaks else 0,
            "max_cpu_peak": max(cpu_peaks) if cpu_peaks else 0,
            "avg_error_rate": statistics.mean(error_rates) if error_rates else 0,
        }

    def export_to_csv(self, filename: Optional[str] = None) -> Path:
        """
        Export metrics to CSV format.

        Args:
            filename: Output filename (default: benchmark_results.csv)

        Returns:
            Path to exported CSV file
        """
        if not self.metrics:
            logger.warning("No metrics to export")
            return None

        if filename is None:
            filename = f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"

        filepath = self.output_dir / filename

        try:
            with open(filepath, "w", newline="") as csvfile:
                fieldnames = [
                    "test_name",
                    "timestamp",
                    "duration_seconds",
                    "task_count",
                    "completed_tasks",
                    "failed_tasks",
                    "throughput",
                    "latency_p50",
                    "latency_p95",
                    "latency_p99",
                    "latency_avg",
                    "latency_min",
                    "latency_max",
                    "memory_peak",
                    "memory_avg",
                    "cpu_peak",
                    "cpu_avg",
                    "error_rate",
                ]

                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                writer.writeheader()

                for metric in self.metrics:
                    writer.writerow(metric.to_dict())

            logger.info(f"Exported metrics to CSV: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to export CSV: {e}")
            raise

    def export_to_json(self, filename: Optional[str] = None) -> Path:
        """
        Export metrics to JSON format.

        Args:
            filename: Output filename (default: benchmark_results.json)

        Returns:
            Path to exported JSON file
        """
        if not self.metrics:
            logger.warning("No metrics to export")
            return None

        if filename is None:
            filename = f"benchmark_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        filepath = self.output_dir / filename

        try:
            report = self.generate_report()

            with open(filepath, "w") as jsonfile:
                json.dump(report, jsonfile, indent=2)

            logger.info(f"Exported metrics to JSON: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to export JSON: {e}")
            raise

    def export_to_html(self, filename: Optional[str] = None) -> Path:
        """
        Export metrics to HTML report with charts.

        Args:
            filename: Output filename (default: benchmark_report.html)

        Returns:
            Path to exported HTML file
        """
        if not self.metrics:
            logger.warning("No metrics to export")
            return None

        if filename is None:
            filename = f"benchmark_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.html"

        filepath = self.output_dir / filename

        try:
            html_content = self._generate_html_report()

            with open(filepath, "w") as htmlfile:
                htmlfile.write(html_content)

            logger.info(f"Exported HTML report: {filepath}")
            return filepath

        except Exception as e:
            logger.error(f"Failed to export HTML: {e}")
            raise

    def _generate_html_report(self) -> str:
        """Generate HTML report with embedded charts"""
        report = self.generate_report()
        summary = report.get("summary", {})
        tests = report.get("tests", [])

        html = f"""<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <title>Performance Benchmark Report</title>
    <script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
    <style>
        body {{
            font-family: Arial, sans-serif;
            margin: 20px;
            background-color: #f5f5f5;
        }}
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background-color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }}
        h1 {{
            color: #333;
            border-bottom: 3px solid #007bff;
            padding-bottom: 10px;
        }}
        h2 {{
            color: #555;
            margin-top: 30px;
        }}
        .summary-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 20px 0;
        }}
        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}
        .metric-card h3 {{
            margin: 0 0 10px 0;
            font-size: 14px;
            opacity: 0.9;
        }}
        .metric-card .value {{
            font-size: 28px;
            font-weight: bold;
        }}
        .metric-card .unit {{
            font-size: 12px;
            opacity: 0.8;
        }}
        .chart-container {{
            position: relative;
            height: 400px;
            margin: 30px 0;
            background: white;
            padding: 20px;
            border-radius: 8px;
            border: 1px solid #ddd;
        }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
        }}
        th, td {{
            padding: 12px;
            text-align: left;
            border-bottom: 1px solid #ddd;
        }}
        th {{
            background-color: #f8f9fa;
            font-weight: bold;
            color: #333;
        }}
        tr:hover {{
            background-color: #f5f5f5;
        }}
        .timestamp {{
            color: #666;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>Performance Benchmark Report</h1>
        <p class="timestamp">Generated: {report.get('timestamp', 'N/A')}</p>

        <h2>Summary Metrics</h2>
        <div class="summary-grid">
            <div class="metric-card">
                <h3>Avg Throughput</h3>
                <div class="value">{summary.get('avg_throughput', 0):.2f}</div>
                <div class="unit">tasks/sec</div>
            </div>
            <div class="metric-card">
                <h3>Avg Latency P95</h3>
                <div class="value">{summary.get('avg_latency_p95', 0):.2f}</div>
                <div class="unit">ms</div>
            </div>
            <div class="metric-card">
                <h3>Max Memory Peak</h3>
                <div class="value">{summary.get('max_memory_peak', 0):.2f}</div>
                <div class="unit">MB</div>
            </div>
            <div class="metric-card">
                <h3>Max CPU Peak</h3>
                <div class="value">{summary.get('max_cpu_peak', 0):.2f}</div>
                <div class="unit">%</div>
            </div>
        </div>

        <h2>Test Results</h2>
        <table>
            <thead>
                <tr>
                    <th>Test Name</th>
                    <th>Throughput (tasks/sec)</th>
                    <th>Latency P95 (ms)</th>
                    <th>Memory Peak (MB)</th>
                    <th>CPU Peak (%)</th>
                    <th>Error Rate (%)</th>
                </tr>
            </thead>
            <tbody>
"""

        for test in tests:
            html += f"""                <tr>
                    <td>{test.get('test_name', 'N/A')}</td>
                    <td>{test.get('throughput', 0):.2f}</td>
                    <td>{test.get('latency_p95', 0):.2f}</td>
                    <td>{test.get('memory_peak', 0):.2f}</td>
                    <td>{test.get('cpu_peak', 0):.2f}</td>
                    <td>{test.get('error_rate', 0):.2f}</td>
                </tr>
"""

        html += """            </tbody>
        </table>

        <h2>Charts</h2>
        <div class="chart-container">
            <canvas id="throughputChart"></canvas>
        </div>
        <div class="chart-container">
            <canvas id="latencyChart"></canvas>
        </div>
        <div class="chart-container">
            <canvas id="resourceChart"></canvas>
        </div>

        <script>
            const testNames = ["""

        test_names = [f"'{t.get('test_name', 'N/A')}'" for t in tests]
        html += ", ".join(test_names) + "];\n"

        throughputs = [t.get("throughput", 0) for t in tests]
        html += f"            const throughputs = {throughputs};\n"

        latencies = [t.get("latency_p95", 0) for t in tests]
        html += f"            const latencies = {latencies};\n"

        memory_peaks = [t.get("memory_peak", 0) for t in tests]
        html += f"            const memoryPeaks = {memory_peaks};\n"

        cpu_peaks = [t.get("cpu_peak", 0) for t in tests]
        html += f"            const cpuPeaks = {cpu_peaks};\n"

        html += """
            // Throughput Chart
            new Chart(document.getElementById('throughputChart'), {
                type: 'bar',
                data: {
                    labels: testNames,
                    datasets: [{
                        label: 'Throughput (tasks/sec)',
                        data: throughputs,
                        backgroundColor: 'rgba(102, 126, 234, 0.8)',
                        borderColor: 'rgba(102, 126, 234, 1)',
                        borderWidth: 1
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: 'Throughput by Test'
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });

            // Latency Chart
            new Chart(document.getElementById('latencyChart'), {
                type: 'line',
                data: {
                    labels: testNames,
                    datasets: [{
                        label: 'Latency P95 (ms)',
                        data: latencies,
                        borderColor: 'rgba(118, 75, 162, 1)',
                        backgroundColor: 'rgba(118, 75, 162, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        tension: 0.4
                    }]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: 'Latency P95 by Test'
                        }
                    },
                    scales: {
                        y: {
                            beginAtZero: true
                        }
                    }
                }
            });

            // Resource Chart
            new Chart(document.getElementById('resourceChart'), {
                type: 'radar',
                data: {
                    labels: testNames,
                    datasets: [
                        {
                            label: 'Memory Peak (MB)',
                            data: memoryPeaks,
                            borderColor: 'rgba(255, 99, 132, 1)',
                            backgroundColor: 'rgba(255, 99, 132, 0.2)'
                        },
                        {
                            label: 'CPU Peak (%)',
                            data: cpuPeaks,
                            borderColor: 'rgba(54, 162, 235, 1)',
                            backgroundColor: 'rgba(54, 162, 235, 0.2)'
                        }
                    ]
                },
                options: {
                    responsive: true,
                    maintainAspectRatio: false,
                    plugins: {
                        title: {
                            display: true,
                            text: 'Resource Usage by Test'
                        }
                    }
                }
            });
        </script>
    </div>
</body>
</html>
"""

        return html
