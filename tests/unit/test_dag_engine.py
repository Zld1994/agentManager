"""Unit tests for DAG engine."""

import pytest
from agentManager.engine.dag import DAGEngine, DAGNode, TaskStatus


class TestDAGNode:
    """Test DAGNode class."""

    def test_create_node(self):
        """Test creating a DAG node."""
        node = DAGNode(
            node_id="task_1",
            task_type="data_processing",
            dependencies=["task_0"],
        )
        assert node.node_id == "task_1"
        assert node.task_type == "data_processing"
        assert node.dependencies == ["task_0"]
        assert node.status == TaskStatus.PENDING

    def test_node_equality(self):
        """Test node equality."""
        node1 = DAGNode(node_id="task_1", task_type="type1")
        node2 = DAGNode(node_id="task_1", task_type="type2")
        assert node1 == node2  # Same node_id

    def test_node_hash(self):
        """Test node hashing."""
        node = DAGNode(node_id="task_1", task_type="type1")
        assert hash(node) == hash("task_1")


class TestDAGEngine:
    """Test DAGEngine class."""

    def test_add_node(self):
        """Test adding nodes to DAG."""
        engine = DAGEngine()
        node = DAGNode(node_id="task_1", task_type="type1")
        engine.add_node(node)
        assert "task_1" in engine.nodes
        assert engine.nodes["task_1"] == node

    def test_add_duplicate_node_fails(self):
        """Test that adding duplicate node raises error."""
        engine = DAGEngine()
        node = DAGNode(node_id="task_1", task_type="type1")
        engine.add_node(node)
        with pytest.raises(ValueError, match="already exists"):
            engine.add_node(node)

    def test_add_edge(self):
        """Test adding edges between nodes."""
        engine = DAGEngine()
        node1 = DAGNode(node_id="task_1", task_type="type1")
        node2 = DAGNode(node_id="task_2", task_type="type2")
        engine.add_node(node1)
        engine.add_node(node2)
        engine.add_edge("task_1", "task_2")
        assert "task_1" in engine.nodes["task_2"].dependencies

    def test_add_edge_nonexistent_node_fails(self):
        """Test that adding edge with nonexistent node fails."""
        engine = DAGEngine()
        node = DAGNode(node_id="task_1", task_type="type1")
        engine.add_node(node)
        with pytest.raises(ValueError, match="not found"):
            engine.add_edge("task_1", "task_999")

    def test_cycle_detection(self):
        """Test that cycles are detected and prevented."""
        engine = DAGEngine()
        node1 = DAGNode(node_id="task_1", task_type="type1")
        node2 = DAGNode(node_id="task_2", task_type="type2")
        engine.add_node(node1)
        engine.add_node(node2)
        engine.add_edge("task_1", "task_2")
        
        # Try to create cycle
        with pytest.raises(ValueError, match="creates a cycle"):
            engine.add_edge("task_2", "task_1")

    def test_detect_deadlock(self):
        """Test deadlock detection."""
        engine = DAGEngine()
        node1 = DAGNode(node_id="task_1", task_type="type1")
        node2 = DAGNode(node_id="task_2", task_type="type2")
        engine.add_node(node1)
        engine.add_node(node2)
        engine.add_edge("task_1", "task_2")
        
        # No cycle yet
        assert not engine.detect_deadlock()

    def test_get_ready_nodes(self):
        """Test getting ready nodes."""
        engine = DAGEngine()
        node1 = DAGNode(node_id="task_1", task_type="type1")
        node2 = DAGNode(node_id="task_2", task_type="type2", dependencies=["task_1"])
        engine.add_node(node1)
        engine.add_node(node2)
        engine.add_edge("task_1", "task_2")
        
        # task_1 is ready (no dependencies)
        ready = engine.get_ready_nodes()
        assert "task_1" in ready
        assert "task_2" not in ready
        
        # Mark task_1 as completed
        engine.update_node_status("task_1", TaskStatus.COMPLETED)
        ready = engine.get_ready_nodes()
        assert "task_2" in ready

    def test_topological_sort(self):
        """Test topological sorting."""
        engine = DAGEngine()
        node1 = DAGNode(node_id="task_1", task_type="type1")
        node2 = DAGNode(node_id="task_2", task_type="type2", dependencies=["task_1"])
        node3 = DAGNode(node_id="task_3", task_type="type3", dependencies=["task_2"])
        engine.add_node(node1)
        engine.add_node(node2)
        engine.add_node(node3)
        engine.add_edge("task_1", "task_2")
        engine.add_edge("task_2", "task_3")
        
        order = engine.topological_sort()
        assert order.index("task_1") < order.index("task_2")
        assert order.index("task_2") < order.index("task_3")

    def test_get_dependencies(self):
        """Test getting node dependencies."""
        engine = DAGEngine()
        node1 = DAGNode(node_id="task_1", task_type="type1")
        node2 = DAGNode(node_id="task_2", task_type="type2", dependencies=["task_1"])
        engine.add_node(node1)
        engine.add_node(node2)
        engine.add_edge("task_1", "task_2")
        
        deps = engine.get_dependencies("task_2")
        assert "task_1" in deps

    def test_get_dependents(self):
        """Test getting node dependents."""
        engine = DAGEngine()
        node1 = DAGNode(node_id="task_1", task_type="type1")
        node2 = DAGNode(node_id="task_2", task_type="type2", dependencies=["task_1"])
        engine.add_node(node1)
        engine.add_node(node2)
        engine.add_edge("task_1", "task_2")
        
        dependents = engine.get_dependents("task_1")
        assert "task_2" in dependents
