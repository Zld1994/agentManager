#!/usr/bin/env python3
"""
Main benchmark runner script.

Executes all performance benchmarks, collects metrics, and generates reports
in multiple formats (CSV, JSON, HTML).

Usage:
    python run_benchmarks.py [--output-dir ./results] [--format all|csv|json|html]
"""

import sys
import time
import logging
import argparse
from pathlib import Path
from typing import List, Tuple, Any
from datetime import datetime

from benchmark_runner import BenchmarkRunner, PerformanceMetrics


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class BenchmarkSuite:
    """Orchestrates benchmark test execution"""
    
    def __init__(self, output_dir: str = "./benchmark_results"):
        """Initialize benchmark suite"""
        self.runner = BenchmarkRunner(output_dir=output_dir)
        self.output_dir = Path(output_dir)
    
    def benchmark_simple_throughput(self) -> Tuple[int, int, int, List[float]]:
        """
        Benchmark simple task throughput.
        
        Returns:
            (task_count, completed, failed, latencies)
        """
        logger.info("Running simple throughput benchmark...")
        task_count = 100
        completed = 0
        failed = 0
        latencies = []
        
        for i in range(task_count):
            try:
                start = time.time()
                # Simulate task execution
                time.sleep(0.01)
                latency = time.time() - start
                latencies.append(latency)
                completed += 1
            except Exception as e:
                logger.error(f"Task {i} failed: {e}")
                failed += 1
        
        return task_count, completed, failed, latencies
    
    def benchmark_high_throughput(self) -> Tuple[int, int, int, List[float]]:
        """
        Benchmark high throughput with many tasks.
        
        Returns:
            (task_count, completed, failed, latencies)
        """
        logger.info("Running high throughput benchmark...")
        task_count = 500
        completed = 0
        failed = 0
        latencies = []
        
        for i in range(task_count):
            try:
                start = time.time()
                # Simulate fast task execution
                time.sleep(0.005)
                latency = time.time() - start
                latencies.append(latency)
                completed += 1
            except Exception as e:
                logger.error(f"Task {i} failed: {e}")
                failed += 1
        
        return task_count, completed, failed, latencies
    
    def benchmark_latency_sensitive(self) -> Tuple[int, int, int, List[float]]:
        """
        Benchmark latency-sensitive operations.
        
        Returns:
            (task_count, completed, failed, latencies)
        """
        logger.info("Running latency-sensitive benchmark...")
        task_count = 50
        completed = 0
        failed = 0
        latencies = []
        
        for i in range(task_count):
            try:
                start = time.time()
                # Simulate latency-sensitive task
                time.sleep(0.02)
                latency = time.time() - start
                latencies.append(latency)
                completed += 1
            except Exception as e:
                logger.error(f"Task {i} failed: {e}")
                failed += 1
        
        return task_count, completed, failed, latencies
    
    def benchmark_memory_intensive(self) -> Tuple[int, int, int, List[float]]:
        """
        Benchmark memory-intensive operations.
        
        Returns:
            (task_count, completed, failed, latencies)
        """
        logger.info("Running memory-intensive benchmark...")
        task_count = 30
        completed = 0
        failed = 0
        latencies = []
        
        for i in range(task_count):
            try:
                start = time.time()
                # Simulate memory-intensive task
                data = [0] * (1024 * 1024)  # ~8MB per task
                time.sleep(0.01)
                latency = time.time() - start
                latencies.append(latency)
                completed += 1
                del data
            except Exception as e:
                logger.error(f"Task {i} failed: {e}")
                failed += 1
        
        return task_count, completed, failed, latencies
    
    def benchmark_cpu_intensive(self) -> Tuple[int, int, int, List[float]]:
        """
        Benchmark CPU-intensive operations.
        
        Returns:
            (task_count, completed, failed, latencies)
        """
        logger.info("Running CPU-intensive benchmark...")
        task_count = 20
        completed = 0
        failed = 0
        latencies = []
        
        for i in range(task_count):
            try:
                start = time.time()
                # Simulate CPU-intensive task
                result = sum(j * j for j in range(100000))
                latency = time.time() - start
                latencies.append(latency)
                completed += 1
            except Exception as e:
                logger.error(f"Task {i} failed: {e}")
                failed += 1
        
        return task_count, completed, failed, latencies
    
    def benchmark_mixed_workload(self) -> Tuple[int, int, int, List[float]]:
        """
        Benchmark mixed workload (CPU + memory + I/O).
        
        Returns:
            (task_count, completed, failed, latencies)
        """
        logger.info("Running mixed workload benchmark...")
        task_count = 40
        completed = 0
        failed = 0
        latencies = []
        
        for i in range(task_count):
            try:
                start = time.time()
                # Simulate mixed workload
                data = [j * j for j in range(10000)]
                time.sleep(0.015)
                latency = time.time() - start
                latencies.append(latency)
                completed += 1
                del data
            except Exception as e:
                logger.error(f"Task {i} failed: {e}")
                failed += 1
        
        return task_count, completed, failed, latencies
    
    def get_all_benchmarks(self) -> List[Tuple[str, callable]]:
        """Get all benchmark tests"""
        return [
            ("simple_throughput", self.benchmark_simple_throughput),
            ("high_throughput", self.benchmark_high_throughput),
            ("latency_sensitive", self.benchmark_latency_sensitive),
            ("memory_intensive", self.benchmark_memory_intensive),
            ("cpu_intensive", self.benchmark_cpu_intensive),
            ("mixed_workload", self.benchmark_mixed_workload),
        ]
    
    def run_all(self) -> List[PerformanceMetrics]:
        """Run all benchmarks"""
        benchmarks = self.get_all_benchmarks()
        return self.runner.run_all_benchmarks(benchmarks)
    
    def export_results(self, formats: List[str] = None) -> dict:
        """
        Export results in specified formats.
        
        Args:
            formats: List of formats ('csv', 'json', 'html', 'all')
        
        Returns:
            Dictionary with export paths
        """
        if formats is None:
            formats = ['all']
        
        if 'all' in formats:
            formats = ['csv', 'json', 'html']
        
        results = {}
        
        if 'csv' in formats:
            try:
                path = self.runner.export_to_csv()
                results['csv'] = str(path)
                logger.info(f"CSV export: {path}")
            except Exception as e:
                logger.error(f"CSV export failed: {e}")
        
        if 'json' in formats:
            try:
                path = self.runner.export_to_json()
                results['json'] = str(path)
                logger.info(f"JSON export: {path}")
            except Exception as e:
                logger.error(f"JSON export failed: {e}")
        
        if 'html' in formats:
            try:
                path = self.runner.export_to_html()
                results['html'] = str(path)
                logger.info(f"HTML export: {path}")
            except Exception as e:
                logger.error(f"HTML export failed: {e}")
        
        return results
    
    def print_summary(self):
        """Print benchmark summary to console"""
        if not self.runner.metrics:
            logger.warning("No metrics to display")
            return
        
        print("\n" + "="*80)
        print("BENCHMARK RESULTS SUMMARY")
        print("="*80)
        
        for metric in self.runner.metrics:
            print(f"\nTest: {metric.test_name}")
            print(f"  Duration: {metric.duration_seconds:.2f}s")
            print(f"  Tasks: {metric.completed_tasks}/{metric.task_count} completed")
            print(f"  Throughput: {metric.throughput:.2f} tasks/sec")
            print(f"  Latency P95: {metric.latency_p95:.2f}ms")
            print(f"  Latency P99: {metric.latency_p99:.2f}ms")
            print(f"  Memory Peak: {metric.memory_peak:.2f}MB")
            print(f"  CPU Peak: {metric.cpu_peak:.2f}%")
            print(f"  Error Rate: {metric.error_rate:.2f}%")
        
        summary = self.runner._generate_summary()
        print("\n" + "-"*80)
        print("OVERALL SUMMARY")
        print("-"*80)
        print(f"Avg Throughput: {summary.get('avg_throughput', 0):.2f} tasks/sec")
        print(f"Avg Latency P95: {summary.get('avg_latency_p95', 0):.2f}ms")
        print(f"Max Memory Peak: {summary.get('max_memory_peak', 0):.2f}MB")
        print(f"Max CPU Peak: {summary.get('max_cpu_peak', 0):.2f}%")
        print(f"Avg Error Rate: {summary.get('avg_error_rate', 0):.2f}%")
        print("="*80 + "\n")


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run performance benchmarks for agentManager"
    )
    parser.add_argument(
        "--output-dir",
        default="./benchmark_results",
        help="Output directory for benchmark results"
    )
    parser.add_argument(
        "--format",
        default="all",
        choices=["all", "csv", "json", "html"],
        help="Export format(s)"
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Enable verbose logging"
    )
    
    args = parser.parse_args()
    
    if args.verbose:
        logging.getLogger().setLevel(logging.DEBUG)
    
    logger.info("Starting benchmark suite...")
    logger.info(f"Output directory: {args.output_dir}")
    
    try:
        suite = BenchmarkSuite(output_dir=args.output_dir)
        
        # Run all benchmarks
        logger.info("Executing benchmarks...")
        suite.run_all()
        
        # Print summary
        suite.print_summary()
        
        # Export results
        logger.info(f"Exporting results in {args.format} format...")
        exports = suite.export_results([args.format])
        
        logger.info("Benchmark suite completed successfully")
        logger.info(f"Results exported to: {args.output_dir}")
        
        return 0
    
    except Exception as e:
        logger.error(f"Benchmark suite failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
