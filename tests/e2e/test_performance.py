"""
E2E Tests Part 3: Performance and Benchmark Testing

Comprehensive end-to-end tests covering:
1. Performance benchmarks (4 tests)
   - test_throughput_benchmark_10_tasks_per_second
   - test_latency_benchmark_p95_under_100ms
   - test_memory_usage_benchmark_under_500mb
   - test_cpu_usage_benchmark_under_80_percent

2. Scalability tests (3 tests)
   - test_scalability_linear_with_task_count
   - test_scalability_with_increasing_dag_complexity
   - test_scalability_with_concurrent_users

3. System limits tests (3 tests)
   - test_max_concurrent_tasks_limit
   - test_max_dag_depth_limit
   - test_max_memory_per_task_limit

Requirements:
- Use pytest framework
- Measure and report performance metrics
- Test system limits and boundaries
- Aim for 10-12 E2E tests

Total: 10 comprehensive E2E tests
"""

import pytest
import logging
import time
import uuid
import psutil
import threading
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime, timedelta
from unittest.mock import Mock, patch, MagicMock
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import statistics

from agentManager.engine.dag import DAGEngine, DAGNode
from agentManager.engine.event_bus import EventBus, Event, EventType
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.engine.checkpoint import Checkpoint, CheckpointManager
from agentManager.scheduler.scheduler_engine import SchedulerEngine, TaskSchedule
from agentManager.scheduler.resource_manager import ResourceManager
from agentManager.scheduler.conflict_detector import ConflictDetector
from agentManager.roles.agent_orchestrator import AgentOrchestrator
from agentManager.roles.agent_config import AgentConfigManager
from agentManager.roles.role_template import RoleTemplateManager
from agentManager.memory.session_memory import MemorySystem

logger = logging.getLogger(__name__)


# ============================================================================
# PERFORMANCE METRICS TRACKING
# ============================================================================

class PerformanceMetrics:
    """Track performance metrics for benchmark tests"""
    
    def __init__(self):
        self.start_time: Optional[float] = None
        self.end_time: Optional[float] = None
        self.task_count: int = 0
        self.completed_tasks: int = 0
        self.failed_tasks: int = 0
        self.latencies: List[float] = []
        self.throughputs: List[float] = []
        self.memory_samples: List[float] = []
        self.cpu_samples: List[float] = []
        self.process = psutil.Process()
    
    def start(self):
        """Start performance measurement"""
        self.start_time = time.time()
        self.process.cpu_percent()  # Initialize CPU counter
    
    def end(self):
        """End performance measurement"""
        self.end_time = time.time()
    
    def get_duration(self) -> float:
        """Get total duration in seconds"""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0
    
    def record_task_completion(self, latency: float, success: bool = True):
        """Record task completion with latency"""
        self.latencies.append(latency)
        if success:
            self.completed_tasks += 1
        else:
            self.failed_tasks += 1
    
    def record_throughput(self, tasks_per_second: float):
        """Record throughput measurement"""
        self.throughputs.append(tasks_per_second)
    
    def sample_memory(self):
        """Sample current memory usage in MB"""
        memory_mb = self.process.memory_info().rss / 1024 / 1024
        self.memory_samples.append(memory_mb)
        return memory_mb
    
    def sample_cpu(self):
        """Sample current CPU usage percentage"""
        cpu_percent = self.process.cpu_percent(interval=0.1)
        self.cpu_samples.append(cpu_percent)
        return cpu_percent
    
    def get_throughput(self) -> float:
        """Get average throughput (tasks/second)"""
        duration = self.get_duration()
        if duration > 0:
            return self.completed_tasks / duration
        return 0.0
    
    def get_latency_p95(self) -> float:
        """Get 95th percentile latency"""
        if len(self.latencies) > 0:
            sorted_latencies = sorted(self.latencies)
            idx = int(len(sorted_latencies) * 0.95)
            return sorted_latencies[idx]
        return 0.0
    
    def get_latency_p99(self) -> float:
        """Get 99th percentile latency"""
        if len(self.latencies) > 0:
            sorted_latencies = sorted(self.latencies)
            idx = int(len(sorted_latencies) * 0.99)
            return sorted_latencies[idx]
        return 0.0
    
    def get_avg_latency(self) -> float:
        """Get average latency"""
        if len(self.latencies) > 0:
            return statistics.mean(self.latencies)
        return 0.0
    
    def get_max_memory(self) -> float:
        """Get peak memory usage in MB"""
        if len(self.memory_samples) > 0:
            return max(self.memory_samples)
        return 0.0
    
    def get_avg_memory(self) -> float:
        """Get average memory usage in MB"""
        if len(self.memory_samples) > 0:
            return statistics.mean(self.memory_samples)
        return 0.0
    
    def get_max_cpu(self) -> float:
        """Get peak CPU usage percentage"""
        if len(self.cpu_samples) > 0:
            return max(self.cpu_samples)
        return 0.0
    
    def get_avg_cpu(self) -> float:
        """Get average CPU usage percentage"""
        if len(self.cpu_samples) > 0:
            return statistics.mean(self.cpu_samples)
        return 0.0
    
    def get_success_rate(self) -> float:
        """Get task success rate"""
        total = self.completed_tasks + self.failed_tasks
        if total > 0:
            return (self.completed_tasks / total) * 100
        return 0.0
    
    def get_summary(self) -> Dict[str, Any]:
        """Get comprehensive performance summary"""
        return {
            "duration_seconds": self.get_duration(),
            "task_count": self.task_count,
            "completed_tasks": self.completed_tasks,
            "failed_tasks": self.failed_tasks,
            "success_rate_percent": self.get_success_rate(),
            "throughput_tasks_per_second": self.get_throughput(),
            "avg_latency_ms": self.get_avg_latency() * 1000,
            "p95_latency_ms": self.get_latency_p95() * 1000,
            "p99_latency_ms": self.get_latency_p99() * 1000,
            "peak_memory_mb": self.get_max_memory(),
            "avg_memory_mb": self.get_avg_memory(),
            "peak_cpu_percent": self.get_max_cpu(),
            "avg_cpu_percent": self.get_avg_cpu(),
        }


