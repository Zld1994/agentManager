"""FastAPI application for agentManager.

This module provides REST API endpoints for workflow and task management.
"""

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any
from datetime import datetime, timezone
import logging
import time
import re
import uuid

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from agentManager.engine.dag import DAGEngine, DAGNode, TaskStatus
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.engine.event_bus import EventBus, EventType, Event
from agentManager.engine.scheduler import SchedulerEngine
from agentManager.config.settings import get_observability_settings
from agentManager.observability.logging import (
    clear_correlation_id,
    configure_logging,
    set_correlation_id,
)
from agentManager.observability.audit import configure_audit_logger
from agentManager.observability.tracing import configure_tracing

# Configure logging
observability_settings = get_observability_settings()
configure_logging(observability_settings)
configure_audit_logger(observability_settings)
configure_tracing(observability_settings)
logger = logging.getLogger(__name__)
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


# Initialize FastAPI app
app = FastAPI(
    title="agentManager API",
    description="AI Agent Orchestration Control Plane",
    version="0.1.0",
)


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    """Attach a request correlation ID to logs and responses."""
    header_name = observability_settings["request_correlation_header"]
    correlation_id = request.headers.get(header_name) or str(uuid.uuid4())
    set_correlation_id(correlation_id)
    try:
        response = await call_next(request)
        response.headers[header_name] = correlation_id
        return response
    finally:
        clear_correlation_id()

# Initialize core engines
dag_engine = DAGEngine()
state_machine = StateMachine()
event_bus = EventBus()
scheduler = SchedulerEngine(max_concurrent_tasks=10)

# ============================================================================
# Prometheus Metrics
# ============================================================================

# Task metrics
tasks_total = Counter(
    'agentmanager_tasks_total',
    'Total number of tasks created',
    ['task_type']
)

task_duration_seconds = Histogram(
    'agentmanager_task_duration_seconds',
    'Task execution duration in seconds',
    ['task_type'],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0)
)

errors_total = Counter(
    'agentmanager_errors_total',
    'Total number of task errors',
    ['error_type']
)

repairs_total = Counter(
    'agentmanager_repairs_total',
    'Total number of repairs performed',
    ['repair_type']
)

# Task timing tracking (for duration calculation)
_task_start_times: Dict[str, float] = {}


# ============================================================================
# Metrics Endpoint
# ============================================================================

@app.get("/metrics")
def metrics():
    """Prometheus metrics endpoint.

    Returns:
        Prometheus format metrics
    """
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


# ============================================================================
# Pydantic Models
# ============================================================================

class TaskRequest(BaseModel):
    """Request to create a task."""
    node_id: str = Field(..., min_length=1, max_length=128, description="Unique task ID")
    task_type: str = Field(..., min_length=1, max_length=64, description="Type of task")
    dependencies: List[str] = Field(default_factory=list, description="Dependency task IDs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Task metadata")

    @field_validator("node_id", "task_type")
    @classmethod
    def validate_identifier(cls, value: str) -> str:
        """Validate task identifiers and task types."""
        value = value.strip()
        if not TASK_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "must contain only letters, numbers, dots, colons, underscores, or hyphens"
            )
        return value

    @field_validator("dependencies")
    @classmethod
    def validate_dependencies(cls, dependencies: List[str]) -> List[str]:
        """Validate dependency IDs and remove duplicates while preserving order."""
        seen = set()
        normalized = []
        for dep in dependencies:
            dep = dep.strip()
            if not dep:
                raise ValueError("dependency IDs must not be empty")
            if not TASK_ID_PATTERN.fullmatch(dep):
                raise ValueError(
                    "dependency IDs must contain only letters, numbers, dots, colons, "
                    "underscores, or hyphens"
                )
            if dep not in seen:
                seen.add(dep)
                normalized.append(dep)
        return normalized


class TaskResponse(BaseModel):
    """Response containing task information."""
    node_id: str
    task_type: str
    status: str
    dependencies: List[str]
    metadata: Dict[str, Any]


class WorkflowRequest(BaseModel):
    """Request to create a workflow."""
    workflow_id: str = Field(..., description="Unique workflow ID")
    tasks: List[TaskRequest] = Field(..., description="List of tasks")


class WorkflowResponse(BaseModel):
    """Response containing workflow information."""
    workflow_id: str
    tasks: List[TaskResponse]
    status: str
    created_at: datetime


class HealthResponse(BaseModel):
    """Health check response."""
    status: str
    version: str
    timestamp: datetime


class ReadyTasksResponse(BaseModel):
    """Response containing ready tasks."""
    ready_tasks: List[str]
    total_tasks: int
    running_tasks: int


class EventResponse(BaseModel):
    """Response containing event information."""
    event_id: str
    event_type: str
    workflow_id: str
    payload: Dict[str, Any]
    timestamp: datetime


# ============================================================================
# Health & Status Endpoints
# ============================================================================

@app.get("/health", response_model=HealthResponse)
def health_check():
    """Health check endpoint.

    Returns:
        Health status and version information
    """
    return {
        "status": "ok",
        "version": "0.1.0",
        "timestamp": utc_now(),
    }


@app.get("/status")
def get_status():
    """Get system status.

    Returns:
        Current system status including task counts
    """
    try:
        return {
            "total_tasks": len(dag_engine.nodes),
            "running_tasks": len(scheduler.running_tasks),
            "completed_tasks": len(scheduler.completed_tasks),
            "dag_nodes": len(dag_engine.nodes),
            "events_published": len(event_bus.events),
        }
    except Exception as e:
        logger.error(f"Error getting system status: {e}")
        errors_total.labels(error_type="status").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get system status",
        )


