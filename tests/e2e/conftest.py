"""
Pytest configuration and fixtures for E2E tests
"""

import pytest
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from agentManager.engine.dag import DAGEngine
from agentManager.engine.event_bus import EventBus
from agentManager.engine.state_manager import StateMachine
from agentManager.engine.checkpoint import CheckpointManager
from agentManager.scheduler.scheduler_engine import SchedulerEngine
from agentManager.scheduler.resource_manager import ResourceManager
from agentManager.scheduler.conflict_detector import ConflictDetector
from agentManager.memory.session_memory import MemorySystem


@pytest.fixture
def project_root():
    """Return project root path"""
    return PROJECT_ROOT


@pytest.fixture
def temp_checkpoint_dir(tmp_path):
    """Create temporary checkpoint directory"""
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    return checkpoint_dir


@pytest.fixture
def dag_engine():
    """Create DAG engine instance"""
    engine = DAGEngine()
    yield engine


@pytest.fixture
def event_bus():
    """Create event bus instance"""
    bus = EventBus()
    yield bus


@pytest.fixture
def state_machine():
    """Create state machine instance"""
    machine = StateMachine()
    yield machine


@pytest.fixture
def checkpoint_manager(tmp_path):
    """Create checkpoint manager with temp directory"""
    manager = CheckpointManager(checkpoint_dir=str(tmp_path / "checkpoints"))
    yield manager


@pytest.fixture
def scheduler_engine():
    """Create scheduler engine instance"""
    engine = SchedulerEngine()
    yield engine


@pytest.fixture
def resource_manager():
    """Create resource manager instance"""
    manager = ResourceManager(
        max_concurrent_tasks=100,
        max_memory_mb=2048,
        max_cpu_percent=80
    )
    yield manager


@pytest.fixture
def conflict_detector():
    """Create conflict detector instance"""
    detector = ConflictDetector()
    yield detector


@pytest.fixture
def memory_system(tmp_path):
    """Create memory system instance"""
    system = MemorySystem(storage_path=str(tmp_path / "memory"))
    yield system
