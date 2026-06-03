"""FastAPI application for agentManager.

This module provides REST API endpoints for workflow and task management.
"""

import hmac
import logging
import os
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import Response
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from agentManager.config.settings import get_auth_settings, get_durable_backend_settings
from agentManager.domain.models import Event, EventType
from agentManager.engine.dag import DAGNode, TaskStatus
from agentManager.engine.event_bus.in_memory import InMemoryEventBus
from agentManager.engine.state_manager import TaskState
from agentManager.observability.logging import (
    clear_request_context,
    new_request_id,
    set_request_context,
    setup_logging,
)
from agentManager.observability.tracing import setup_tracing
from agentManager.runtime.factory import configure_runtime_audit_sinks, create_runtime
from agentManager.runtime.hooks import HookRunner

# Deferred task plan imports (used after runtime initialisation)
from agentManager.domain.task_plan import TaskPlan as _TaskPlan
from agentManager.domain.task_plan import TaskPlanItem as _TaskPlanItem
from agentManager.domain.task_plan import TaskPlanItemStatus as _TaskPlanItemStatus
from agentManager.domain.task_plan import TaskPlanStatus as _TaskPlanStatus

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
# The FastAPI process uses an in-process InMemoryEventBus for the
# synchronous ``publish``/``subscribe``/``get_events`` calls driven by the
# request handlers and in-process subscribers (hooks, tests). When the
# runtime's ``event_bus`` is also an ``InMemoryEventBus`` (i.e. no Redis
# configured), we reuse the same instance so API-published events are visible
# to runtime subscribers. When the runtime uses an async backend (e.g.
# ``RedisStreamEventBus``), a separate ``InMemoryEventBus`` is created for
# the synchronous API layer; the async runtime bus is left to workflow/task
# executor paths that ``await`` its coroutine methods.
_runtime_bus = _runtime.event_bus
if isinstance(_runtime_bus, InMemoryEventBus):
    event_bus = _runtime_bus
else:
    event_bus = InMemoryEventBus()
scheduler = _runtime.scheduler

# In-memory task plan storage (prototype) with thread-safe access
_task_plans: Dict[str, _TaskPlan] = {}
_task_plans_lock = threading.Lock()
hook_runner = HookRunner()

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
    # Security: use constant-time comparison to prevent timing attacks
    if not hmac.compare_digest(token, _auth_settings["auth_token"]):
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


class TaskPlanItemRequest(BaseModel):
    """Request model for a task plan item."""

    id: str = Field(..., min_length=1, description="Item ID")
    title: str = Field(..., min_length=1, description="Item title")
    description: str = ""
    priority: int = Field(default=0, ge=0)
    dependencies: List[str] = Field(default_factory=list)
    assignee: str = ""
    required_skills: List[str] = Field(default_factory=list)
    workdir: str = ""
    verification: str = ""
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("workdir")
    @classmethod
    def validate_workdir(cls, value: str) -> str:
        """Reject absolute paths and parent traversal in workdir."""
        if not value:
            return value
        if os.path.isabs(value):
            raise ValueError("workdir must be relative, not absolute")
        if ".." in Path(value).parts:
            raise ValueError("workdir must not contain '..'")
        return value


class TaskPlanRequest(BaseModel):
    """Request to create a task plan."""

    plan_id: str = Field(..., min_length=1, max_length=128)
    source_task_id: str = ""
    items: List[TaskPlanItemRequest] = Field(..., min_length=1)
    temporary_roles: List[str] = Field(default_factory=list)
    selected_templates: List[str] = Field(default_factory=list)
    preferred_assignees: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @field_validator("plan_id")
    @classmethod
    def validate_plan_id(cls, value: str) -> str:
        value = value.strip()
        if not TASK_ID_PATTERN.fullmatch(value):
            raise ValueError(
                "must contain only letters, numbers, dots, colons, " "underscores, or hyphens"
            )
        return value


class TaskPlanUpdateRequest(BaseModel):
    """Request to update a task plan."""

    items: Optional[List[TaskPlanItemRequest]] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskPlanItemResponse(BaseModel):
    """Response model for a task plan item."""

    id: str
    title: str
    description: str = ""
    priority: int = 0
    dependencies: List[str] = []
    assignee: str = ""
    required_skills: List[str] = []
    workdir: str = ""
    verification: str = ""
    status: str = "pending_review"
    metadata: Dict[str, Any] = {}


