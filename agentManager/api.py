"""FastAPI application for agentManager.

This module provides REST API endpoints for workflow and task management.
"""

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import Response
from pydantic import BaseModel, Field, field_validator
from typing import List, Dict, Any
from datetime import datetime, timezone
from starlette.middleware.trustedhost import TrustedHostMiddleware
import logging
import os
import time
import re

from prometheus_client import Counter, Histogram, generate_latest, CONTENT_TYPE_LATEST

from agentManager.engine.dag import DAGNode, TaskStatus
from agentManager.engine.state_manager import TaskState
from agentManager.engine.event_bus import EventType, Event
from agentManager.observability.logging import (
    setup_logging,
    new_request_id,
    set_request_context,
    clear_request_context,
)
from agentManager.config.settings import get_auth_settings, get_durable_backend_settings
from agentManager.observability.tracing import setup_tracing
from agentManager.runtime.factory import configure_runtime_audit_sinks, create_runtime

# Configure structured logging (JSON by default, respects LOG_LEVEL/LOG_JSON env)
setup_logging()
logger = logging.getLogger(__name__)
TASK_ID_PATTERN = re.compile(r"^[A-Za-z0-9_.:-]+$")

# Initialise tracing (no-op unless OTEL_TRACING_ENABLED=true).
setup_tracing()


