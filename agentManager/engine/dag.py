"""DAG Engine for task dependency management.

This module provides a Directed Acyclic Graph (DAG) engine for managing
task dependencies and execution order.

Cycle detection is implemented with depth-first search (DFS). Edge additions
are checked against a virtual view of the graph before mutation, so rejected
edges never need rollback and node dependency lists stay consistent. The DFS
tracks the active recursion stack and returns the concrete cycle path when a
back edge is found, which gives callers useful debugging context.
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple
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
    """Manages task DAG and dependency resolution.

    The engine keeps the graph acyclic by running DFS cycle detection before
    adding edges. The detector uses three-state visitation tracking:
    unvisited, visiting, and visited. Encountering an edge to a visiting node
    means the current recursion stack contains a cycle, and the matching slice
    of that stack is returned as the cycle path.
    """

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

        The proposed edge is validated with DFS cycle detection before the
        NetworkX graph or node dependency list is modified. If a cycle would
        be introduced, the error message includes the concrete cycle path.

        Args:
            from_node: Source node ID
            to_node: Target node ID

        Raises:
            ValueError: If nodes don't exist or would create cycle
        """
        if from_node not in self.nodes or to_node not in self.nodes:
            raise ValueError("One or both nodes not found")

        cycle_path = self._detect_cycle_path(extra_edge=(from_node, to_node))
        if cycle_path:
            cycle_description = " -> ".join(cycle_path)
            message = f"Adding edge {from_node}->{to_node} creates a cycle: " f"{cycle_description}"
            raise ValueError(message)

        self.graph.add_edge(from_node, to_node)

        # Update node dependencies
        if from_node not in self.nodes[to_node].dependencies:
            self.nodes[to_node].dependencies.append(from_node)

        logger.info(f"Added edge: {from_node} -> {to_node}")

    def _successors_with_extra_edge(
        self,
        node_id: str,
        extra_edge: Optional[Tuple[str, str]] = None,
    ) -> List[str]:
        """Return graph successors plus a proposed edge without mutation."""
        successors = list(self.graph.successors(node_id))
        if extra_edge and extra_edge[0] == node_id and extra_edge[1] not in successors:
            successors.append(extra_edge[1])
        return successors

    def _detect_cycle_path(
        self,
        extra_edge: Optional[Tuple[str, str]] = None,
    ) -> Optional[List[str]]:
        """Detect a cycle using DFS and optionally include a virtual edge.

        Args:
            extra_edge: Optional edge to include in traversal without adding it
                to the underlying graph.

        Returns:
            A list of node IDs describing the first cycle found, with the
            starting node repeated at the end, or None when the graph is
            acyclic.
        """
        visiting: set[str] = set()
        visited: set[str] = set()
        stack: List[str] = []
        stack_index: Dict[str, int] = {}

        def dfs(node_id: str) -> Optional[List[str]]:
            visiting.add(node_id)
            stack_index[node_id] = len(stack)
            stack.append(node_id)

            for successor in self._successors_with_extra_edge(node_id, extra_edge):
                if successor in visiting:
                    cycle_start = stack_index[successor]
                    return stack[cycle_start:] + [successor]

                if successor not in visited:
                    cycle_path = dfs(successor)
                    if cycle_path:
                        return cycle_path

            stack.pop()
            stack_index.pop(node_id)
            visiting.remove(node_id)
            visited.add(node_id)
            return None

        for node_id in self.nodes:
            if node_id not in visited:
                cycle_path = dfs(node_id)
                if cycle_path:
                    return cycle_path

        return None

    def detect_cycle_path(self) -> Optional[List[str]]:
        """Return the concrete cycle path if the graph contains a cycle.

        DFS tracks nodes currently on the recursion stack. When traversal sees
        an edge to a node already on that stack, that stack segment is the
        cycle. The returned path repeats the first node at the end, for
        example ``["A", "B", "A"]``.

        Returns:
            Cycle path if one is found, otherwise None.
        """
        return self._detect_cycle_path()

    def detect_deadlock(self) -> bool:
        """Detect if graph contains a cycle (deadlock).

        Uses the same DFS cycle detector as edge validation. When a cycle is
        found, the path is logged to make dependency deadlocks debuggable.

        Returns:
            True if cycle detected, False otherwise
        """
        cycle_path = self.detect_cycle_path()
        if cycle_path:
            logger.error("Deadlock detected: cycle found in DAG: %s", cycle_path)
            return True
        return False

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
                self.nodes[dep].status == TaskStatus.COMPLETED for dep in node.dependencies
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
