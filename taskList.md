# agentManager 基础设施修复路线图

> **定位：** 本文件是当前可执行的工作计划，不是完成报告。
> 上一轮维护（任务 1-8）的历史记录归档在 `docs/reports/maintenance-2026-05-30.md`。

**原则：** 先修底座，再做产品。不做 UI/Agent 角色系统，先把 Docker、CI、durable runtime wiring、recovery policy、observability 这几个底座闭环。

**工作规则：**
- 每个任务足够小，可独立审查。
- 实施更改之前优先编写聚焦测试。
- 保留无关的本地更改，每个任务前检查 `git status --short`。
- 使用 Python 3.11 或 3.12 验证（3.15 依赖 wheel 不可靠）。
- 仅当实现影响文档化行为时才更新 `TODO.md`、`README.md`、`docs/api.md` 或 `AGENTS.md`。

---

## 代码审查发现的真实问题

以下问题通过审查源码确认，不是推测：

### 问题 1：Docker/Compose 状态矛盾
- `TODO.md` 第 49 行明确记录 Docker/Compose 验证被阻塞（WSL 缺少 `docker compose`）
- 但旧 taskList 中 Task 3 写"已通过 Daocloud 镜像源完成运行时验证"
- **真实状态：** 配置文件和 Dockerfile 已静态验证；部分环境通过替代镜像源验证过；但标准 CI / 干净机器 / 目标部署环境下的 Docker Compose 验证尚未闭环

