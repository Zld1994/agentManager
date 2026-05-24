"""FastAPI application for agentManager.

This module provides REST API endpoints for workflow and task management.
"""

from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging
import uuid

from agentManager.engine.dag import DAGEngine, DAGNode, TaskStatus
from agentManager.engine.state_manager import StateMachine, TaskState
from agentManager.engine.event_bus import EventBus, EventType, Event
from agentManager.engine.scheduler import SchedulerEngine

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize FastAPI app
app = FastAPI(
    title="agentManager API",
    description="AI Agent Orchestration Control Plane",
    version="0.1.0",
)

# Initialize core engines
dag_engine = DAGEngine()
state_machine = StateMachine()
event_bus = EventBus()
scheduler = SchedulerEngine(max_concurrent_tasks=10)


# ============================================================================
# Pydantic Models
# ============================================================================

class TaskRequest(BaseModel):
    """Request to create a task."""
    node_id: str = Field(..., description="Unique task ID")
    task_type: str = Field(..., description="Type of task")
    dependencies: List[str] = Field(default_factory=list, description="Dependency task IDs")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Task metadata")


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
        "timestamp": datetime.utcnow(),
    }


@app.get("/status")
def get_status():
    """Get system status.
    
    Returns:
        Current system status including task counts
    """
    return {
        "total_tasks": len(dag_engine.nodes),
        "running_tasks": len(scheduler.running_tasks),
        "completed_tasks": len(scheduler.completed_tasks),
        "dag_nodes": len(dag_engine.nodes),
        "events_published": len(event_bus.events),
    }


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
            if dep not in dag_engine.nodes:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"Dependency not found: {dep}",
                )
            try:
                dag_engine.add_edge(dep, request.node_id)
            except ValueError as e:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=str(e),
                )

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
            event_id=str(uuid.uuid4()),
            event_type=EventType.TASK_CREATED,
            workflow_id="default",
            payload={"task_id": request.node_id, "task_type": request.task_type},
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
    ready_tasks = dag_engine.get_ready_nodes()
    return {
        "ready_tasks": ready_tasks,
        "total_tasks": len(dag_engine.nodes),
        "running_tasks": len(scheduler.running_tasks),
    }


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
        dag_engine.update_node_status(task_id, TaskStatus.COMPLETED)
        
        # Allow completion from any non-terminal state
        current_state = state_machine.get_state(task_id)
        if current_state not in [TaskState.COMPLETED, TaskState.BLOCKED_HITL]:
            state_machine.transition(task_id, TaskState.COMPLETED, reason="API request")
        
        scheduler.mark_completed(task_id)

        event_bus.publish(Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TASK_COMPLETED,
            workflow_id="default",
            payload={"task_id": task_id},
        ))

        return {"task_id": task_id, "status": "completed"}

    except Exception as e:
        logger.error(f"Error completing task: {e}")
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
        dag_engine.update_node_status(task_id, TaskStatus.FAILED)
        
        # Allow failure from any non-terminal state
        current_state = state_machine.get_state(task_id)
        if current_state not in [TaskState.COMPLETED, TaskState.BLOCKED_HITL]:
            state_machine.transition(task_id, TaskState.FAILED, reason=reason)
        
        scheduler.mark_failed(task_id)

        event_bus.publish(Event(
            event_id=str(uuid.uuid4()),
            event_type=EventType.TASK_FAILED,
            workflow_id="default",
            payload={"task_id": task_id, "reason": reason},
        ))

        return {"task_id": task_id, "status": "failed"}

    except Exception as e:
        logger.error(f"Error failing task: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e),
        )