class TaskPlanResponse(BaseModel):
    """Response model for a task plan."""

    plan_id: str
    source_task_id: str = ""
    items: List[TaskPlanItemResponse]
    created_by: str = "manager"
    status: str = "draft"
    temporary_roles: List[str] = []
    selected_templates: List[str] = []
    preferred_assignees: List[str] = []
    created_at: datetime
    updated_at: datetime
    metadata: Dict[str, Any] = {}


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
        events_count = len(event_bus.events)
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


# ============================================================================
# Task Plan Endpoints
# ============================================================================


def _plan_to_response(plan: _TaskPlan) -> TaskPlanResponse:
    """Convert a TaskPlan dataclass to a TaskPlanResponse."""
    return TaskPlanResponse(
        plan_id=plan.plan_id,
        source_task_id=plan.source_task_id,
        items=[
            TaskPlanItemResponse(
                id=item.id,
                title=item.title,
                description=item.description,
                priority=item.priority,
                dependencies=item.dependencies,
                assignee=item.assignee,
                required_skills=item.required_skills,
                workdir=item.workdir,
                verification=item.verification,
                status=(
                    item.status.value
                    if isinstance(item.status, _TaskPlanItemStatus)
                    else item.status
                ),
                metadata=item.metadata,
            )
            for item in plan.items
        ],
        created_by=plan.created_by,
        status=plan.status.value if isinstance(plan.status, _TaskPlanStatus) else plan.status,
        temporary_roles=plan.temporary_roles,
        selected_templates=plan.selected_templates,
        preferred_assignees=plan.preferred_assignees,
        created_at=plan.created_at,
        updated_at=plan.updated_at,
        metadata=plan.metadata,
    )


@app.post("/task-plans", status_code=status.HTTP_201_CREATED)
def create_task_plan(
    request: TaskPlanRequest,
    _auth=Depends(verify_token),
):
    """Create a new task plan for review and confirmation."""
    with _task_plans_lock:
        if request.plan_id in _task_plans:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Task plan {request.plan_id} already exists",
            )

        try:
            items = [
                _TaskPlanItem(
                    id=req.id,
                    title=req.title,
                    description=req.description,
                    priority=req.priority,
                    dependencies=req.dependencies,
                    assignee=req.assignee,
                    required_skills=req.required_skills,
                    workdir=req.workdir,
                    verification=req.verification,
                    status=_TaskPlanItemStatus.PENDING_REVIEW,
                    metadata=req.metadata,
                )
                for req in request.items
            ]

            plan = _TaskPlan(
                plan_id=request.plan_id,
                source_task_id=request.source_task_id,
                items=items,
                status=_TaskPlanStatus.DRAFT,
                temporary_roles=request.temporary_roles,
                selected_templates=request.selected_templates,
                preferred_assignees=request.preferred_assignees,
                metadata=request.metadata,
            )
            plan.validate_dependencies()

            _task_plans[request.plan_id] = plan

            response = _plan_to_response(plan)
            event = Event(
                event_type=EventType.TASK_PLAN_CREATED,
                workflow_id=request.source_task_id or "default",
                payload={"plan_id": request.plan_id, "items_count": len(items)},
            )

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error creating task plan: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            )
    event_bus.publish(event)
    return response


@app.get("/task-plans/{plan_id}")
def get_task_plan(
    plan_id: str,
    _auth=Depends(verify_token),
):
    """Retrieve a task plan by ID."""
    with _task_plans_lock:
        if plan_id not in _task_plans:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task plan {plan_id} not found",
            )
        return _plan_to_response(_task_plans[plan_id])


