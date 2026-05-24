"""
Unit tests for Resource Manager.

Tests resource allocation, deallocation, availability checking,
and utilization metrics.
"""

import pytest
from datetime import datetime
import sys
sys.path.insert(0, '/home/zld/allProject/agentManager')

from scheduler.resource_manager import (
    ResourceMetrics,
    ResourcePool,
    ResourceManager,
)


class TestResourceMetrics:
    """Test ResourceMetrics dataclass."""
    
    def test_valid_metrics(self) -> None:
        """Test creating valid metrics."""
        metrics = ResourceMetrics(
            timestamp=datetime.now(),
            cpu_usage=50.0,
            memory_usage=75.0,
            gpu_usage=25.0,
            network_usage=10.0,
            active_tasks=5,
        )
        assert metrics.cpu_usage == 50.0
        assert metrics.active_tasks == 5
    
    def test_invalid_cpu_usage(self) -> None:
        """Test invalid CPU usage raises error."""
        with pytest.raises(ValueError):
            ResourceMetrics(
                timestamp=datetime.now(),
                cpu_usage=150.0,  # Invalid: > 100
                memory_usage=50.0,
                gpu_usage=0.0,
                network_usage=0.0,
                active_tasks=0,
            )
    
    def test_invalid_negative_tasks(self) -> None:
        """Test negative active tasks raises error."""
        with pytest.raises(ValueError):
            ResourceMetrics(
                timestamp=datetime.now(),
                cpu_usage=50.0,
                memory_usage=50.0,
                gpu_usage=0.0,
                network_usage=0.0,
                active_tasks=-1,
            )


class TestResourcePool:
    """Test ResourcePool dataclass."""
    
    def test_pool_creation(self) -> None:
        """Test creating a resource pool."""
        pool = ResourcePool(
            pool_id="test_pool",
            total_cpu=8.0,
            total_memory=16.0,
            total_gpu=2.0,
            total_network=1000.0,
        )
        assert pool.pool_id == "test_pool"
        assert pool.total_cpu == 8.0
    
    def test_get_total_allocated(self) -> None:
        """Test calculating total allocated resources."""
        pool = ResourcePool(
            pool_id="test_pool",
            total_cpu=8.0,
            total_memory=16.0,
            total_gpu=2.0,
            total_network=1000.0,
        )
        pool.allocated["task1"] = {"cpu": 2.0, "memory": 4.0, "gpu": 0.5, "network": 100.0}
        pool.allocated["task2"] = {"cpu": 1.0, "memory": 2.0, "gpu": 0.5, "network": 50.0}
        
        assert pool.get_total_allocated("cpu") == 3.0
        assert pool.get_total_allocated("memory") == 6.0
        assert pool.get_total_allocated("gpu") == 1.0
    
    def test_get_available(self) -> None:
        """Test calculating available resources."""
        pool = ResourcePool(
            pool_id="test_pool",
            total_cpu=8.0,
            total_memory=16.0,
            total_gpu=2.0,
            total_network=1000.0,
        )
        pool.allocated["task1"] = {"cpu": 2.0, "memory": 4.0, "gpu": 0.5, "network": 100.0}
        
        assert pool.get_available("cpu") == 6.0
        assert pool.get_available("memory") == 12.0
        assert pool.get_available("gpu") == 1.5


