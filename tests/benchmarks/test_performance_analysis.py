"""
Tests for performance analysis module
"""

import pytest
import json
from pathlib import Path
from datetime import datetime
from tests.benchmarks.performance_analysis import (
    PerformanceAnalyzer,
    PerformanceBaseline,
    PerformanceInsight,
)


@pytest.fixture
def analyzer():
    """Create performance analyzer"""
    return PerformanceAnalyzer()


@pytest.fixture
def sample_metrics():
    """Sample benchmark metrics for testing"""
    return [
        {
            'test_name': 'test_throughput_basic',
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': 10.0,
            'task_count': 1000,
            'completed_tasks': 950,
            'failed_tasks': 50,
            'throughput': 95.0,
            'latency_p50': 10.5,
            'latency_p95': 25.3,
            'latency_p99': 45.2,
            'latency_avg': 15.2,
            'latency_min': 5.1,
            'latency_max': 50.0,
            'memory_peak': 256.5,
            'memory_avg': 200.3,
            'cpu_peak': 45.2,
            'cpu_avg': 35.1,
            'error_rate': 5.0,
        },
        {
            'test_name': 'test_latency_optimization',
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': 15.0,
            'task_count': 1500,
            'completed_tasks': 1450,
            'failed_tasks': 50,
            'throughput': 96.7,
            'latency_p50': 9.2,
            'latency_p95': 22.1,
            'latency_p99': 38.5,
            'latency_avg': 13.8,
            'latency_min': 4.2,
            'latency_max': 42.0,
            'memory_peak': 280.2,
            'memory_avg': 215.5,
            'cpu_peak': 48.5,
            'cpu_avg': 38.2,
            'error_rate': 3.3,
        },
        {
            'test_name': 'test_high_error_rate',
            'timestamp': datetime.now().isoformat(),
            'duration_seconds': 10.0,
            'task_count': 1000,
            'completed_tasks': 500,
            'failed_tasks': 500,
            'throughput': 50.0,
            'latency_p50': 20.0,
            'latency_p95': 50.0,
            'latency_p99': 100.0,
            'latency_avg': 30.0,
            'latency_min': 10.0,
            'latency_max': 150.0,
            'memory_peak': 512.0,
            'memory_avg': 400.0,
            'cpu_peak': 85.0,
            'cpu_avg': 70.0,
            'error_rate': 50.0,
        },
    ]


@pytest.fixture
def baseline_metrics(tmp_path):
    """Create baseline metrics file"""
    baselines = {
        'test_throughput_basic': {
            'throughput': 100.0,
            'latency_p95': 20.0,
            'memory_peak': 200.0,
            'cpu_peak': 40.0,
            'error_rate': 2.0,
            'timestamp': datetime.now().isoformat(),
        },
        'test_latency_optimization': {
            'throughput': 100.0,
            'latency_p95': 20.0,
            'memory_peak': 250.0,
            'cpu_peak': 45.0,
            'error_rate': 2.0,
            'timestamp': datetime.now().isoformat(),
        },
    }
    
    baseline_file = tmp_path / "baselines.json"
    with open(baseline_file, 'w') as f:
        json.dump(baselines, f)
    
    return baseline_file


class TestPerformanceAnalyzer:
    """Tests for PerformanceAnalyzer class"""
    
    def test_initialization(self):
        """Test analyzer initialization"""
        analyzer = PerformanceAnalyzer()
        assert analyzer.baselines == {}
        assert analyzer.insights == []
    
    def test_load_baselines(self, baseline_metrics):
        """Test loading baseline metrics"""
        analyzer = PerformanceAnalyzer(str(baseline_metrics))
        assert len(analyzer.baselines) == 2
        assert 'test_throughput_basic' in analyzer.baselines
    
    def test_save_baselines(self, analyzer, tmp_path):
        """Test saving baseline metrics"""
        analyzer.baselines['test_1'] = PerformanceBaseline(
            test_name='test_1',
            throughput=100.0,
            latency_p95=20.0,
            memory_peak=200.0,
            cpu_peak=40.0,
            error_rate=2.0,
            timestamp=datetime.now().isoformat(),
        )
        
        output_file = tmp_path / "saved_baselines.json"
        analyzer.save_baselines(str(output_file))
        
        assert output_file.exists()
        with open(output_file) as f:
            data = json.load(f)
            assert 'test_1' in data
    
    def test_analyze_metrics(self, analyzer, sample_metrics):
        """Test metrics analysis"""
        insights = analyzer.analyze_metrics(sample_metrics)
        
        assert isinstance(insights, list)
        assert len(insights) > 0
        
        # Check for expected insights
        categories = {i.category for i in insights}
        assert 'error' in categories  # High error rate should be detected
    
    def test_identify_bottlenecks(self, analyzer, sample_metrics):
        """Test bottleneck identification"""
        bottlenecks = analyzer.identify_bottlenecks(sample_metrics)
        
        assert 'throughput_bottlenecks' in bottlenecks
        assert 'latency_bottlenecks' in bottlenecks
        assert 'memory_bottlenecks' in bottlenecks
        assert 'cpu_bottlenecks' in bottlenecks
        assert 'error_bottlenecks' in bottlenecks
        
        # Verify bottlenecks are ranked
        if bottlenecks['throughput_bottlenecks']:
            assert bottlenecks['throughput_bottlenecks'][0]['rank'] == 1
    
    def test_compare_with_baseline(self, analyzer, sample_metrics, baseline_metrics):
        """Test baseline comparison"""
        analyzer_with_baseline = PerformanceAnalyzer(str(baseline_metrics))
        comparison = analyzer_with_baseline.compare_with_baseline(sample_metrics)
        
        assert 'tests_compared' in comparison
        assert 'regressions' in comparison
        assert 'improvements' in comparison
        assert 'new_tests' in comparison
        assert 'summary' in comparison
    
    def test_get_insights_by_severity(self, analyzer, sample_metrics):
        """Test filtering insights by severity"""
        analyzer.analyze_metrics(sample_metrics)
        
        critical = analyzer.get_insights_by_severity('critical')
        warnings = analyzer.get_insights_by_severity('warning')
        
        assert isinstance(critical, list)
        assert isinstance(warnings, list)
    
    def test_get_insights_by_category(self, analyzer, sample_metrics):
        """Test filtering insights by category"""
        analyzer.analyze_metrics(sample_metrics)
        
        error_insights = analyzer.get_insights_by_category('error')
        assert isinstance(error_insights, list)
    
    def test_generate_analysis_report(self, analyzer, sample_metrics):
        """Test comprehensive analysis report generation"""
        report = analyzer.generate_analysis_report(sample_metrics)
        
        assert 'timestamp' in report
        assert 'metrics_analyzed' in report
        assert 'insights' in report
        assert 'insights_summary' in report
        assert 'bottlenecks' in report
        assert 'baseline_comparison' in report
        
        assert report['metrics_analyzed'] == 3
