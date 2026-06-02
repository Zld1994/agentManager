"""
Performance Analysis and Insights Generation

Analyzes benchmark results, compares with baselines, identifies bottlenecks,
and generates actionable insights for performance optimization.
"""

import json
from typing import Any, Dict, List, Optional
from datetime import datetime
from pathlib import Path
from dataclasses import dataclass, asdict
import logging

logger = logging.getLogger(__name__)


@dataclass
class PerformanceBaseline:
    """Baseline performance metrics for comparison"""

    test_name: str
    throughput: float
    latency_p95: float
    memory_peak: float
    cpu_peak: float
    error_rate: float
    timestamp: str


@dataclass
class PerformanceInsight:
    """Performance insight with severity and recommendation"""

    category: str  # 'throughput', 'latency', 'memory', 'cpu', 'error'
    severity: str  # 'critical', 'warning', 'info'
    message: str
    metric_name: str
    current_value: float
    baseline_value: Optional[float]
    deviation_percent: Optional[float]
    recommendation: str


class PerformanceAnalyzer:
    """
    Analyzes benchmark results and generates performance insights.

    Capabilities:
    - Compare current metrics with baselines
    - Identify performance bottlenecks
    - Detect anomalies and regressions
    - Generate actionable recommendations
    """

    def __init__(self, baseline_file: Optional[str] = None):
        """
        Initialize performance analyzer.

        Args:
            baseline_file: Optional path to baseline metrics JSON file
        """
        self.baselines: Dict[str, PerformanceBaseline] = {}
        self.insights: List[PerformanceInsight] = []

        if baseline_file and Path(baseline_file).exists():
            self._load_baselines(baseline_file)

    def _load_baselines(self, baseline_file: str):
        """Load baseline metrics from JSON file"""
        try:
            with open(baseline_file, "r") as f:
                data = json.load(f)
                for test_name, metrics in data.items():
                    self.baselines[test_name] = PerformanceBaseline(
                        test_name=test_name,
                        throughput=metrics.get("throughput", 0),
                        latency_p95=metrics.get("latency_p95", 0),
                        memory_peak=metrics.get("memory_peak", 0),
                        cpu_peak=metrics.get("cpu_peak", 0),
                        error_rate=metrics.get("error_rate", 0),
                        timestamp=metrics.get("timestamp", ""),
                    )
            logger.info(f"Loaded {len(self.baselines)} baseline metrics")
        except Exception as e:
            logger.warning(f"Failed to load baselines: {e}")

    def save_baselines(self, output_file: str):
        """Save current metrics as new baselines"""
        try:
            data = {}
            for test_name, baseline in self.baselines.items():
                data[test_name] = asdict(baseline)

            with open(output_file, "w") as f:
                json.dump(data, f, indent=2)

            logger.info(f"Saved baselines to {output_file}")
        except Exception as e:
            logger.error(f"Failed to save baselines: {e}")

    def analyze_metrics(self, metrics: List[Dict[str, Any]]) -> List[PerformanceInsight]:
        """
        Analyze metrics and generate insights.

        Args:
            metrics: List of metric dictionaries from benchmark results

        Returns:
            List of PerformanceInsight objects
        """
        self.insights = []

        for metric in metrics:
            test_name = metric.get("test_name", "Unknown")

            # Analyze throughput
            self._analyze_throughput(metric, test_name)

            # Analyze latency
            self._analyze_latency(metric, test_name)

            # Analyze memory
            self._analyze_memory(metric, test_name)

            # Analyze CPU
            self._analyze_cpu(metric, test_name)

            # Analyze errors
            self._analyze_errors(metric, test_name)

        return self.insights

    def _analyze_throughput(self, metric: Dict[str, Any], test_name: str):
        """Analyze throughput metrics"""
        current = metric.get("throughput", 0)
        baseline = self.baselines.get(test_name)

        if current == 0:
            self.insights.append(
                PerformanceInsight(
                    category="throughput",
                    severity="critical",
                    message=f"Zero throughput detected for {test_name}",
                    metric_name="throughput",
                    current_value=current,
                    baseline_value=None,
                    deviation_percent=None,
                    recommendation=(
                        "Investigate test execution and ensure tasks are being processed"
                    ),
                )
            )
            return

        if baseline:
            deviation = ((current - baseline.throughput) / baseline.throughput) * 100

            if deviation < -20:
                self.insights.append(
                    PerformanceInsight(
                        category="throughput",
                        severity="critical",
                        message=f"Significant throughput regression in {test_name}",
                        metric_name="throughput",
                        current_value=current,
                        baseline_value=baseline.throughput,
                        deviation_percent=deviation,
                        recommendation="Review recent code changes and optimize critical paths",
                    )
                )
            elif deviation < -10:
                self.insights.append(
                    PerformanceInsight(
                        category="throughput",
                        severity="warning",
                        message=f"Throughput degradation in {test_name}",
                        metric_name="throughput",
                        current_value=current,
                        baseline_value=baseline.throughput,
                        deviation_percent=deviation,
                        recommendation=(
                            "Monitor performance trends and investigate potential bottlenecks"
                        ),
                    )
                )
            elif deviation > 20:
                self.insights.append(
                    PerformanceInsight(
                        category="throughput",
                        severity="info",
                        message=f"Throughput improvement in {test_name}",
                        metric_name="throughput",
                        current_value=current,
                        baseline_value=baseline.throughput,
                        deviation_percent=deviation,
                        recommendation="Document optimization and consider applying to other tests",
                    )
                )

    def _analyze_latency(self, metric: Dict[str, Any], test_name: str):
        """Analyze latency metrics"""
        current_p95 = metric.get("latency_p95", 0)
        current_p99 = metric.get("latency_p99", 0)
        baseline = self.baselines.get(test_name)

        if current_p95 > 1000:
            self.insights.append(
                PerformanceInsight(
                    category="latency",
                    severity="warning",
                    message=f"High P95 latency in {test_name}",
                    metric_name="latency_p95",
                    current_value=current_p95,
                    baseline_value=baseline.latency_p95 if baseline else None,
                    deviation_percent=None,
                    recommendation=(
                        "Profile code to identify slow operations and optimize critical paths"
                    ),
                )
            )

        if current_p99 > 2000:
            self.insights.append(
                PerformanceInsight(
                    category="latency",
                    severity="critical",
                    message=f"Critical P99 latency in {test_name}",
                    metric_name="latency_p99",
                    current_value=current_p99,
                    baseline_value=baseline.latency_p99 if baseline else None,
                    deviation_percent=None,
                    recommendation=(
                        "Investigate tail latency causes and implement caching or optimization"
                    ),
                )
            )

        if baseline:
            deviation_p95 = ((current_p95 - baseline.latency_p95) / baseline.latency_p95) * 100

            if deviation_p95 > 30:
                self.insights.append(
                    PerformanceInsight(
                        category="latency",
                        severity="warning",
                        message=f"Latency regression in {test_name}",
                        metric_name="latency_p95",
                        current_value=current_p95,
                        baseline_value=baseline.latency_p95,
                        deviation_percent=deviation_p95,
                        recommendation="Review recent changes and optimize slow operations",
                    )
                )

    def _analyze_memory(self, metric: Dict[str, Any], test_name: str):
        """Analyze memory metrics"""
        current_peak = metric.get("memory_peak", 0)
        baseline = self.baselines.get(test_name)

        if current_peak > 1000:
            self.insights.append(
                PerformanceInsight(
                    category="memory",
                    severity="warning",
                    message=f"High memory usage in {test_name}",
                    metric_name="memory_peak",
                    current_value=current_peak,
                    baseline_value=baseline.memory_peak if baseline else None,
                    deviation_percent=None,
                    recommendation=(
                        "Review memory allocation patterns and consider streaming or pagination"
                    ),
                )
            )

        if baseline:
            deviation = ((current_peak - baseline.memory_peak) / baseline.memory_peak) * 100

            if deviation > 50:
                self.insights.append(
                    PerformanceInsight(
                        category="memory",
                        severity="critical",
                        message=f"Memory usage spike in {test_name}",
                        metric_name="memory_peak",
                        current_value=current_peak,
                        baseline_value=baseline.memory_peak,
                        deviation_percent=deviation,
                        recommendation="Investigate memory leaks and optimize data structures",
                    )
                )

    def _analyze_cpu(self, metric: Dict[str, Any], test_name: str):
        """Analyze CPU metrics"""
        current_peak = metric.get("cpu_peak", 0)
        baseline = self.baselines.get(test_name)

        if current_peak > 90:
            self.insights.append(
                PerformanceInsight(
                    category="cpu",
                    severity="warning",
                    message=f"High CPU usage in {test_name}",
                    metric_name="cpu_peak",
                    current_value=current_peak,
                    baseline_value=baseline.cpu_peak if baseline else None,
                    deviation_percent=None,
                    recommendation="Consider parallelization or algorithm optimization",
                )
            )

        if baseline:
            deviation = ((current_peak - baseline.cpu_peak) / baseline.cpu_peak) * 100

            if deviation > 40:
                self.insights.append(
                    PerformanceInsight(
                        category="cpu",
                        severity="warning",
                        message=f"CPU usage increase in {test_name}",
                        metric_name="cpu_peak",
                        current_value=current_peak,
                        baseline_value=baseline.cpu_peak,
                        deviation_percent=deviation,
                        recommendation="Profile CPU usage and optimize hot paths",
                    )
                )

    def _analyze_errors(self, metric: Dict[str, Any], test_name: str):
        """Analyze error metrics"""
        error_rate = metric.get("error_rate", 0)
        baseline = self.baselines.get(test_name)

        if error_rate > 5:
            self.insights.append(
                PerformanceInsight(
                    category="error",
                    severity="critical",
                    message=f"High error rate in {test_name}",
                    metric_name="error_rate",
                    current_value=error_rate,
                    baseline_value=baseline.error_rate if baseline else None,
                    deviation_percent=None,
                    recommendation="Investigate failure causes and improve error handling",
                )
            )
        elif error_rate > 1:
            self.insights.append(
                PerformanceInsight(
                    category="error",
                    severity="warning",
                    message=f"Elevated error rate in {test_name}",
                    metric_name="error_rate",
                    current_value=error_rate,
                    baseline_value=baseline.error_rate if baseline else None,
                    deviation_percent=None,
                    recommendation="Monitor error patterns and implement preventive measures",
                )
            )

    def identify_bottlenecks(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Identify performance bottlenecks across all tests.

        Args:
            metrics: List of metric dictionaries

        Returns:
            Dictionary with bottleneck analysis
        """
        bottlenecks = {
            "throughput_bottlenecks": [],
            "latency_bottlenecks": [],
            "memory_bottlenecks": [],
            "cpu_bottlenecks": [],
            "error_bottlenecks": [],
        }

        # Find worst performers
        if metrics:
            # Throughput bottlenecks (lowest throughput)
            sorted_by_throughput = sorted(metrics, key=lambda m: m.get("throughput", 0))
            bottlenecks["throughput_bottlenecks"] = [
                {"test": m.get("test_name"), "throughput": m.get("throughput", 0), "rank": i + 1}
                for i, m in enumerate(sorted_by_throughput[:3])
            ]

            # Latency bottlenecks (highest P95)
            sorted_by_latency = sorted(metrics, key=lambda m: m.get("latency_p95", 0), reverse=True)
            bottlenecks["latency_bottlenecks"] = [
                {"test": m.get("test_name"), "latency_p95": m.get("latency_p95", 0), "rank": i + 1}
                for i, m in enumerate(sorted_by_latency[:3])
            ]

            # Memory bottlenecks (highest peak)
            sorted_by_memory = sorted(metrics, key=lambda m: m.get("memory_peak", 0), reverse=True)
            bottlenecks["memory_bottlenecks"] = [
                {"test": m.get("test_name"), "memory_peak": m.get("memory_peak", 0), "rank": i + 1}
                for i, m in enumerate(sorted_by_memory[:3])
            ]

            # CPU bottlenecks (highest peak)
            sorted_by_cpu = sorted(metrics, key=lambda m: m.get("cpu_peak", 0), reverse=True)
            bottlenecks["cpu_bottlenecks"] = [
                {"test": m.get("test_name"), "cpu_peak": m.get("cpu_peak", 0), "rank": i + 1}
                for i, m in enumerate(sorted_by_cpu[:3])
            ]

            # Error bottlenecks (highest error rate)
            sorted_by_errors = sorted(metrics, key=lambda m: m.get("error_rate", 0), reverse=True)
            bottlenecks["error_bottlenecks"] = [
                {"test": m.get("test_name"), "error_rate": m.get("error_rate", 0), "rank": i + 1}
                for i, m in enumerate(sorted_by_errors[:3])
                if m.get("error_rate", 0) > 0
            ]

        return bottlenecks

    def compare_with_baseline(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Compare current metrics with baselines.

        Args:
            metrics: List of metric dictionaries

        Returns:
            Dictionary with comparison results
        """
        comparison = {
            "tests_compared": 0,
            "regressions": [],
            "improvements": [],
            "new_tests": [],
            "summary": {},
        }

        for metric in metrics:
            test_name = metric.get("test_name")
            baseline = self.baselines.get(test_name)

            if not baseline:
                comparison["new_tests"].append(test_name)
                continue

            comparison["tests_compared"] += 1

            # Compare throughput
            throughput_deviation = (
                (metric.get("throughput", 0) - baseline.throughput) / baseline.throughput * 100
                if baseline.throughput > 0
                else 0
            )

            # Compare latency
            latency_deviation = (
                (metric.get("latency_p95", 0) - baseline.latency_p95) / baseline.latency_p95 * 100
                if baseline.latency_p95 > 0
                else 0
            )

            # Compare memory
            memory_deviation = (
                (metric.get("memory_peak", 0) - baseline.memory_peak) / baseline.memory_peak * 100
                if baseline.memory_peak > 0
                else 0
            )

            # Determine if regression or improvement
            is_regression = (
                throughput_deviation < -10 or latency_deviation > 20 or memory_deviation > 30
            )

            is_improvement = (
                throughput_deviation > 20 or latency_deviation < -20 or memory_deviation < -20
            )

            result = {
                "test_name": test_name,
                "throughput_change": throughput_deviation,
                "latency_change": latency_deviation,
                "memory_change": memory_deviation,
            }

            if is_regression:
                comparison["regressions"].append(result)
            elif is_improvement:
                comparison["improvements"].append(result)

        # Generate summary
        comparison["summary"] = {
            "total_tests": len(metrics),
            "tests_compared": comparison["tests_compared"],
            "new_tests": len(comparison["new_tests"]),
            "regressions": len(comparison["regressions"]),
            "improvements": len(comparison["improvements"]),
        }

        return comparison

    def get_insights_by_severity(self, severity: str) -> List[PerformanceInsight]:
        """Get insights filtered by severity level"""
        return [i for i in self.insights if i.severity == severity]

    def get_insights_by_category(self, category: str) -> List[PerformanceInsight]:
        """Get insights filtered by category"""
        return [i for i in self.insights if i.category == category]

    def generate_analysis_report(self, metrics: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Generate comprehensive analysis report.

        Args:
            metrics: List of metric dictionaries

        Returns:
            Dictionary containing full analysis
        """
        insights = self.analyze_metrics(metrics)
        bottlenecks = self.identify_bottlenecks(metrics)
        comparison = self.compare_with_baseline(metrics)

        return {
            "timestamp": datetime.now().isoformat(),
            "metrics_analyzed": len(metrics),
            "insights": [
                {
                    "category": i.category,
                    "severity": i.severity,
                    "message": i.message,
                    "metric_name": i.metric_name,
                    "current_value": i.current_value,
                    "baseline_value": i.baseline_value,
                    "deviation_percent": i.deviation_percent,
                    "recommendation": i.recommendation,
                }
                for i in insights
            ],
            "insights_summary": {
                "critical": len(self.get_insights_by_severity("critical")),
                "warning": len(self.get_insights_by_severity("warning")),
                "info": len(self.get_insights_by_severity("info")),
            },
            "bottlenecks": bottlenecks,
            "baseline_comparison": comparison,
        }