class TestResourceManager:
    """Test ResourceManager class."""
    
    @pytest.fixture
    def manager(self) -> ResourceManager:
        """Create a resource manager for testing."""
        return ResourceManager(
            total_cpu=8.0,
            total_memory=16.0,
            total_gpu=2.0,
            total_network=1000.0,
        )
    
    def test_initialization(self, manager: ResourceManager) -> None:
        """Test resource manager initialization."""
        assert manager.pool.total_cpu == 8.0
        assert manager.pool.total_memory == 16.0
        assert manager.active_tasks == 0
    
    def test_allocate_resources_success(self, manager: ResourceManager) -> None:
        """Test successful resource allocation."""
        result = manager.allocate_resources(
            task_id="task1",
            cpu=2.0,
            memory=4.0,
            gpu=0.5,
            network=100.0,
        )
        assert result is True
        assert "task1" in manager.task_allocations
        assert manager.active_tasks == 1
    
    def test_allocate_resources_insufficient(self, manager: ResourceManager) -> None:
        """Test allocation fails with insufficient resources."""
        result = manager.allocate_resources(
            task_id="task1",
            cpu=10.0,  # More than available
            memory=4.0,
        )
        assert result is False
        assert "task1" not in manager.task_allocations
    
    def test_allocate_duplicate_task(self, manager: ResourceManager) -> None:
        """Test allocation fails for duplicate task ID."""
        manager.allocate_resources(
            task_id="task1",
            cpu=2.0,
            memory=4.0,
        )
        result = manager.allocate_resources(
            task_id="task1",
            cpu=1.0,
            memory=2.0,
        )
        assert result is False
    
    def test_release_resources(self, manager: ResourceManager) -> None:
        """Test resource release."""
        manager.allocate_resources(
            task_id="task1",
            cpu=2.0,
            memory=4.0,
        )
        assert manager.active_tasks == 1
        
        manager.release_resources("task1")
        assert "task1" not in manager.task_allocations
        assert manager.active_tasks == 0
    
    def test_get_available_resources(self, manager: ResourceManager) -> None:
        """Test getting available resources."""
        manager.allocate_resources(
            task_id="task1",
            cpu=2.0,
            memory=4.0,
            gpu=0.5,
            network=100.0,
        )
        
        available = manager.get_available_resources()
        assert available["cpu"] == 6.0
        assert available["memory"] == 12.0
        assert available["gpu"] == 1.5
        assert available["network"] == 900.0
    
    def test_get_resource_metrics(self, manager: ResourceManager) -> None:
        """Test getting resource metrics."""
        manager.allocate_resources(
            task_id="task1",
            cpu=4.0,
            memory=8.0,
            gpu=1.0,
            network=500.0,
        )
        
        metrics = manager.get_resource_metrics()
        assert metrics.cpu_usage == 50.0  # 4/8 * 100
        assert metrics.memory_usage == 50.0  # 8/16 * 100
        assert metrics.gpu_usage == 50.0  # 1/2 * 100
        assert metrics.network_usage == 50.0  # 500/1000 * 100
        assert metrics.active_tasks == 1
    
    def test_check_resource_availability_true(self, manager: ResourceManager) -> None:
        """Test resource availability check returns true."""
        result = manager.check_resource_availability(
            cpu=4.0,
            memory=8.0,
            gpu=1.0,
            network=500.0,
        )
        assert result is True
    
    def test_check_resource_availability_false(self, manager: ResourceManager) -> None:
        """Test resource availability check returns false."""
        result = manager.check_resource_availability(
            cpu=10.0,  # More than available
            memory=8.0,
        )
        assert result is False
    
    def test_get_resource_utilization(self, manager: ResourceManager) -> None:
        """Test getting resource utilization statistics."""
        manager.allocate_resources(
            task_id="task1",
            cpu=2.0,
            memory=4.0,
            gpu=0.5,
            network=100.0,
        )
        manager.allocate_resources(
            task_id="task2",
            cpu=2.0,
            memory=4.0,
            gpu=0.5,
            network=100.0,
        )
        
        utilization = manager.get_resource_utilization()
        
        assert utilization["cpu"]["total"] == 8.0
        assert utilization["cpu"]["allocated"] == 4.0
        assert utilization["cpu"]["available"] == 4.0
        assert utilization["cpu"]["utilization_percent"] == 50.0
        
        assert utilization["memory"]["allocated"] == 8.0
        assert utilization["memory"]["utilization_percent"] == 50.0
    
    def test_multiple_allocations_and_releases(self, manager: ResourceManager) -> None:
        """Test multiple allocation and release cycles."""
        # Allocate 3 tasks
        for i in range(3):
            result = manager.allocate_resources(
                task_id=f"task{i}",
                cpu=1.0,
                memory=2.0,
            )
            assert result is True
        
        assert manager.active_tasks == 3
        
        # Release first task
        manager.release_resources("task0")
        assert manager.active_tasks == 2
        
        # Allocate new task with freed resources
        result = manager.allocate_resources(
            task_id="task3",
            cpu=2.0,
            memory=4.0,
        )
        assert result is True
        assert manager.active_tasks == 3
