# API Documentation

**agentManager REST API v0.1.0**

This document describes the REST API endpoints for agentManager. This project is a Phase 1 prototype and is not production-ready. All endpoints return JSON responses.

## Base URL

```
http://localhost:8000
```

## Authentication

Currently, no authentication is required. This will be added in Phase 2.

## Response Format

Responses are returned as plain JSON objects. Success responses use the endpoint-specific shape shown below. Error responses use FastAPI's standard `{"detail": "..."}` format.

## Endpoints

### Health & Status

#### GET /health

Health check endpoint. Use this to verify the API is running.

**Request**:
```bash
curl http://localhost:8000/health
```

**Response** (200 OK):
```json
{
  "status": "ok",
  "version": "0.1.0",
  "timestamp": "2026-05-24T04:00:00Z"
}
```

**Use Cases**:
- Kubernetes liveness probe
- Load balancer health check
- Monitoring and alerting

---

#### GET /status

Get current system status including task counts and metrics.

**Request**:
```bash
curl http://localhost:8000/status
```

**Response** (200 OK):
```json
{
  "total_tasks": 10,
  "running_tasks": 3,
  "completed_tasks": 5,
  "dag_nodes": 10,
  "events_published": 25
}
```

**Fields**:
- `total_tasks`: Total number of tasks in the system
- `running_tasks`: Number of currently running tasks
- `completed_tasks`: Number of completed tasks
- `dag_nodes`: Number of nodes in the DAG
- `events_published`: Total events published

---

### Task Management

#### POST /tasks

Create a new task in the system.

**Request**:
```bash
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "node_id": "task_1",
    "task_type": "data_processing",
    "dependencies": ["task_0"],
    "metadata": {"priority": "high"}
  }'
```

**Request Body**:
```json
{
  "node_id": "string (required)",
  "task_type": "string (required)",
  "dependencies": ["string"] (optional, default: []),
  "metadata": {object} (optional, default: {})
}
```

**Response** (201 Created):
```json
{
  "node_id": "task_1",
  "task_type": "data_processing",
  "status": "pending",
  "dependencies": ["task_0"],
  "metadata": {"priority": "high"}
}
```

**Error Responses**:
- 400 Bad Request: Task already exists or dependency not found
- 500 Internal Server Error: Server error

**Validation Rules**:
- `node_id`: Must be unique, non-empty string
- `task_type`: Must be non-empty string
- `dependencies`: All referenced tasks must exist
- No circular dependencies allowed

**Example**:
```bash
# Create a simple task
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"node_id":"task_1","task_type":"type1"}'

# Create task with dependencies
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "node_id":"task_2",
    "task_type":"type2",
    "dependencies":["task_1"]
  }'
```

---

#### GET /tasks/{task_id}

Get information about a specific task.

**Request**:
```bash
curl http://localhost:8000/tasks/task_1
```

**Response** (200 OK):
```json
{
  "node_id": "task_1",
  "task_type": "data_processing",
  "status": "pending",
  "dependencies": [],
  "metadata": {}
}
```

**Path Parameters**:
- `task_id`: The ID of the task to retrieve

**Response Fields**:
- `node_id`: Task identifier
- `task_type`: Type of task
- `status`: Current task status (pending, ready, running, verifying, completed, failed, blocked_repair, blocked_hitl)
- `dependencies`: List of dependency task IDs
- `metadata`: Custom metadata

**Error Responses**:
- 404 Not Found: Task does not exist

**Example**:
```bash
curl http://localhost:8000/tasks/task_1
```

---

#### GET /tasks/ready

Get all tasks that are ready for execution (no pending dependencies). The `ready_tasks` field contains task/node IDs, not full task objects.

**Request**:
```bash
curl http://localhost:8000/tasks/ready
```

**Response** (200 OK):
```json
{
  "ready_tasks": ["task_1", "task_3"],
  "total_tasks": 5,
  "running_tasks": 2
}
```

**Response Fields**:
- `ready_tasks`: List of task IDs ready to execute
- `total_tasks`: Total number of tasks in system
- `running_tasks`: Number of currently running tasks

**Use Cases**:
- Scheduler polling for next tasks to execute
- Monitoring dashboard
- Task distribution to workers