@app.put("/task-plans/{plan_id}")
def update_task_plan(
    plan_id: str,
    request: TaskPlanUpdateRequest,
    _auth=Depends(verify_token),
):
    """Update a task plan (items and metadata)."""
    with _task_plans_lock:
        if plan_id not in _task_plans:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task plan {plan_id} not found",
            )

        plan = _task_plans[plan_id]
        plan_status = plan.status.value if isinstance(plan.status, _TaskPlanStatus) else plan.status
        if plan_status == _TaskPlanStatus.CONFIRMED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Cannot update a confirmed task plan",
            )

        try:
            if request.items is not None:
                # Build a lookup of existing items by id to preserve statuses
                existing_items = {item.id: item for item in plan.items}
                new_items: list[_TaskPlanItem] = []
                for req in request.items:
                    # Preserve existing item status if the item id matches
                    existing = existing_items.get(req.id)
                    preserved_status = (
                        existing.status
                        if existing is not None
                        else _TaskPlanItemStatus.PENDING_REVIEW
                    )
                    new_items.append(
                        _TaskPlanItem(
                            id=req.id,
                            title=req.title,
                            description=req.description,
                            priority=req.priority,
                            dependencies=req.dependencies,
                            assignee=req.assignee,
                            required_skills=req.required_skills,
                            workdir=req.workdir,
                            verification=req.verification,
                            status=preserved_status,
                            metadata=req.metadata,
                        )
                    )
                plan.items = new_items
                plan.validate_dependencies()

            if request.metadata is not None:
                plan.metadata = request.metadata

            plan.updated_at = utc_now()

            response = _plan_to_response(plan)
            event = Event(
                event_type=EventType.TASK_PLAN_UPDATED,
                workflow_id=plan.source_task_id or "default",
                payload={"plan_id": plan_id},
            )

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error updating task plan: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            )
    event_bus.publish(event)
    return response


@app.post("/task-plans/{plan_id}/confirm")
def confirm_task_plan(
    plan_id: str,
    _auth=Depends(verify_token),
):
    """Confirm a task plan, transitioning all items to confirmed status."""
    with _task_plans_lock:
        if plan_id not in _task_plans:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task plan {plan_id} not found",
            )

        plan = _task_plans[plan_id]
        plan_status = plan.status.value if isinstance(plan.status, _TaskPlanStatus) else plan.status
        if plan_status == _TaskPlanStatus.CONFIRMED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task plan is already confirmed",
            )

        try:
            plan.validate_dependencies()
            plan.validate_verification()
            hook_context = {
                "plan_id": plan_id,
                "source_task_id": plan.source_task_id or "",
                "items_count": str(len(plan.items)),
            }

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error confirming task plan: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            )

    try:
        hook_runner.run_hooks("before_task_plan_confirm", hook_context)
    except Exception as e:
        logger.error("Task plan confirmation hook failed: %s", e)
        event_bus.publish(
            Event(
                event_type=EventType.TASK_PLAN_CONFIRM_FAILED,
                workflow_id=hook_context["source_task_id"] or "default",
                payload={"plan_id": plan_id, "reason": str(e)},
            )
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Task plan confirmation hook failed",
        )

    with _task_plans_lock:
        plan = _task_plans.get(plan_id)
        if plan is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Task plan {plan_id} not found",
            )

        plan_status = plan.status.value if isinstance(plan.status, _TaskPlanStatus) else plan.status
        if plan_status == _TaskPlanStatus.CONFIRMED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Task plan is already confirmed",
            )

        try:
            plan.validate_dependencies()
            plan.validate_verification()

            plan.status = _TaskPlanStatus.CONFIRMED
            for item in plan.items:
                if item.status == _TaskPlanItemStatus.PENDING_REVIEW:
                    item.status = _TaskPlanItemStatus.CONFIRMED
                # Inject agent_id, workdir, and plan_id into item metadata
                # only if not already set by the user
                if item.assignee:
                    item.metadata.setdefault("agent_id", item.assignee)
                if item.workdir:
                    item.metadata.setdefault("workdir", item.workdir)
                item.metadata.setdefault("plan_id", plan_id)
            plan.updated_at = utc_now()

            response = _plan_to_response(plan)
            confirmed_event = Event(
                event_type=EventType.TASK_PLAN_CONFIRMED,
                workflow_id=plan.source_task_id or "default",
                payload={
                    "plan_id": plan_id,
                    "items_count": len(plan.items),
                    "assignees": list({item.assignee for item in plan.items if item.assignee}),
                },
            )

        except ValueError as e:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(e),
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error confirming task plan: {e}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Internal server error",
            )

    event_bus.publish(confirmed_event)
    try:
        hook_runner.run_hooks("after_task_plan_confirm", hook_context)
    except Exception as e:
        logger.error("Task plan post-confirm hook failed: %s", e)
        event_bus.publish(
            Event(
                event_type=EventType.TASK_PLAN_CONFIRM_FAILED,
                workflow_id=hook_context["source_task_id"] or "default",
                payload={"plan_id": plan_id, "reason": str(e)},
            )
        )
    return response