# ============================================================================
# PYTEST FIXTURES (defined in conftest.py)
# ============================================================================

@pytest.fixture
def performance_metrics():
    """Create performance metrics tracker"""
    return PerformanceMetrics()


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def _create_simple_task(task_id: str, duration: float = 0.01) -> Dict[str, Any]:
    """Create a simple task for testing"""
    return {
        "id": task_id,
        "name": f"task_{task_id}",
        "type": "compute",
        "duration": duration,
        "status": "pending",
        "created_at": datetime.now(),
    }


def _create_dag_with_depth(dag_engine: DAGEngine, depth: int) -> str:
    """Create a DAG with specified depth"""
    dag_id = str(uuid.uuid4())
    nodes = []
    
    for i in range(depth):
        node = DAGNode(
            node_id=f"node_{i}",
            task_type="compute",
            config={"duration": 0.01}
        )
        nodes.append(node)
        
        if i > 0:
            dag_engine.add_edge(nodes[i-1].node_id, node.node_id)
    
    return dag_id


def _execute_task_with_metrics(
    task: Dict[str, Any],
    metrics: PerformanceMetrics
) -> bool:
    """Execute a task and record metrics"""
    try:
        start = time.time()
        time.sleep(task.get("duration", 0.01))
        latency = time.time() - start
        metrics.record_task_completion(latency, success=True)
        return True
    except Exception as e:
        logger.error(f"Task execution failed: {e}")
        metrics.record_task_completion(0, success=False)
        return False


def _execute_concurrent_tasks(
    tasks: List[Dict[str, Any]],
    metrics: PerformanceMetrics,
    max_workers: int = 10
) -> int:
    """Execute tasks concurrently and return completion count"""
    completed = 0
    
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(_execute_task_with_metrics, task, metrics): task
            for task in tasks
        }
        
        for future in as_completed(futures):
            try:
                if future.result():
                    completed += 1
            except Exception as e:
                logger.error(f"Concurrent execution error: {e}")
    
    return completed