**Example**:
```bash
curl http://localhost:8000/tasks/ready
```

---

#### POST /tasks/{task_id}/complete

Mark a task as completed.

**Request**:
```bash
curl -X POST http://localhost:8000/tasks/task_1/complete
```

**Response** (200 OK):
```json
{
  "task_id": "task_1",
  "status": "completed"
}
```

**Path Parameters**:
- `task_id`: The ID of the task to complete

**Error Responses**:
- 404 Not Found: Task does not exist
- 500 Internal Server Error: Invalid state transition

**State Transitions**:
- The handler transitions any non-terminal task to `COMPLETED`.
- `COMPLETED` and `BLOCKED_HITL` are terminal states and are not transitioned by this endpoint.

**Example**:
```bash
curl -X POST http://localhost:8000/tasks/task_1/complete
```

---

#### POST /tasks/{task_id}/fail

Mark a task as failed.

**Request**:
```bash
curl -X POST "http://localhost:8000/tasks/task_1/fail?reason=timeout"
```

**Query Parameters**:
- `reason` (optional): Reason for failure

**Response** (200 OK):
```json
{
  "task_id": "task_1",
  "status": "failed"
}
```

**Path Parameters**:
- `task_id`: The ID of the task to fail

**Error Responses**:
- 404 Not Found: Task does not exist
- 500 Internal Server Error: Invalid state transition

**State Transitions**:
- The handler transitions any non-terminal task to `FAILED`.
- `COMPLETED` and `BLOCKED_HITL` are terminal states and are not transitioned by this endpoint.

**Example**:
```bash
# Fail task with reason
curl -X POST "http://localhost:8000/tasks/task_1/fail?reason=network_error"

# Fail task without reason
curl -X POST http://localhost:8000/tasks/task_1/fail
```

---

## Status Codes

| Code | Meaning |
|------|---------|
| 200 | OK - Request succeeded |
| 201 | Created - Resource created successfully |
| 400 | Bad Request - Invalid input or validation error |
| 404 | Not Found - Resource does not exist |
| 500 | Internal Server Error - Server error |

---

## Error Handling

All errors return a JSON response with a `detail` field:

```json
{
  "detail": "Task task_1 not found"
}
```

Common errors:
- "Task {id} already exists" - Duplicate task creation
- "Task {id} not found" - Task does not exist
- "Dependency not found: {id}" - Referenced dependency does not exist
- "Adding edge creates a cycle" - Circular dependency detected
- "Invalid transition: {from} → {to}" - Invalid state transition

---

## Rate Limiting

Currently, no rate limiting is implemented. This will be added in Phase 2.

---

## Pagination

Currently, no pagination is implemented. This will be added in Phase 2 when dealing with large datasets.

---

## Versioning

API version is included in responses. Current version: `0.1.0`

Future versions will be available at:
- `/v1/tasks` (v1 endpoints)
- `/v2/tasks` (v2 endpoints)

---

## WebSocket Support

WebSocket support for real-time event streaming will be added in Phase 2.

---

## Examples

### Complete Workflow

```bash
# 1. Create task_1
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"node_id":"task_1","task_type":"type1"}'

# 2. Create task_2 depending on task_1
curl -X POST http://localhost:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"node_id":"task_2","task_type":"type2","dependencies":["task_1"]}'

# 3. Check ready tasks (only task_1 is ready)
curl http://localhost:8000/tasks/ready

# 4. Complete task_1
curl -X POST http://localhost:8000/tasks/task_1/complete

# 5. Check ready tasks again (now task_2 is ready)
curl http://localhost:8000/tasks/ready

# 6. Complete task_2
curl -X POST http://localhost:8000/tasks/task_2/complete

# 7. Check status
curl http://localhost:8000/status
```

---

## Troubleshooting

### "Task not found" error
- Verify the task ID is correct
- Check that the task was created successfully

### "Dependency not found" error
- Ensure all dependency tasks exist
- Create dependencies before dependent tasks

### "Adding edge creates a cycle" error
- Check for circular dependencies
- Ensure task dependencies form a DAG (no cycles)

### "Invalid transition" error
- Check current task status
- Verify the target status is valid for current status

---

**Last Updated**: 2026-05-24  
**API Version**: 0.1.0  
**Status**: Phase 1 Complete
