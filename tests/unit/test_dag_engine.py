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

    def _add_nodes(self, engine, *node_ids):
        """Add simple test nodes."""
        for node_id in node_ids:
            engine.add_node(DAGNode(node_id=node_id, task_type="type1"))

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
        with pytest.raises(ValueError, match="task_1 -> task_2 -> task_1"):
            engine.add_edge("task_2", "task_1")
        assert not engine.graph.has_edge("task_2", "task_1")
        assert "task_2" not in engine.nodes["task_1"].dependencies

    def test_detect_cycle_path_simple_cycle(self):
        """Test cycle path reporting for a simple A->B->A cycle."""
        engine = DAGEngine()
        self._add_nodes(engine, "A", "B")
        engine.graph.add_edges_from([("A", "B"), ("B", "A")])

        assert engine.detect_cycle_path() == ["A", "B", "A"]
        assert engine.detect_deadlock()

    def test_add_edge_rejects_simple_cycle_before_mutation(self):
        """Test that add_edge rejects A->B->A before mutating graph state."""
        engine = DAGEngine()
        self._add_nodes(engine, "A", "B")
        engine.add_edge("A", "B")

        with pytest.raises(ValueError, match="A -> B -> A"):
            engine.add_edge("B", "A")

        assert not engine.graph.has_edge("B", "A")
        assert "B" not in engine.nodes["A"].dependencies

    def test_add_edge_rejects_complex_cycle_before_mutation(self):
        """Test that add_edge rejects A->B->C->A cycles before mutation."""
        engine = DAGEngine()
        self._add_nodes(engine, "A", "B", "C")
        engine.add_edge("A", "B")
        engine.add_edge("B", "C")

        with pytest.raises(ValueError, match="A -> B -> C -> A"):
            engine.add_edge("C", "A")

        assert not engine.graph.has_edge("C", "A")
        assert "C" not in engine.nodes["A"].dependencies

    def test_add_edge_rejects_self_loop_before_mutation(self):
        """Test that add_edge rejects self-loops before mutating graph state."""
        engine = DAGEngine()
        self._add_nodes(engine, "A")

        with pytest.raises(ValueError, match="A -> A"):
            engine.add_edge("A", "A")

        assert not engine.graph.has_edge("A", "A")
        assert "A" not in engine.nodes["A"].dependencies

    def test_detect_cycle_path_multiple_independent_cycles(self):
        """Test cycle path reporting when multiple independent cycles exist."""
        engine = DAGEngine()
        self._add_nodes(engine, "A", "B", "C", "D")
        engine.graph.add_edges_from(
            [
                ("A", "B"),
                ("B", "A"),
                ("C", "D"),
                ("D", "C"),
            ]
        )

        cycle_path = engine.detect_cycle_path()

        assert cycle_path in (["A", "B", "A"], ["C", "D", "C"])
        assert engine.detect_deadlock()

    def test_detect_cycle_path_valid_dag_returns_none(self):
        """Test valid DAGs do not report a cycle path."""
        engine = DAGEngine()
        self._add_nodes(engine, "A", "B", "C", "D")
        engine.add_edge("A", "B")
        engine.add_edge("A", "C")
        engine.add_edge("B", "D")
        engine.add_edge("C", "D")

        assert engine.detect_cycle_path() is None
        assert not engine.detect_deadlock()

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
