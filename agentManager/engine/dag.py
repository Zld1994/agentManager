"""DAG Engine for task dependency management.

This module provides a Directed Acyclic Graph (DAG) engine for managing
task dependencies and execution order.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import networkx as nx
import logging

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    """Task execution status."""
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    BLOCKED_REPAIR = "blocked_repair"
    BLOCKED_HITL = "blocked_hitl"


@dataclass
class DAGNode:
    """Represents a task node in the DAG."""
    node_id: str
    task_type: str
    dependencies: List[str] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING

    def __hash__(self):
        return hash(self.node_id)

    def __eq__(self, other):
        if isinstance(other, DAGNode):
            return self.node_id == other.node_id
        return False


class DAGEngine:
    """Manages task DAG and dependency resolution."""

    def __init__(self):
        """Initialize DAG engine."""
        self.nodes: Dict[str, DAGNode] = {}
        self.graph = nx.DiGraph()

    def add_node(self, node: DAGNode) -> None:
        """Add a node to the DAG.

        Args:
            node: DAGNode to add

        Raises:
            ValueError: If node_id already exists
        """
        if node.node_id in self.nodes:
            raise ValueError(f"Node {node.node_id} already exists")

        self.nodes[node.node_id] = node
        self.graph.add_node(node.node_id)
        logger.info(f"Added node: {node.node_id}")

    def add_edge(self, from_node: str, to_node: str) -> None:
        """Add dependency edge from from_node to to_node.

        Args:
            from_node: Source node ID
            to_node: Target node ID

        Raises:
            ValueError: If nodes don't exist or would create cycle
        """
        if from_node not in self.nodes or to_node not in self.nodes:
            raise ValueError("One or both nodes not found")

        # Temporarily add edge to check for cycles
        self.graph.add_edge(from_node, to_node)

        # Check if adding this edge creates a cycle
        if not nx.is_directed_acyclic_graph(self.graph):
            self.graph.remove_edge(from_node, to_node)
            raise ValueError(
                f"Adding edge {from_node}->{to_node} creates a cycle"
            )

        # Update node dependencies
        if from_node not in self.nodes[to_node].dependencies:
            self.nodes[to_node].dependencies.append(from_node)

        logger.info(f"Added edge: {from_node} -> {to_node}")

    def detect_deadlock(self) -> bool:
        """Detect if graph contains a cycle (deadlock).

        Returns:
            True if cycle detected, False otherwise
        """
        has_cycle = not nx.is_directed_acyclic_graph(self.graph)
        if has_cycle:
            logger.error("Deadlock detected: cycle found in DAG")
        return has_cycle

    def get_ready_nodes(self) -> List[str]:
        """Get all nodes with no pending dependencies.

        Returns:
            List of node IDs that are ready to execute
        """
        ready = []
        for node_id, node in self.nodes.items():
            if node.status != TaskStatus.PENDING:
                continue

            # Check if all dependencies are completed
            all_deps_completed = all(
                self.nodes[dep].status == TaskStatus.COMPLETED
                for dep in node.dependencies
            )

            if all_deps_completed:
                ready.append(node_id)

        return ready

    def topological_sort(self) -> List[str]:
        """Get topological sort order of nodes.

        Returns:
            List of node IDs in topological order

        Raises:
            ValueError: If graph contains cycle
        """
        if self.detect_deadlock():
            raise ValueError("Cannot sort: DAG contains cycle")

        return list(nx.topological_sort(self.graph))

    def get_node(self, node_id: str) -> Optional[DAGNode]:
        """Get node by ID.

        Args:
            node_id: Node ID to retrieve

        Returns:
            DAGNode if found, None otherwise
        """
        return self.nodes.get(node_id)

    def update_node_status(self, node_id: str, status: TaskStatus) -> None:
        """Update node status.

        Args:
            node_id: Node ID to update
            status: New status

        Raises:
            ValueError: If node not found
        """
        if node_id not in self.nodes:
            raise ValueError(f"Node {node_id} not found")

        self.nodes[node_id].status = status
        logger.info(f"Updated node {node_id} status to {status.value}")

    def get_dependencies(self, node_id: str) -> List[str]:
        """Get all dependencies of a node.

        Args:
            node_id: Node ID

        Returns:
            List of dependency node IDs
        """
        if node_id not in self.nodes:
            return []
        return self.nodes[node_id].dependencies

    def get_dependents(self, node_id: str) -> List[str]:
        """Get all nodes that depend on this node.

        Args:
            node_id: Node ID

        Returns:
            List of dependent node IDs
        """
        if node_id not in self.nodes:
            return []
        return list(self.graph.successors(node_id))
