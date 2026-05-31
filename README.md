# agentManager

**AI Agent Orchestration Control Plane Prototype**

> **Current Status**: Phase 1 Prototype  
> **This project is NOT production-ready yet.**

## 📋 Project Status

agentManager 是一个 AI Agent 控制平面的原型实现。它提供了任务依赖管理、状态机、事件总线和调度器的基础框架。

### ✅ Implemented (Phase 1)
- In-memory DAG engine with cycle detection
- Task state machine with emergency transitions
- Event bus with wildcard subscriptions
- Scheduler with conflict detection and backoff
- FastAPI REST API (7 endpoints)
- 66 unit tests (100% passing)
- Opt-in durable backend interfaces for PostgreSQL state, S3-compatible checkpoints,
  Redis Streams retries, and pluggable vector memory

### 🔄 Planned (Phase 2-4)
- FastAPI service with full CRUD
- Real L1-L4 repair workflow
- Docker sandbox hardening
- GitHub Actions CI/CD

---

## 🚀 Quick Start

### Installation
```bash
# Clone repository
git clone https://github.com/Zld1994/agentManager.git
cd agentManager

# Install in development mode
pip install -e .

# Install dev dependencies (optional)
pip install -e ".[dev]"
```

### Run Tests
```bash
# Run all unit tests
pytest tests/unit/ -v

# Run specific test module
pytest tests/unit/test_dag_engine.py -v

# Run with coverage
pytest tests/unit/ --cov=agentManager --cov-report=term-missing
```

### Start API Server
```bash
# Start FastAPI server
python -m uvicorn agentManager.api:app --host 127.0.0.1 --port 8000

# Access API documentation
# Swagger UI: http://localhost:8000/docs
# ReDoc: http://localhost:8000/redoc
```

### Runtime Modes

agentManager supports three runtime modes, selected automatically by the
`RuntimeFactory` based on environment variables:

| Mode | State | Events | Checkpoints | Memory | When |
|------|-------|--------|-------------|--------|------|
| **local memory** (default) | In-memory | In-memory | In-memory | SQLite | No `DATABASE_URL` / `REDIS_URL` set |
| **local durable** | In-memory | In-memory | In-memory | SQLite + vector backend | `VECTOR_BACKEND=qdrant` |
| **production-like** | PostgreSQL | Redis Streams | S3/MinIO | SQLite + Qdrant | All env vars set |

**local memory** — All state lives in process memory. Suitable for
development, testing, and short-lived experiments. Data is lost on restart.

**local durable** — Structured data persists in SQLite while vector search
delegates to Qdrant (or the built-in Jaccard fallback). Suitable for
single-machine long-running sessions.

**production-like** — Full durable stack via Docker Compose: PostgreSQL for
state, Redis Streams for events, S3-compatible storage for checkpoints, and
Qdrant for vector search. Requires `docker compose up`.

### Durable Backend Configuration

Local usage defaults to in-memory state and SQLite-backed memory.
Production-oriented durability is opt-in through environment variables:

```bash
DATABASE_URL=postgresql://agentmanager:secret@postgres:5432/agentmanager
REDIS_URL=redis://redis:6379/0
OBJECT_STORE_ENDPOINT=http://minio:9000
OBJECT_STORE_BUCKET=agentmanager-checkpoints
OBJECT_STORE_ACCESS_KEY=...
OBJECT_STORE_SECRET_KEY=...
VECTOR_BACKEND=sqlite  # sqlite, memory, or qdrant
QDRANT_URL=http://qdrant:6333
QDRANT_API_KEY=...
```

The `RuntimeFactory` reads these variables at startup and wires the
appropriate backend implementations. When a URL is empty or unset, the
corresponding in-memory or SQLite fallback is used automatically. If a
durable backend fails to initialise (e.g. Postgres is unreachable), the
factory logs a warning and falls back to the in-memory default so the API
remains functional.

`agentManager.storage` exposes the durable repository/object-store interfaces. Unit tests mock
PostgreSQL, Redis, S3/MinIO, and Qdrant clients, so a live service stack is not required for the
default test workflow.