# ============================================================================
# Task Management Endpoints
# ============================================================================

@app.post("/tasks", response_model=TaskResponse, status_code=status.HTTP_201_CREATED)
def create_task(request: TaskRequest):
    """Create a new task.

    Args:
        request: Task creation request

    Returns:
        Created task information

    Raises:
        HTTPException: If task creation fails
    """
    try:
        # Check if task already exists
        if request.node_id in dag_engine.nodes:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task {request.node_id} already exists",
            )

        for dep in request.dependencies:
            if dep not in dag_engine.nodes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Dependency not found: {dep}",
                )

        # Create DAG node
        node = DAGNode(
            node_id=request.node_id,
            task_type=request.task_type,
            dependencies=request.dependencies,
            metadata=request.metadata,
        )
        dag_engine.add_node(node)

        # Add edges for dependencies
        for dep in request.dependencies:
            try:
                dag_engine.add_edge(dep, request.node_id)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                )

        # Track task creation metric after DAG mutations succeed.
        tasks_total.labels(task_type=request.task_type).inc()
        _task_start_times[request.node_id] = time.time()

        # Initialize state machine
        state_machine.initialize(request.node_id, TaskState.PENDING)

        # Add to scheduler
        scheduler.add_task(
            task_id=request.node_id,
            priority=0,
            dependencies=request.dependencies,
        )

        # Publish event
        event_bus.publish(Event(
            event_type=EventType.TASK_CREATED,
            workflow_id="default",
            payload={
                "task_id": request.node_id,
                "task_type": request.task_type,
            },
        ))

        return {
            "node_id": request.node_id,
            "task_type": request.task_type,
            "status": "pending",
            "dependencies": request.dependencies,
            "metadata": request.metadata,
        }

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating task: {e}")
        errors_total.labels(error_type="task_creation").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.get("/tasks/ready", response_model=ReadyTasksResponse)
def get_ready_tasks():
    """Get all tasks ready for execution.

    Returns:
        List of ready task IDs
    """
    try:
        ready_tasks = dag_engine.get_ready_nodes()
        return {
            "ready_tasks": ready_tasks,
            "total_tasks": len(dag_engine.nodes),
            "running_tasks": len(scheduler.running_tasks),
        }
    except Exception as e:
        logger.error(f"Error getting ready tasks: {e}")
        errors_total.labels(error_type="ready_tasks").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get ready tasks",
        )


@app.get("/tasks/{task_id}", response_model=TaskResponse)
def get_task(task_id: str):
    """Get task information.

    Args:
        task_id: Task ID

    Returns:
        Task information

    Raises:
        HTTPException: If task not found
    """
    try:
        node = dag_engine.get_node(task_id)
        if not node:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task {task_id} not found",
            )

        return {
            "node_id": node.node_id,
            "task_type": node.task_type,
            "status": node.status.value,
            "dependencies": node.dependencies,
            "metadata": node.metadata,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting task {task_id}: {e}")
        errors_total.labels(error_type="task_retrieval").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get task",
        )


@app.post("/tasks/{task_id}/complete")
def complete_task(task_id: str):
    """Mark task as completed.

    Args:
        task_id: Task ID

    Returns:
        Updated task status

    Raises:
        HTTPException: If task not found
    """
    if task_id not in dag_engine.nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    try:
        # Calculate and record task duration
        if task_id in _task_start_times:
            duration = time.time() - _task_start_times[task_id]
            node = dag_engine.get_node(task_id)
            if node:
                task_duration_seconds.labels(task_type=node.task_type).observe(duration)
            del _task_start_times[task_id]

        dag_engine.update_node_status(task_id, TaskStatus.COMPLETED)

        # Allow completion from any non-terminal state
        current_state = state_machine.get_state(task_id)
        if current_state not in [TaskState.COMPLETED, TaskState.BLOCKED_HITL]:
            state_machine.transition(task_id, TaskState.COMPLETED, reason="API request")

        scheduler.mark_completed(task_id)

        event_bus.publish(Event(
            event_type=EventType.TASK_COMPLETED,
            workflow_id="default",
            payload={"task_id": task_id},
        ))

        return {"task_id": task_id, "status": "completed"}

    except Exception as e:
        logger.error(f"Error completing task: {e}")
        errors_total.labels(error_type="task_completion").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )


@app.post("/tasks/{task_id}/fail")
def fail_task(task_id: str, reason: str = ""):
    """Mark task as failed.

    Args:
        task_id: Task ID
        reason: Failure reason

    Returns:
        Updated task status

    Raises:
        HTTPException: If task not found
    """
    if task_id not in dag_engine.nodes:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task {task_id} not found",
        )

    try:
        # Track error metric
        errors_total.labels(error_type="task_failure").inc()

        # Clean up timing tracking
        if task_id in _task_start_times:
            del _task_start_times[task_id]

        dag_engine.update_node_status(task_id, TaskStatus.FAILED)

        # Allow failure from any non-terminal state
        current_state = state_machine.get_state(task_id)
        if current_state not in [TaskState.COMPLETED, TaskState.BLOCKED_HITL]:
            state_machine.transition(task_id, TaskState.FAILED, reason=reason)

        scheduler.mark_failed(task_id)

        event_bus.publish(Event(
            event_type=EventType.TASK_FAILED,
            workflow_id="default",
            payload={"task_id": task_id, "reason": reason},
        ))

        return {"task_id": task_id, "status": "failed"}

    except Exception as e:
        logger.error(f"Error failing task: {e}")
        errors_total.labels(error_type="task_failure_handler").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