def utc_now() -> datetime:
    """Return a timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


_docs_enabled = os.getenv("DOCS_ENABLED", "true").lower() != "false"
_docs_kwargs = {} if _docs_enabled else {"docs_url": None, "redoc_url": None, "openapi_url": None}

# Initialize FastAPI app
app = FastAPI(
    title="agentManager API",
    description="AI Agent Orchestration Control Plane",
    version="0.1.0",
    **_docs_kwargs,
)


def _instrument_fastapi_app(fastapi_app: FastAPI) -> bool:
    """Instrument FastAPI when the optional OTEL instrumentation package exists."""
    try:
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
    except (ImportError, AttributeError):
        logger.debug("FastAPI OpenTelemetry instrumentation is unavailable")
        return False
    FastAPIInstrumentor.instrument_app(fastapi_app)
    return True


_instrument_fastapi_app(app)


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    """Attach security headers to every response."""
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    return response


@app.middleware("http")
async def request_body_size_limit_middleware(request: Request, call_next):
    """Reject requests whose Content-Length exceeds the configured limit."""
    content_length = request.headers.get("content-length")
    if content_length:
        max_size = int(os.getenv("MAX_REQUEST_BODY_SIZE", "1048576"))
        try:
            if int(content_length) > max_size:
                return Response(
                    status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                    content="Request body too large",
                )
        except ValueError:
            pass
    return await call_next(request)


_allowed_hosts_str = os.getenv("ALLOWED_HOSTS", "")
if _allowed_hosts_str:
    _allowed_hosts = [h.strip() for h in _allowed_hosts_str.split(",") if h.strip()]
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=_allowed_hosts)


@app.middleware("http")
async def request_correlation_middleware(request: Request, call_next):
    """Attach a correlation ID to every request for log tracing."""
    req_id = request.headers.get("X-Request-ID") or new_request_id()
    set_request_context(request_id=req_id)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = req_id
        return response
    finally:
        clear_request_context()


# Initialize core engines via RuntimeFactory
_runtime_settings = get_durable_backend_settings()
configure_runtime_audit_sinks(_runtime_settings)
_runtime = create_runtime(settings=_runtime_settings)
dag_engine = _runtime.dag_engine
state_machine = _runtime.state_machine
event_bus = _runtime.event_bus
scheduler = _runtime.scheduler

# ============================================================================
# Prometheus Metrics
# ============================================================================

# Task metrics
tasks_total = Counter("agentmanager_tasks_total", "Total number of tasks created", ["task_type"])

task_duration_seconds = Histogram(
    "agentmanager_task_duration_seconds",
    "Task execution duration in seconds",
    ["task_type"],
    buckets=(0.1, 0.5, 1.0, 2.5, 5.0, 10.0, 30.0, 60.0),
)

errors_total = Counter("agentmanager_errors_total", "Total number of task errors", ["error_type"])

repairs_total = Counter(
    "agentmanager_repairs_total", "Total number of repairs performed", ["repair_type"]
)

# Task timing tracking (for duration calculation)
_task_start_times: Dict[str, float] = {}


# ============================================================================
# Authentication
# ============================================================================

_auth_settings = get_auth_settings()


def verify_token(request: Request):
    """Validate Bearer token when API authentication is enabled."""
    if not _auth_settings["auth_enabled"]:
        return
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )
    token = auth_header[7:]
    if token != _auth_settings["auth_token"]:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Unauthorized",
        )


# ============================================================================
# Metrics Endpoint
# ============================================================================

_metrics_enabled = os.getenv("METRICS_ENABLED", "true").lower() != "false"

if _metrics_enabled:

    @app.get("/metrics")
    def metrics(_auth=Depends(verify_token)):
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
    dependencies: Dict[str, str] = Field(default_factory=dict)


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
def health_check(response: Response, strict: bool = False):
    """Health check endpoint.

    Returns:
        Health status and version information
    """
    dependencies: Dict[str, str] = {}
    if os.getenv("DATABASE_URL"):
        dependencies["postgres"] = _check_postgres_dependency(os.environ["DATABASE_URL"])
    if os.getenv("REDIS_URL"):
        dependencies["redis"] = _check_redis_dependency(os.environ["REDIS_URL"])

    degraded = any(value != "ok" for value in dependencies.values())
    health_status = "ok"
    if degraded:
        health_status = "unhealthy" if strict else "degraded"
    if strict and degraded:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE

    return {
        "status": health_status,
        "version": "0.1.0",
        "timestamp": utc_now(),
        "dependencies": dependencies,
    }


def _check_postgres_dependency(database_url: str) -> str:
    try:
        import psycopg

        with psycopg.connect(database_url, connect_timeout=2) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
        return "ok"
    except Exception:
        logger.exception("PostgreSQL health check failed")
        return "degraded"


def _check_redis_dependency(redis_url: str) -> str:
    try:
        import redis

        client = redis.from_url(redis_url, socket_connect_timeout=2, socket_timeout=2)
        client.ping()
        return "ok"
    except Exception:
        logger.exception("Redis health check failed")
        return "degraded"


@app.get("/status")
def get_status(_auth=Depends(verify_token)):
    """Get system status.

    Returns:
        Current system status including task counts
    """
    try:
        events_count = len(event_bus.events) if hasattr(event_bus, "events") else 0
        return {
            "total_tasks": len(dag_engine.nodes),
            "running_tasks": len(scheduler.running_tasks),
            "completed_tasks": len(scheduler.completed_tasks),
            "dag_nodes": len(dag_engine.nodes),
            "events_published": events_count,
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
def create_task(request: TaskRequest, _auth=Depends(verify_token)):
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
        from agentManager.observability.logging import get_request_id

        event_bus.publish(
            Event(
                event_type=EventType.TASK_CREATED,
                workflow_id="default",
                payload={
                    "task_id": request.node_id,
                    "task_type": request.task_type,
                    "correlation_id": get_request_id() or "unknown",
                },
            )
        )

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
            detail="Internal server error",
        )


@app.get("/tasks/ready", response_model=ReadyTasksResponse)
def get_ready_tasks(_auth=Depends(verify_token)):
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
def get_task(task_id: str, _auth=Depends(verify_token)):
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
def complete_task(task_id: str, _auth=Depends(verify_token)):
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

        event_bus.publish(
            Event(
                event_type=EventType.TASK_COMPLETED,
                workflow_id="default",
                payload={"task_id": task_id},
            )
        )

        return {"task_id": task_id, "status": "completed"}

    except Exception as e:
        logger.error(f"Error completing task: {e}")
        errors_total.labels(error_type="task_completion").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )


@app.post("/tasks/{task_id}/fail")
def fail_task(task_id: str, reason: str = "", _auth=Depends(verify_token)):
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

        event_bus.publish(
            Event(
                event_type=EventType.TASK_FAILED,
                workflow_id="default",
                payload={"task_id": task_id, "reason": reason},
            )
        )

        return {"task_id": task_id, "status": "failed"}

    except Exception as e:
        logger.error(f"Error failing task: {e}")
        errors_total.labels(error_type="task_failure_handler").inc()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error",
        )