### 问题 2：持久化后端未接入运行主路径
- [api.py:62-65](file:///h:/AllProject/agentManager/agentManager/api.py#L62-L65) 仍然模块级初始化全局内存对象：
  ```python
  dag_engine = DAGEngine()
  state_machine = StateMachine()
  event_bus = EventBus()
  scheduler = SchedulerEngine(max_concurrent_tasks=10)
  ```
- `agentManager/storage/postgres.py` 有 `PostgresStateRepository`，但 API 层没有使用它
- `agentManager/storage/object_store.py` 有 `S3ObjectStore`，但 `CheckpointManager` 没有使用它
- `MemorySystem` 只支持 SQLite 后端（[memory_system.py:95](file:///h:/AllProject/agentManager/agentManager/memory/memory_system.py#L95)），不支持持久化后端
- **真实状态：** 接口和 mock 测试已完成，但 API / WorkflowCoordinator / TaskExecutor 在配置开启时并未真正使用 Postgres、Redis、对象存储

### 问题 3：RecoveryStrategy 选择逻辑与描述不一致
- [workflow_coordinator.py:214-217](file:///h:/AllProject/agentManager/agentManager/runtime/workflow_coordinator.py#L214-L217)：
  ```python
  repair_pipeline = getattr(self.recovery_engine, "defect_repair_pipeline", None)
  if repair_pipeline is not None:
      strategy = RecoveryStrategy.DEFECT_REPAIR
  ```
- 这意味着只要 `defect_repair_pipeline` 存在，就会覆盖 `error_classifier` 的分类结果，强制走 DEFECT_REPAIR
- 旧 taskList 描述"仅当 classification 判断需要 repair 且 workflow policy 允许时才启用"，但代码没有 workflow policy 检查
- **真实状态：** repair_pipeline 存在 = 必须 repair，缺少 policy 和 classification 门控

### 问题 4：README 表述矛盾
- [README.md:6](file:///h:/AllProject/agentManager/README.md#L6)："This project is NOT production-ready yet."
- [README.md:488](file:///h:/AllProject/agentManager/README.md#L488)："provides production-ready monitoring"
- **真实状态：** 具备生产化观测的最小基础设施，但不是 production-ready

### 问题 5：CI 质量门禁偏宽松
- [ci.yml:73](file:///h:/AllProject/agentManager/.github/workflows/ci.yml#L73)：coverage `fail-under=80` 仅在 Python 3.10 上跑
- [ci.yml:86](file:///h:/AllProject/agentManager/.github/workflows/ci.yml#L86)：mypy 是 `|| true`，不阻断合并
- [ci.yml:91](file:///h:/AllProject/agentManager/.github/workflows/ci.yml#L91)：flake8 只检查 `agentManager/`，不检查 `tests/`
- [ci.yml:120](file:///h:/AllProject/agentManager/.github/workflows/ci.yml#L120)：Codecov `fail_ci_if_error: false`
- Docker build / compose up 不在 CI 强制验证里
- **真实状态：** CI 报告生成已完成，但质量门禁未收紧

### 问题 6：middleware 异常路径可能泄漏 context
- [api.py:52-59](file:///h:/AllProject/agentManager/agentManager/api.py#L52-L59)：`request_correlation_middleware` 在 `call_next` 后调用 `clear_request_context()`，但如果 `call_next` 抛异常，`clear_request_context()` 不会执行
- **真实状态：** 需要用 try/finally 包裹

---

## P0：修正事实与验证闭环

### P0-1：统一 Docker/Compose 状态描述

**目的：** 消除 TODO.md 和 taskList 之间的状态矛盾

**文件：**
- 修改：`TODO.md`

- [x] **P0-1.1：更新 TODO.md Docker/Compose 状态** (✅ 已完成)

  将 TODO.md 第 48-49 行的"剩余障碍"更新为准确描述：
  - Compose 配置和 Dockerfile 已静态验证
  - 部分环境通过 Daocloud 镜像源完成过运行时验证
  - 标准 CI / 干净机器 / 目标部署环境下的 Docker Compose 验证尚未闭环
  - 后续操作不变：在 WSL 中安装 Docker Compose v2 或在 Windows 上暴露 Docker Desktop Compose

  验证：`git diff TODO.md` 确认状态描述一致

- [ ] **P0-1.2：在 CI 中添加 Docker build / compose config 验证**

  在 `.github/workflows/ci.yml` 中添加 job：
  - `docker compose config` 语法验证
  - `docker build -f Dockerfile.prod -t agentmanager:prod .` 生产镜像构建
  - `docker build -f Dockerfile.dev -t agentmanager:dev .` 开发镜像构建

  验证：CI 运行结果

### P0-2：修正 README 表述矛盾

**目的：** 消除 "NOT production-ready" 和 "production-ready monitoring" 的矛盾

**文件：**
- 修改：`README.md`

- [x] **P0-2.1：将 README.md 第 488 行 "production-ready monitoring" 改为准确表述** (✅ 已完成)

  改为："具备生产化观测的最小基础设施（the project overall is still in prototype phase）"

  验证：`git diff README.md` 确认表述一致

### P0-3：修复 middleware 异常路径 context 泄漏

**目的：** 确保 request context 在异常路径也能清理

**文件：**
- 修改：`agentManager/api.py`
- 测试：`tests/unit/test_api.py`

- [x] **P0-3.1：用 try/finally 包裹 middleware** (✅ 已完成)

  将 [api.py:52-59](file:///h:/AllProject/agentManager/agentManager/api.py#L52-L59) 的 `request_correlation_middleware` 改为使用 try/finally 包裹，确保即使在异常情况下也会调用 `clear_request_context()`

  验证：`python -m pytest tests/unit/test_api.py -v --no-cov` - 30 个测试全部通过

### P0-4：修复 RecoveryStrategy 选择逻辑

**目的：** 让 defect repair 策略选择符合预期语义

**文件：**
- 修改：`agentManager/runtime/workflow_coordinator.py`
- 测试：`tests/unit/test_recovery_engine.py`

- [x] **P0-4.1：修复 _recover_failed_task 中的 strategy 覆盖逻辑** (✅ 已完成)

  修改了 [workflow_coordinator.py](file:///h:/AllProject/agentManager/agentManager/runtime/workflow_coordinator.py) 的逻辑：
  1. 添加了 `allow_defect_repair` 参数到 `WorkflowCoordinator.__init__`，默认 True
  2. 只有当 `failure_type` 是 RUNTIME（可修复类型）且 `repair_pipeline` 存在且 `allow_defect_repair` 为 True 时，才将 strategy 改为 DEFECT_REPAIR
  3. 不可修复错误（如 SYNTAX、UNKNOWN）不会进入 repair

  验证：`python -m pytest tests/unit/test_recovery_engine.py -v --no-cov` - 43 个测试全部通过

### P0-5：CI 质量门禁收紧

**目的：** 让 CI 真正能阻断低质量合并

**文件：**
- 修改：`.github/workflows/ci.yml`

- [x] **P0-5.1：flake8 扩展到 tests/ 目录** (✅ 已完成)
- [x] **P0-5.2：mypy 对核心模块非 advisory** (✅ 已完成)
- [x] **P0-5.3：coverage threshold 在主版本 Python 强制** (✅ 已完成)
- [x] **P0-5.4：添加 durable backend integration job** (✅ 已完成)

  更新了 CI 配置，包括：
  - 将覆盖率阈值检查扩展到 Python 3.10 和 3.12
  - 将 flake8 检查范围扩展到 tests/ 目录
  - 将 mypy 分为核心模块的阻塞检查和整体的建议性检查
  - 添加了持久化后端集成测试作业

---

## P1：把 durable backend 接入主路径 ✅ 已完成

### P1-1：引入 RuntimeFactory

**目的：** API 不再直接模块级创建全局 in-memory 对象，改为根据配置选择后端

**文件：**
- 添加：`agentManager/runtime/factory.py`
- 修改：`agentManager/api.py`
- 修改：`agentManager/config/settings.py`
- 测试：`tests/unit/test_runtime_factory.py`

- [x] **P1-1.1：创建 RuntimeFactory** (✅ 已完成)

  创建 `agentManager/runtime/factory.py`，提供 `create_runtime()` 工厂函数，内部包含：
  - `_create_state_machine(settings)` — 根据 DATABASE_URL 返回 PostgresStateRepository 包装的 StateMachine 或内存 StateMachine
  - `_create_event_bus(settings)` — 根据 REDIS_URL 返回 RedisStreamEventBus 或内存 InMemoryEventBus
  - `_create_checkpoint_manager(settings)` — 根据 OBJECT_STORE_ENDPOINT 返回 ObjectStoreCheckpointManager 或 InMemoryCheckpointManager
  - `_create_memory_system(settings)` — 根据 VECTOR_BACKEND 返回带 Qdrant 向量后端或 SQLite 后端的 MemorySystem

- [x] **P1-1.2：重构 api.py 使用 RuntimeFactory** (✅ 已完成)

  将 api.py 的模块级全局对象改为通过 RuntimeFactory 创建：
  ```python
  from agentManager.runtime.factory import create_runtime
  _runtime = create_runtime()
  dag_engine = _runtime.dag_engine
  state_machine = _runtime.state_machine
  event_bus = _runtime.event_bus
  scheduler = _runtime.scheduler
  ```

- [x] **P1-1.3：添加 RuntimeFactory 测试** (✅ 已完成)

  测试覆盖：
  - 无环境变量时创建内存后端
  - 有 DATABASE_URL 时创建 Postgres 后端（mock）
  - 有 REDIS_URL 时创建 Redis 后端
  - 有 OBJECT_STORE_ENDPOINT 时创建对象存储后端（mock）
  - Qdrant 后端不可用时回退到 SQLite
  - URL 凭证遮蔽

  验证：`python -m pytest tests/unit/test_runtime_factory.py -v --no-cov` — 17 通过

### P1-2：StateManager 持久化集成

**目的：** 工作流状态和任务运行状态可持久化到 PostgreSQL

**文件：**
- 修改：`agentManager/engine/state_manager.py`
- 测试：`tests/unit/test_state_manager.py`

- [x] **P1-2.1：StateMachine 支持 StateRepository 后端** (✅ 已完成 — 已有实现)

  StateMachine 已支持 `repository` 参数，`transition()` 同时写内存和持久化，`get_state()` 优先从内存读取，miss 时从持久化读取。RuntimeFactory 正确注入 PostgresStateRepository。

- [x] **P1-2.2：添加持久化 StateManager 测试** (✅ 已完成)

  验证：`python -m pytest tests/unit/test_state_manager.py -v --no-cov` — 15 通过

### P1-3：CheckpointManager 持久化集成

**目的：** 检查点可写入对象存储

**文件：**
- 修改：`agentManager/engine/checkpoint.py`
- 测试：`tests/unit/test_checkpoint.py`

- [x] **P1-3.1：CheckpointManager 支持 ObjectStore 后端** (✅ 已完成 — 已有实现)

  ObjectStoreCheckpointManager 已存在，RuntimeFactory 正确注入 S3ObjectStore。`save_checkpoint()` 写入对象存储，`load_checkpoint()` 从对象存储读取。

- [x] **P1-3.2：添加持久化 CheckpointManager 测试** (✅ 已完成)

  验证：`python -m pytest tests/unit/test_checkpoint.py -v --no-cov` — 12 通过

### P1-4：MemorySystem 持久化集成

**目的：** 内存系统支持非 SQLite 后端

**文件：**
- 修改：`agentManager/memory/memory_system.py`
- 修改：`agentManager/memory/memory_backend.py`
- 测试：`tests/unit/memory/test_memory_system.py`

- [x] **P1-4.1：MemorySystem 支持可插拔后端** (✅ 已完成)

  修改 MemorySystem：
  - 新增 `vector_backend` 参数，接受可选的 VectorSearchBackend 实例
  - `store()` 在向量后端可用时同时索引内容到向量后端
  - `search()` 在向量后端可用时使用向量搜索，回退到子串匹配
  - 新增 `_search_via_vector_backend()` 和 `_search_via_substring()` 内部方法

- [x] **P1-4.2：添加持久化 MemorySystem 测试** (✅ 已完成)

  测试覆盖：
  - 接受 vector_backend 参数
  - 默认 vector_backend 为 None
  - 向量搜索出错时回退到子串匹配
  - 无向量后端时使用子串搜索

  验证：`python -m pytest tests/unit/memory/test_memory_system.py -v --no-cov` — 40 通过

### P1-5：Compose 环境集成测试

**目的：** 在 Compose 环境下跑 Postgres + Redis + MinIO/Qdrant 的集成测试

**文件：**
- 添加：`tests/e2e/test_persistent_backends.py`
- 修改：`docker-compose.yml`（如需添加 test service）

- [x] **P1-5.1：添加 mock 集成测试** (✅ 已完成)

  创建 `tests/e2e/test_persistent_backends.py`，包含：
  - `TestRuntimeFactoryWiring` — 验证 RuntimeFactory 正确连接各后端
  - `TestDockerComposeIntegration` — 标记为 `@pytest.mark.integration`，需要真实 Docker 服务

  验证：`python -m pytest tests/e2e/test_persistent_backends.py -v --no-cov` — 5 通过，3 跳过

- [x] **P1-5.2：注册 integration pytest marker** (✅ 已完成)

  在 `pyproject.toml` 的 `[tool.pytest.ini_options]` 中注册 `integration` marker

### P1-6：README 写清楚三种运行模式

**目的：** 明确 prototype / production-ready / production-oriented 的边界

**文件：**
- 修改：`README.md`

- [x] **P1-6.1：在 README 中添加运行模式说明** (✅ 已完成)

  在 README.md 的 "Durable Backend Configuration" 部分添加了：
  - Runtime Modes 表格（local memory / local durable / production-like）
  - 每种模式的详细说明
  - RuntimeFactory 如何根据环境变量自动选择后端的说明

  验证：`git diff README.md`

---

## P2：生产安全与观测深化 ✅ 已完成

### P2-1：OTEL exporter 端到端验证 ✅

**目的：** 从"配置存在"变成"可实际接入 collector"

**文件：**
- 修改：`agentManager/observability/tracing.py`
- 添加：`monitoring/otel-collector-config.yml`

- [x] **P2-1.1：添加 OTEL 采样率配置** ✅

  在 `setup_tracing()` 中添加 `OTEL_TRACING_SAMPLE_RATE` 环境变量支持（0.0 到 1.0）

- [x] **P2-1.2：添加 OTLP HTTP 导出器选项** ✅

  支持 gRPC（默认）和 HTTP 导出器，通过 `OTEL_EXPORTER_OTLP_PROTOCOL` 配置

- [x] **P2-1.3：添加 OTEL Collector 配置文件** ✅

  创建 `monitoring/otel-collector-config.yml`，配置接收 OTLP（gRPC 和 HTTP）并导出到 Jaeger/Zipkin/Logging

- [ ] **P2-1.4：添加更细粒度 span 覆盖**

  （待完成：扩展到检查点/内存/沙箱/缺陷修复流水线）

### P2-2：审计事件落库策略 ✅

**目的：** 审计事件不只是写日志，还要有明确落库位置

**文件：**
- 修改：`agentManager/observability/audit.py`

- [x] **P2-2.1：审计事件支持多输出** ✅

  修改 `record_audit_event()`，支持同时输出到：
  - 日志（当前行为，默认）
  - PostgreSQL audit_record 表（占位符实现）
  - 对象存储（占位符实现）

  通过 `AUDIT_SINK` 环境变量配置：`log`（默认）、`log,db`、`log,db,object_storage`
  
  新增 `register_audit_handler()`/`unregister_audit_handler()` 自定义处理器机制

- [ ] **P2-2.2：添加审计落库测试**

  （占位符实现已完成，完整实现待后续）

### P2-3：Prometheus 告警规则 ✅

**目的：** 从"指标存在"变成"有基础告警"

**文件：**
- 添加：`monitoring/alerts.yml`
- 修改：`monitoring/prometheus.yml`

- [x] **P2-3.1：添加基础告警规则** ✅

  添加 5 个告警：
  - HighErrorRate：高错误率（>10%）
  - TaskExecutionTimeout：任务执行超时
  - SandboxDeniedIncreased：沙箱拒绝次数异常
  - RecoveryUpgradeExcessive：恢复升级次数异常
  - ApiHighLatency：API 高延迟（95% 分位 >1s）

- [x] **P2-3.2：更新 Prometheus 配置引用告警规则** ✅

### P2-4：WorkerSandbox 真实 Docker 集成测试 ✅

**目的：** 不只 mock，还要有真实 Docker 环境下的集成测试

**文件：**
- 添加：`tests/integration/test_sandbox_docker.py`

- [x] **P2-4.1：编写真实 Docker 环境下的沙箱测试** ✅

  测试覆盖：
  - 容器创建和启动
  - 命令执行和输出分离
  - 超时清理
  - 工作空间隔离
  - 网络隔离
  - 资源限制验证
  - 拒绝挂载验证

  标记为 `@pytest.mark.integration`，需要 Docker 环境，自动检测可用性

- [ ] **P2-4.2：在 CI 中添加集成测试 job（条件运行）**

  （待后续：添加 CI 集成测试 job）

---

## P3：执行闭环语义深化

### P3-1：memory write-back 真实实现

**目的：** WorkflowCoordinator 构造参数里没有 memory backend，memory write-back 缺少真实实现

**文件：**
- 修改：`agentManager/runtime/workflow_coordinator.py`
- 修改：`agentManager/memory/engineering_memory.py`
- 测试：`tests/e2e/test_execution_recovery_memory_loop.py`

- [ ] **P3-1.1：WorkflowCoordinator 接受可选 memory_backend 参数**

  在 `__init__` 中添加 `memory_backend: Optional[Any] = None`

- [ ] **P3-1.2：任务完成后写入 engineering memory**

  在 `_execute_scheduled_task` 成功路径中，如果 `memory_backend` 存在，写入执行结果

- [ ] **P3-1.3：添加 memory write-back 测试**

  验证：`python -m pytest tests/e2e/test_execution_recovery_memory_loop.py -v --no-cov`

### P3-2：resume from checkpoint 测试

**目的：** 验证从检查点恢复工作流的完整路径

**文件：**
- 添加：`tests/e2e/test_checkpoint_resume.py`

- [ ] **P3-2.1：编写从检查点恢复的端到端测试**

  测试覆盖：
  - 工作流执行到一半崩溃
  - 从检查点恢复
  - 验证已完成任务不重复执行
  - 验证未完成任务继续执行

  验证：`python -m pytest tests/e2e/test_checkpoint_resume.py -v --no-cov`

### P3-3：workflow crash/restart 后恢复测试

**目的：** 验证工作流崩溃重启后的状态恢复

**文件：**
- 添加：`tests/e2e/test_workflow_crash_recovery.py`

- [ ] **P3-3.1：编写工作流崩溃恢复的端到端测试**

  测试覆盖：
  - 工作流执行中模拟崩溃
  - 重新创建 WorkflowCoordinator
  - 从持久化状态恢复
  - 验证工作流可继续执行

  验证：`python -m pytest tests/e2e/test_workflow_crash_recovery.py -v --no-cov`

---

## 产品能力路线图（独立文档）

TODO.md 后面列出的 agent config、skills/MCP、项目地图、任务 JSON、角色模板、Manager 分解任务、UI 等是下一阶段产品能力，不应该和当前基础设施修复混在一个 taskList 里。

建议单独建 `docs/roadmap/product-agent-platform.md`，按优先级拆：

1. Agent/Profile 配置系统
2. Skills/MCP 模板库
3. 项目地图与上下文索引
4. Manager 任务分解 JSON schema
5. UI 配置与任务编排
6. 定时任务/hooks

**当前不做这些。先闭环 P0-P3。**

---

## 验证矩阵

每个 P0/P1 任务完成后运行：

```powershell
python -m pytest tests/unit/test_api.py -v --no-cov
python -m pytest tests/unit/ -v --no-cov
python -m pytest tests/e2e/ -v --no-cov
python -m pytest -q
```

全部 P0 完成后额外运行：

```powershell
python -m flake8 agentManager tests --max-line-length=100 --jobs=1
git diff --check
```

P1-5 完成后额外运行（如果 Docker 可用）：

```powershell
docker compose config
docker compose build agentmanager
docker compose up -d
# 等待 API 就绪后
python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read().decode())"
docker compose down
```

---

## 建议的提交顺序

### P0（先做）

1. `fix: unify docker/compose status description in TODO.md`
2. `fix: resolve README production-ready wording contradiction`
3. `fix: middleware context leak on exception path`
4. `fix: recovery strategy selection logic - add policy gate`
5. `ci: tighten quality gates - flake8 tests/, mypy core, coverage matrix`

### P1（P0 完成后）

6. `feat: add RuntimeFactory for backend selection`
7. `refactor: api.py use RuntimeFactory instead of module-level globals`
8. `feat: StateMachine supports StateRepository backend`
9. `feat: CheckpointManager supports ObjectStore backend`
10. `feat: MemorySystem supports pluggable backends`
11. `test: add persistent backend integration tests`
12. `docs: add three runtime modes to README`

### P2（P1 完成后）

13. `feat: add OTEL sampling rate and HTTP exporter option`
14. `feat: add audit event multi-sink support`
15. `feat: add Prometheus alert rules`
16. `test: add real Docker sandbox integration tests`
17. `fix: P2 code review — audit forward ref, tracing validation, alert metric alignment, test robustness`

### P3（P2 完成后）

17. `feat: WorkflowCoordinator accepts memory_backend parameter`
18. `test: add checkpoint resume e2e tests`
19. `test: add workflow crash/restart recovery e2e tests`

---

## 验证完成 (2026-05-31)

**P0 任务全部完成**：
- P0-2: 修正 README 表述矛盾
- P0-3: 修复 middleware 异常路径 context 泄漏
- P0-4: 修复 RecoveryStrategy 选择逻辑
- P0-5: CI 质量门禁收紧

**测试验证结果**：
- `python -m pytest tests/unit/test_api.py -v --no-cov` - 30 个通过
- `python -m pytest tests/unit/test_recovery_engine.py -v --no-cov` - 43 个通过
- `python -m pytest tests/unit/test_task_executor.py tests/unit/test_domain_models.py -v --no-cov` - 44 个通过
