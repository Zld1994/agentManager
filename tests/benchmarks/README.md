"""
Performance Benchmarks for agentManager

This module provides comprehensive performance testing and benchmarking capabilities
for the agentManager system.

## Components

### benchmark_runner.py
Core benchmarking infrastructure:
- `PerformanceMetrics`: Data class for collecting performance metrics
- `BenchmarkRunner`: Main orchestrator for running benchmarks and generating reports

### run_benchmarks.py
Executable script for running the full benchmark suite:
- Executes 6 different benchmark scenarios
- Collects comprehensive metrics
- Exports results in CSV, JSON, and HTML formats

### test_benchmark_runner.py
Unit and integration tests covering:
- Metrics collection and calculation
- Export functionality
- Report generation
- Full workflow integration

## Usage

### Running Benchmarks

```bash
# Run all benchmarks with all export formats
python tests/benchmarks/run_benchmarks.py

# Run with specific output directory
python tests/benchmarks/run_benchmarks.py --output-dir ./my_results

# Run with specific export format
python tests/benchmarks/run_benchmarks.py --format json

# Enable verbose logging
python tests/benchmarks/run_benchmarks.py --verbose
```

### Running Tests

```bash
# Run all benchmark tests
pytest tests/benchmarks/test_benchmark_runner.py -v

# Run specific test class
pytest tests/benchmarks/test_benchmark_runner.py::TestPerformanceMetrics -v

# Run with coverage
pytest tests/benchmarks/test_benchmark_runner.py --cov=tests.benchmarks
```

## Benchmark Scenarios

1. **simple_throughput**: 100 tasks with 10ms each
2. **high_throughput**: 500 tasks with 5ms each
3. **latency_sensitive**: 50 tasks with 20ms each
4. **memory_intensive**: 30 tasks with ~8MB memory allocation
5. **cpu_intensive**: 20 tasks with CPU-heavy computation
6. **mixed_workload**: 40 tasks combining CPU, memory, and I/O

## Metrics Collected

### Throughput
- tasks/sec: Number of tasks completed per second

### Latency
- p50, p95, p99: Percentile latencies in milliseconds
- avg, min, max: Average, minimum, maximum latencies

### Resource Usage
- memory_peak: Peak memory usage in MB
- memory_avg: Average memory usage in MB
- cpu_peak: Peak CPU usage percentage
- cpu_avg: Average CPU usage percentage

### Error Metrics
- error_rate: Percentage of failed tasks

## Export Formats

### CSV
Tabular format suitable for spreadsheet analysis:
- One row per benchmark test
- All metrics as columns
- Easy to import into Excel/Sheets

### JSON
Structured format with full report:
- Complete metrics for each test
- Summary statistics
- Timestamp and metadata

### HTML
Interactive report with visualizations:
- Summary metric cards
- Results table
- Three interactive charts:
  - Throughput by test (bar chart)
  - Latency P95 by test (line chart)
  - Resource usage by test (radar chart)

## Output Directory Structure

```
benchmark_results/
├── benchmark_results_YYYYMMDD_HHMMSS.csv
├── benchmark_results_YYYYMMDD_HHMMSS.json
└── benchmark_report_YYYYMMDD_HHMMSS.html
```

## Integration with CI/CD

The benchmark suite can be integrated into CI/CD pipelines:

```yaml
# Example GitHub Actions workflow
- name: Run Performance Benchmarks
  run: |
    python tests/benchmarks/run_benchmarks.py --output-dir ./benchmark_results
    
- name: Upload Results
  uses: actions/upload-artifact@v2
  with:
    name: benchmark-results
    path: benchmark_results/
```

## Performance Targets

Recommended performance targets for the agentManager system:

- **Throughput**: > 10 tasks/sec
- **Latency P95**: < 100ms
- **Latency P99**: < 200ms
- **Memory Peak**: < 500MB
- **CPU Peak**: < 80%
- **Error Rate**: < 1%

## Extending Benchmarks

To add new benchmark scenarios:

1. Add a new method to `BenchmarkSuite` in `run_benchmarks.py`:

```python
def benchmark_custom_scenario(self) -> Tuple[int, int, int, List[float]]:
    \"\"\"Custom benchmark scenario\"\"\"
    task_count = 100
    completed = 0
    failed = 0
    latencies = []
    
    for i in range(task_count):
        try:
            start = time.time()
            # Your test logic here
            latency = time.time() - start
            latencies.append(latency)
            completed += 1
        except Exception as e:
            failed += 1
    
    return task_count, completed, failed, latencies
```

2. Register it in `get_all_benchmarks()`:

```python
def get_all_benchmarks(self) -> List[Tuple[str, callable]]:
    return [
        # ... existing benchmarks ...
        ("custom_scenario", self.benchmark_custom_scenario),
    ]
```

3. Add corresponding tests in `test_benchmark_runner.py`

## Troubleshooting

### High Memory Usage
- Reduce task count in benchmark scenarios
- Check for memory leaks in tested code
- Monitor with `--verbose` flag

### Inconsistent Results
- Run benchmarks multiple times for statistical significance
- Close other applications to reduce system noise
- Use dedicated test environment

### Export Failures
- Ensure output directory is writable
- Check disk space availability
- Verify file permissions

## Dependencies

- psutil: System resource monitoring
- pytest: Testing framework
- chart.js: HTML report visualization (CDN-based)

## License

Part of agentManager project
"""