### Observability Configuration

The API installs a request correlation middleware and exposes Prometheus metrics at `/metrics`.
Structured JSON logs, audit helpers, and local-safe tracing hooks for workflow, task, and recovery
operations are configured through environment variables:

```bash
LOG_LEVEL=INFO
LOG_FORMAT=json
REQUEST_CORRELATION_HEADER=X-Request-ID
WORKFLOW_CORRELATION_METADATA_KEY=correlation_id
AUDIT_LOGGER_NAME=agentManager.audit
OTEL_TRACING_ENABLED=false
OTEL_SERVICE_NAME=agentManager
OTEL_EXPORTER_OTLP_ENDPOINT=
```

Tracing remains disabled by default for local development. `OTEL_TRACING_ENABLED=true` records the
opt-in setting for deployments that wire a collector/exporter around these hooks.

### Test API Endpoints
```bash
# Health check
curl http://127.0.0.1:8000/health

# Get system status
curl http://127.0.0.1:8000/status

# Create a task
curl -X POST http://127.0.0.1:8000/tasks \
  -H "Content-Type: application/json" \
  -d '{"node_id":"task_1","task_type":"data_processing"}'

# Get ready tasks
curl http://127.0.0.1:8000/tasks/ready

# Complete a task
curl -X POST http://127.0.0.1:8000/tasks/task_1/complete
```

---

## 📁 Project Structure

```
agentManager/
├── api.py                          # FastAPI application entry point
├── engine/
│   ├── __init__.py
│   ├── dag.py                      # DAG engine (cycle detection fixed)
│   ├── state_manager.py            # State machine (HITL fixed)
│   ├── event_bus.py                # Event bus (wildcard fixed)
│   └── scheduler.py                # Scheduler (deadlock fixed)
├── memory/
│   ├── memory_system.py
│   └── task_history.py
├── observability/                  # Logging, audit, and tracing helpers
├── runtime/                        # Reserved for Phase 2
│   └── __init__.py
└── __init__.py

monitoring/
└── prometheus.yml                  # Prometheus configuration

tests/
├── unit/
│   ├── test_dag_engine.py          # 13 tests
│   ├── test_state_manager.py       # 12 tests
│   ├── test_event_bus.py           #  9 tests
│   ├── test_scheduler.py           # 17 tests
│   └── test_api.py                 # 15 tests
├── integration/                    # Reserved for Phase 2
└── e2e/                            # Reserved for Phase 3

pyproject.toml                       # Project configuration
README.md                            # This file
```

---

## 🔌 API Reference

### Health & Status

#### GET /health
Health check endpoint.

**Response** (200 OK):
```json
{
  "status": "ok",
  "version": "0.1.0",
  "timestamp": "2026-05-24T04:00:00Z"
}
```

#### GET /status
Get system status.

**Response** (200 OK):
```json
{
  "total_tasks": 5,
  "running_tasks": 2,
  "completed_tasks": 1,
  "dag_nodes": 5,
  "events_published": 12
}
```

### Task Management

#### POST /tasks
Create a new task.

**Request Body**:
```json
{
  "node_id": "task_1",
  "task_type": "data_processing",
  "dependencies": ["task_0"],
  "metadata": {}
}
```

**Response** (201 Created):
```json
{
  "node_id": "task_1",
  "task_type": "data_processing",
  "status": "pending",
  "dependencies": ["task_0"],
  "metadata": {}
}
```

**Errors**:
- 400: Task already exists or dependency not found
- 500: Internal server error

#### GET /tasks/{task_id}
Get task information.

**Response** (200 OK):
```json
{
  "node_id": "task_1",
  "task_type": "data_processing",
  "status": "pending",
  "dependencies": ["task_0"],
  "metadata": {}
}
```

**Errors**:
- 404: Task not found

#### GET /tasks/ready
Get all tasks ready for execution.

**Response** (200 OK):
```json
{
  "ready_tasks": ["task_1", "task_3"],
  "total_tasks": 5,
  "running_tasks": 2
}
```

#### POST /tasks/{task_id}/complete
Mark task as completed.

