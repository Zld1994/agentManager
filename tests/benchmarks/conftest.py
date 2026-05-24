"""
Pytest configuration for benchmark tests.
"""

import pytest
import logging
from pathlib import Path
from tests.benchmarks.benchmark_runner import BenchmarkRunner


@pytest.fixture
def benchmark_runner():
    """Create a benchmark runner instance"""
    output_dir = Path("./test_benchmark_results")
    runner = BenchmarkRunner(output_dir=str(output_dir))
    yield runner
    # Cleanup is optional - results are useful for inspection


@pytest.fixture
def sample_metrics():
    """Create sample performance metrics for testing"""
    from tests.benchmarks.benchmark_runner import PerformanceMetrics
    
    metrics = PerformanceMetrics(test_name="sample_test")
    metrics.task_count = 100
    metrics.completed_tasks = 95
    metrics.failed_tasks = 5
    metrics.duration_seconds = 10.0
    
    # Add sample latencies (in seconds)
    metrics.latencies = [0.01 + (i * 0.0001) for i in range(95)]
    
    # Add sample memory samples (in MB)
    metrics.memory_samples = [100 + (i * 0.5) for i in range(100)]
    
    # Add sample CPU samples (in %)
    metrics.cpu_samples = [25 + (i * 0.1) for i in range(100)]
    
    metrics.finalize()
    return metrics


@pytest.fixture
def caplog_handler(caplog):
    """Configure caplog for benchmark tests"""
    caplog.set_level(logging.INFO)
    return caplog
