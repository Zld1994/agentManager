"""Unit tests for TaskHistory module."""

import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from agentManager.memory import MemorySystem, TaskHistory, TaskRecord


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    yield db_path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def memory_system(temp_db):
    """Create a MemorySystem instance with temporary database."""
    system = MemorySystem(db_path=temp_db)
    yield system
    system.close()


def utc_now():
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


@pytest.fixture
def task_history(memory_system):
    """Create a TaskHistory instance."""
    return TaskHistory(memory_system)


def test_task_record_creation():
    """Test TaskRecord dataclass creation."""
    now = utc_now()
    record = TaskRecord(
        task_id="task_001",
        session_id="session_001",
        task_name="Test Task",
        status="running",
        start_time=now,
    )
    assert record.task_id == "task_001"
    assert record.session_id == "session_001"
    assert record.status == "running"
    assert record.end_time is None


def test_task_record_serialization():
    """Test TaskRecord to_dict and from_dict."""
    now = utc_now()
    record = TaskRecord(
        task_id="task_001",
        session_id="session_001",
        task_name="Test Task",
        status="completed",
        start_time=now,
        result={"output": "success"},
    )

    data = record.to_dict()
    assert data["task_id"] == "task_001"
    assert isinstance(data["start_time"], str)

    restored = TaskRecord.from_dict(data)
    assert restored.task_id == record.task_id
    assert restored.result == record.result


def test_record_task_start(task_history):
    """Test recording task start."""
    task_history.record_task_start("session_001", "task_001", "Test Task")
    record = task_history.get_task_record("task_001")

    assert record is not None
    assert record.task_id == "task_001"
    assert record.status == "running"
    assert record.end_time is None


def test_record_task_end(task_history):
    """Test recording task end."""
    task_history.record_task_start("session_001", "task_001", "Test Task")
    task_history.record_task_end("task_001", "completed", result={"output": "success"})

    record = task_history.get_task_record("task_001")
    assert record.status == "completed"
    assert record.end_time is not None
    assert record.result == {"output": "success"}


def test_get_task_duration(task_history):
    """Test task duration calculation."""
    task_history.record_task_start("session_001", "task_001", "Test Task")
    task_history.record_task_end("task_001", "completed")

    duration = task_history.get_task_duration("task_001")
    assert duration is not None
    assert duration >= 0


def test_get_session_tasks(task_history):
    """Test retrieving all tasks for a session."""
    task_history.record_task_start("session_001", "task_001", "Task 1")
    task_history.record_task_start("session_001", "task_002", "Task 2")
    task_history.record_task_start("session_002", "task_003", "Task 3")

    session_tasks = task_history.get_session_tasks("session_001")
    assert len(session_tasks) == 2


def test_get_failed_tasks(task_history):
    """Test retrieving failed tasks."""
    task_history.record_task_start("session_001", "task_001", "Task 1")
    task_history.record_task_end("task_001", "failed", error="Test error")

    task_history.record_task_start("session_001", "task_002", "Task 2")
    task_history.record_task_end("task_002", "completed")

    failed_tasks = task_history.get_failed_tasks()
    assert len(failed_tasks) >= 1


def test_search_tasks(task_history):
    """Test searching tasks."""
    task_history.record_task_start("session_001", "task_001", "Database Query")
    task_history.record_task_start("session_001", "task_002", "API Request")

    results = task_history.search_tasks("Database")
    assert len(results) >= 1