**Response** (200 OK):
```json
{
  "task_id": "task_1",
  "status": "completed"
}
```

**Errors**:
- 404: Task not found
- 500: State transition error

#### POST /tasks/{task_id}/fail
Mark task as failed.

**Query Parameters**:
- `reason` (optional): Failure reason

**Response** (200 OK):
```json
{
  "task_id": "task_1",
  "status": "failed"
}
```

**Errors**:
- 404: Task not found
- 500: State transition error

---

## 🧪 Testing

### Test Coverage
- **DAG Engine**: Node creation, edge addition, cycle detection, topological sort
- **State Machine**: Initialization, transitions, history, emergency HITL
- **Event Bus**: Subscribe, publish, filtering, wildcard subscriptions
- **Scheduler**: Task scheduling, conflict detection, backoff mechanism
- **API**: CRUD operations, error handling, integration flows

### Test Statistics
```
test_dag_engine.py        13/13 ✅
test_state_manager.py     12/12 ✅
test_event_bus.py          9/9  ✅
test_scheduler.py         17/17 ✅
test_api.py               15/15 ✅
────────────────────────────────
Total                     66/66 ✅ (100%)
```

### Running Tests
```bash
# Run all tests
pytest tests/unit/ -v

# Run with coverage report
pytest tests/unit/ --cov=agentManager --cov-report=html

# Run specific test
pytest tests/unit/test_dag_engine.py::TestDAGEngine::test_cycle_detection -v
```

---

## 🏗️ Core Modules

### DAG Engine (`agentManager/engine/dag.py`)

Manages task dependencies and execution order.

```python
from agentManager.engine import DAGEngine, DAGNode, TaskStatus

engine = DAGEngine()
engine.add_node(DAGNode(node_id="task_1", task_type="type1"))
engine.add_node(DAGNode(node_id="task_2", task_type="type2"))
engine.add_edge("task_1", "task_2")
engine.update_node_status("task_1", TaskStatus.COMPLETED)
ready = engine.get_ready_nodes()  # ["task_2"]
```

**Key Features**:
- Cycle detection using NetworkX
- Topological sorting
- Ready node discovery
- Status tracking

### State Machine (`agentManager/engine/state_manager.py`)

Manages task lifecycle and state transitions.

```python
from agentManager.engine import StateMachine, TaskState

sm = StateMachine()
sm.initialize("task_1", TaskState.PENDING)
sm.transition("task_1", TaskState.READY)
sm.transition("task_1", TaskState.IMPLEMENTING)
sm.transition("task_1", TaskState.VERIFYING)
sm.transition("task_1", TaskState.COMPLETED)

sm.initialize("task_2", TaskState.READY)
sm.transition("task_2", TaskState.BLOCKED_HITL)  # Emergency transition from a non-terminal state
```

**Key Features**:
- Valid state transitions
- Emergency HITL from any non-terminal state
- Transition history tracking
- Terminal state detection

### Event Bus (`agentManager/engine/event_bus.py`)

Publishes and subscribes to task events.

```python
from agentManager.engine import EventBus, Event, EventType

bus = EventBus()
bus.subscribe(EventType.TASK_COMPLETED, callback)
bus.subscribe(EventType.TASK_COMPLETED, callback, workflow_id=None)  # Global
event = Event(event_id="e1", event_type=EventType.TASK_COMPLETED, workflow_id="wf1")
bus.publish(event)
```

**Key Features**:
- Workflow-specific subscriptions
- Global wildcard subscriptions
- Event filtering by type and workflow
- Exception handling in callbacks

### Scheduler (`agentManager/engine/scheduler.py`)

Schedules and manages task execution.

```python
from agentManager.engine import SchedulerEngine

scheduler = SchedulerEngine(max_concurrent_tasks=10)
scheduler.add_task("task_1", priority=5, dependencies=["task_0"])
scheduler.execute_scheduled_tasks()
scheduler.mark_completed("task_1")
```

**Key Features**:
- Priority-based scheduling
- Dependency conflict detection
- Backoff mechanism for retries
- Concurrent task limit

