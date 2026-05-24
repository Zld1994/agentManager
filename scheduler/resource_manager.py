"""
Resource Manager for agentManager.

Provides real-time resource tracking, allocation/deallocation logic,
and utilization metrics for task execution management.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Optional
import psutil


@dataclass
class ResourceMetrics:
    """Represents current resource utilization metrics."""
    
    timestamp: datetime
    cpu_usage: float  # 0-100%
    memory_usage: float  # 0-100%
    gpu_usage: float  # 0-100%
    network_usage: float  # 0-100%
    active_tasks: int
    
    def __post_init__(self) -> None:
        """Validate metric ranges."""
        for attr in ["cpu_usage", "memory_usage", "gpu_usage", "network_usage"]:
            value = getattr(self, attr)
            if not 0 <= value <= 100:
                raise ValueError(f"{attr} must be between 0 and 100")
        if self.active_tasks < 0:
            raise ValueError("active_tasks must be non-negative")


@dataclass
class ResourcePool:
    """Represents a resource pool with allocation tracking."""
    
    pool_id: str
    total_cpu: float
    total_memory: float
    total_gpu: float
    total_network: float
    allocated: Dict[str, Dict[str, float]] = field(default_factory=dict)
    
    def get_total_allocated(self, resource_type: str) -> float:
        """
        Get total allocated amount for a resource type.
        
        Args:
            resource_type: Type of resource (cpu, memory, gpu, network).
            
        Returns:
            Total allocated amount.
        """
        total = 0.0
        for task_resources in self.allocated.values():
            total += task_resources.get(resource_type, 0.0)
        return total
    
    def get_available(self, resource_type: str) -> float:
        """
        Get available amount for a resource type.
        
        Args:
            resource_type: Type of resource (cpu, memory, gpu, network).
            
        Returns:
            Available amount.
        """
        total_attr = f"total_{resource_type}"
        if not hasattr(self, total_attr):
            return 0.0
        
        total = getattr(self, total_attr)
        allocated = self.get_total_allocated(resource_type)
        return total - allocated


class ResourceManager:
    """
    Manages resource allocation, deallocation, and monitoring.
    
    Tracks resource usage across tasks, enforces allocation limits,
    and provides real-time utilization metrics.
    """
    
    def __init__(
        self,
        total_cpu: float,
        total_memory: float,
        total_gpu: float,
        total_network: float,
    ) -> None:
        """
        Initialize the resource manager.
        
        Args:
            total_cpu: Total CPU cores available.
            total_memory: Total memory in GB available.
            total_gpu: Total GPU units available.
            total_network: Total network bandwidth in Mbps available.
        """
        self.pool = ResourcePool(
            pool_id="default",
            total_cpu=total_cpu,
            total_memory=total_memory,
            total_gpu=total_gpu,
            total_network=total_network,
        )
        self.task_allocations: Dict[str, Dict[str, float]] = {}
        self.active_tasks: int = 0
    
    def allocate_resources(
        self,
        task_id: str,
        cpu: float,
        memory: float,
        gpu: float = 0.0,
        network: float = 0.0,
    ) -> bool:
        """
        Allocate resources to a task.
        
        Args:
            task_id: Unique task identifier.
            cpu: CPU cores to allocate.
            memory: Memory in GB to allocate.
            gpu: GPU units to allocate (default: 0).
            network: Network bandwidth in Mbps to allocate (default: 0).
            
        Returns:
            True if allocation successful, False if insufficient resources.
        """
        # Check if task already allocated
        if task_id in self.task_allocations:
            return False
        
        # Check resource availability
        if not self.check_resource_availability(cpu, memory, gpu, network):
            return False
        
        # Allocate resources
        allocation = {
            "cpu": cpu,
            "memory": memory,
            "gpu": gpu,
            "network": network,
        }
        self.task_allocations[task_id] = allocation
        self.pool.allocated[task_id] = allocation
        self.active_tasks += 1
        
        return True
    
    def release_resources(self, task_id: str) -> None:
        """
        Release resources allocated to a task.
        
        Args:
            task_id: Unique task identifier.
        """
        if task_id in self.task_allocations:
            del self.task_allocations[task_id]
            del self.pool.allocated[task_id]
            self.active_tasks = max(0, self.active_tasks - 1)
    
    def get_available_resources(self) -> Dict[str, float]:
        """
        Get currently available resources.
        
        Returns:
            Dictionary with available amounts for each resource type.
        """
        return {
            "cpu": self.pool.get_available("cpu"),
            "memory": self.pool.get_available("memory"),
            "gpu": self.pool.get_available("gpu"),
            "network": self.pool.get_available("network"),
        }
    
    def get_resource_metrics(self) -> ResourceMetrics:
        """
        Get current resource utilization metrics.
        
        Returns:
            ResourceMetrics object with current system metrics.
        """
        # Calculate utilization percentages
        cpu_usage = (
            (self.pool.get_total_allocated("cpu") / self.pool.total_cpu * 100)
            if self.pool.total_cpu > 0
            else 0.0
        )
        memory_usage = (
            (self.pool.get_total_allocated("memory") / self.pool.total_memory * 100)
            if self.pool.total_memory > 0
            else 0.0
        )
        gpu_usage = (
            (self.pool.get_total_allocated("gpu") / self.pool.total_gpu * 100)
            if self.pool.total_gpu > 0
            else 0.0
        )
        network_usage = (
            (self.pool.get_total_allocated("network") / self.pool.total_network * 100)
            if self.pool.total_network > 0
            else 0.0
        )
        
        return ResourceMetrics(
            timestamp=datetime.now(),
            cpu_usage=min(cpu_usage, 100.0),
            memory_usage=min(memory_usage, 100.0),
            gpu_usage=min(gpu_usage, 100.0),
            network_usage=min(network_usage, 100.0),
            active_tasks=self.active_tasks,
        )
    
    def check_resource_availability(
        self,
        cpu: float,
        memory: float,
        gpu: float = 0.0,
        network: float = 0.0,
    ) -> bool:
        """
        Check if requested resources are available.
        
        Args:
            cpu: CPU cores required.
            memory: Memory in GB required.
            gpu: GPU units required (default: 0).
            network: Network bandwidth in Mbps required (default: 0).
            
        Returns:
            True if resources are available, False otherwise.
        """
        available = self.get_available_resources()
        
        return (
            available["cpu"] >= cpu
            and available["memory"] >= memory
            and available["gpu"] >= gpu
            and available["network"] >= network
        )
    
    def get_resource_utilization(self) -> Dict[str, Dict[str, float]]:
        """
        Get detailed resource utilization statistics.
        
        Returns:
            Dictionary with utilization stats for each resource type.
        """
        utilization = {}
        
        for resource_type in ["cpu", "memory", "gpu", "network"]:
            total = getattr(self.pool, f"total_{resource_type}")
            allocated = self.pool.get_total_allocated(resource_type)
            available = self.pool.get_available(resource_type)
            
            utilization[resource_type] = {
                "total": total,
                "allocated": allocated,
                "available": available,
                "utilization_percent": (
                    (allocated / total * 100) if total > 0 else 0.0
                ),
            }
        
        return utilization