---

## 🔧 Key Fixes (Phase 1)

### 1. DAG Cycle Detection
**Problem**: `topological_sort()` returns generator, cycle not detected if not consumed  
**Fix**: Use `nx.is_directed_acyclic_graph()` for direct DAG check

### 2. Scheduler Deadlock
**Problem**: Conflicted tasks immediately re-queued, causing infinite loop  
**Fix**: Deferred queue + backoff mechanism (5 second retry delay)

### 3. StateMachine HITL
**Problem**: Only `BLOCKED_REPAIR → BLOCKED_HITL` allowed  
**Fix**: Allow emergency transitions from any non-terminal state

### 4. EventBus Wildcard
**Problem**: Global listeners not triggered  
**Fix**: Publish triggers both exact and wildcard subscriptions

---

## 📈 Development Roadmap

### Phase 1 ✅ (Complete)
- [x] DAG engine with cycle detection
- [x] State machine with HITL
- [x] Event bus with wildcard subscriptions
- [x] Scheduler with backoff
- [x] FastAPI REST API
- [x] 66 unit tests

### Phase 2 (1-2 weeks)
- [x] PostgreSQL state repository interface
- [x] Redis Streams event bus with ACK/retry/DLQ behavior
- [ ] TaskExecutor execution loop
- [ ] RecoveryEngine real recovery
- [x] Memory three-layer design with pluggable vector backend
- [ ] DefectRepair pipeline

### Phase 3 (2-3 weeks)
- [ ] Docker sandbox hardening
- [ ] Secret management
- [ ] Prometheus metrics
- [ ] OpenTelemetry tracing
- [ ] GitHub Actions CI/CD

### Phase 4 (2-3 weeks)
- [ ] Production deployment guide
- [ ] Performance optimization
- [ ] Security audit
- [ ] Documentation completion

---

## 📚 Documentation

- [Reports Archive](./docs/reports/README.md) - Historical phase, completion, and test reports
- [Phase 1 Completion Report](./docs/reports/PHASE1_COMPLETION_REPORT.md) - Detailed Phase 1 summary
- [Phase 1 Quick Reference](./docs/reports/PHASE1_QUICK_REFERENCE.md) - Quick API reference
- [API Documentation](./docs/api.md) - Full API specification (coming in Phase 2)

---

## 🤝 Contributing

This is a prototype project. Contributions are welcome for:
- Bug fixes
- Test improvements
- Documentation
- Performance optimization

---

## 🔭 Observability

The `agentManager.observability` module provides production-oriented monitoring infrastructure (the project overall is still in prototype phase):

- **Structured Logging** — JSON-formatted logs with request/workflow correlation IDs (`X-Request-ID` header propagated automatically)
- **OpenTelemetry Tracing** — Opt-in distributed tracing (set `OTEL_ENABLED=true`); zero overhead when disabled
- **Audit Events** — Security-critical actions (workflow creation, task execution, sandbox denials, recovery escalation, config validation failures) logged under the `audit` namespace
- **Prometheus Metrics** — Task counters, duration histograms, error/repair counters at `/metrics`

### Configuration

| Variable | Default | Description |
|---|---|---|
| `LOG_LEVEL` | `INFO` | Python log level |
| `LOG_JSON` | `true` | JSON output (false = human-readable) |
| `OTEL_TRACING_ENABLED` | `false` | Enable OpenTelemetry tracing |
| `OTEL_SERVICE_NAME` | `agentManager` | OTEL service name |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | `http://localhost:4317` | OTLP gRPC endpoint |
| `AUDIT_ENABLED` | `true` | Emit audit log events |

---

## 📄 License

MIT License - See LICENSE file for details

---

## 🔗 Links

- **GitHub**: https://github.com/Zld1994/agentManager
- **Issues**: https://github.com/Zld1994/agentManager/issues
- **Discussions**: https://github.com/Zld1994/agentManager/discussions

---

**Last Updated**: 2026-05-24  
**Status**: Phase 1 Complete, Phase 2 In Progress  
**Test Coverage**: 66/66 ✅
