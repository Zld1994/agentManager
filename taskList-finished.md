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

  **审查修正：** 非数字回退 1.0，超出 [0,1] 钳位并输出 WARNING

- [x] **P2-1.2：添加 OTLP HTTP 导出器选项** ✅

  支持 gRPC（默认）和 HTTP 导出器，通过 `OTEL_EXPORTER_OTLP_PROTOCOL` 配置

  **审查修正：** protocol 添加合法性校验，无效值回退 gRPC 并输出 WARNING；HTTP 导出器移除 `insecure=True`（仅 gRPC 支持）

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
  - PostgreSQL audit_record 表（占位符实现，输出 WARNING 提醒未实际落库）
  - 对象存储（占位符实现，输出 WARNING 提醒未实际归档）

  通过 `AUDIT_SINK` 环境变量配置：`log`（默认）、`log,db`、`log,db,object_storage`
  
  新增 `register_audit_handler()`/`unregister_audit_handler()` 自定义处理器机制

  **审查修正：**
  - `_get_audit_sinks()` 添加 `_VALID_SINKS` 校验，无效 sink 名输出 WARNING 并被忽略；全部无效时回退 `log`
  - `configure_audit_sinks()` 改为进程内 `_override_sinks` 变量（优先级高于环境变量），不再写 `os.environ`，线程安全
  - 新增 `reset_audit_sinks()` 清除覆盖恢复默认
  - `_custom_audit_handlers` 从 `Set` 改为 `List`（lambda 不可哈希）

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
  - TaskExecutionTimeout：任务执行超过 60s
  - SandboxDeniedIncreased：沙箱拒绝次数异常
  - RecoveryUpgradeExcessive：恢复升级次数异常
  - ApiHighLatency：API 高延迟（95% 分位 >1s）

  **审查修正：**
  - 指标名对齐 api.py 中的实际 Prometheus Counter 名称，添加指标名注释
  - TaskExecutionTimeout 表达式从 `bucket{le="60"}` 改为 `count - bucket{le="60"}`，语义从"60s 内完成的任务"修正为"超过 60s 的任务"
  - TaskExecutionTimeout `for` 从 1m 改为 2m，减少瞬时告警噪音

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

  **审查修正：**
  - `docker_available()` 先用 `shutil.which("docker")` 快速检测
  - 网络隔离测试改用 `python3 -c "import socket; ..."` 替代 `ping`（slim 镜像无 ping）
  - 容器状态断言精确化为 `== "running"`，添加 `container.reload()`
  - `test_denied_mount` 改用 `with` 语句防止容器泄漏

- [ ] **P2-4.2：在 CI 中添加集成测试 job（条件运行）**

  （待后续：添加 CI 集成测试 job）

---

## P3：执行闭环语义深化 ✅ 已完成

### P3-1：memory write-back 真实实现 ✅

**目的：** WorkflowCoordinator 构造参数里没有 memory backend，memory write-back 缺少真实实现

**文件：**
- 修改：`agentManager/runtime/workflow_coordinator.py`
- 修改：`agentManager/runtime/factory.py`
- 测试：`tests/e2e/test_workflow_resume_and_memory.py`

- [x] **P3-1.1：WorkflowCoordinator 接受可选 memory_backend 参数** (✅ 已完成 — 改进方案)

  使用 `Optional[MemoryBackend]` 而非 `Optional[Any]`，类型安全且可维护

- [x] **P3-1.2：任务完成后写入 engineering memory** (✅ 已完成)

  在 `_execute_scheduled_task` 成功路径和恢复成功路径中自动写入 memory，best-effort 语义
  - 新增 `_write_task_result_to_memory()` 方法
  - 新增 `_write_recovery_result_to_memory()` 方法

- [x] **P3-1.3：RuntimeFactory 自动注入 memory_backend** (✅ 已完成 — 新增)

  新增 `_create_engineering_memory()` 工厂函数，Runtime dataclass 新增 `engineering_memory` 字段

- [x] **P3-1.4：添加 memory write-back 测试** (✅ 已完成)

  4 个测试覆盖：任务完成写回、恢复成功写回、无 backend 时不写回、best-effort 容错

  验证：`python -m pytest tests/e2e/test_workflow_resume_and_memory.py -v --no-cov`

### P3-2：resume from checkpoint ✅

**目的：** 验证从检查点恢复工作流的完整路径

**文件：**
- 修改：`agentManager/runtime/workflow_coordinator.py`
- 测试：`tests/e2e/test_workflow_resume_and_memory.py`

- [x] **P3-2.1：实现 resume_workflow 方法** (✅ 已完成 — 改进方案)

  原方案只写测试不添加能力，改为先实现 `resume_workflow()` 方法：
  - 从 checkpoint 恢复已完成任务的状态
  - 跳过已完成任务
  - 继续执行未完成任务
  - 新增 `_restore_completed_tasks_from_checkpoints()` 私有方法

- [x] **P3-2.2：编写从检查点恢复的端到端测试** (✅ 已完成)

  3 个测试覆盖：
  - 已完成任务不重复执行
  - 未完成任务继续执行
  - 无 checkpoint 时正常运行所有任务

  验证：`python -m pytest tests/e2e/test_workflow_resume_and_memory.py -v --no-cov`

### P3-3：workflow crash/restart 后恢复 ✅

**目的：** 验证工作流崩溃重启后的状态恢复

**文件：**
- 测试：`tests/e2e/test_workflow_resume_and_memory.py`

- [x] **P3-3.1：编写工作流崩溃恢复的端到端测试** (✅ 已完成 — 改进方案)

  原方案独立测试文件，改为统一到 `test_workflow_resume_and_memory.py`：
  - 崩溃后从新 StateMachine + 持久化 checkpoint 恢复
  - 运行中任务崩溃后重新执行
  - 恢复时同时写入 memory backend

  3 个测试覆盖：
  - 从持久化状态恢复（已完成任务不重复执行）
  - 运行中任务崩溃后重新执行
  - 崩溃恢复 + memory write-back

  验证：`python -m pytest tests/e2e/test_workflow_resume_and_memory.py -v --no-cov`

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
18. `fix: P2 review round 2 — sink validation, in-process override, alert semantics, test precision`

### P3（P2 完成后）

17. `feat: WorkflowCoordinator accepts MemoryBackend parameter with auto write-back`
18. `feat: RuntimeFactory injects EngineeringMemory for workflow write-back`
19. `feat: add resume_workflow method to WorkflowCoordinator`
20. `test: add unified P3 e2e tests for memory write-back, checkpoint resume, and crash recovery`
21. `fix: P3 code review — remove redundant import, precise return type, extract shared write_record, resume writes memory, remove getattr, fix test assertion`

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

**P3 任务全部完成 (2026-06-01)**：
- P3-1: Memory write-back 真实实现（类型安全 MemoryBackend + 自动 write-back + RuntimeFactory 注入）
- P3-2: Resume from checkpoint（实现 resume_workflow 方法 + 端到端测试）
- P3-3: Workflow crash/restart 恢复（统一测试覆盖崩溃恢复场景）

**P3 测试验证结果**：
- `python -m pytest tests/e2e/test_workflow_resume_and_memory.py -v --no-cov` - 10 个通过
- `python -m pytest -q --no-cov` - 652 通过，12 跳过

**P3 代码审查修正 (2026-06-01)**:
- #1: 删除 `_create_engineering_memory` 函数体内冗余 import
- #2: `_create_engineering_memory` 返回类型 `-> Any` 改为 `-> Optional[EngineeringMemory]`
- #3: `_create_engineering_memory` 忽略 settings 参数 — docstring 明确说明行为
- #4: 提取 `_write_record_to_memory()` 消除代码重复，新增 `key_prefix` 参数修复前缀提取 bug
- #5: `resume_workflow` 恢复已完成任务时写入 memory
- #6: 去掉 `_restore_completed_tasks_from_checkpoints` 中多余 `getattr`
- #7: `test_api.py` 断言改为 `"OK" in result.stdout.strip().splitlines()`

**最终验证 (2026-06-01)**:
- `python -m pytest -q --no-cov` - 652 通过，12 跳过

---

# agentManager M4 任务清单归档 — 2026-06-02

> 来源：	askList.md
> 状态：所有复核后的 checkbox 项已完成，归档后 	askList.md 仅保留未完成内容。

# agentManager M4 任务清单 — 专家团 v5

> **生成时间：** 2026-06-01
> **版本历史：** v1 初始评审 → v2 方案收敛 → v3 M4-C.5.1 闭环 + stderr 修复 → v4 补齐审计工厂注入 + 性能基准扩展 + 防篡改 → v5 校准 M4-E.7 和 CI sandbox 状态
> **来源：** 专家团评审（独立评审 → 交叉质询 → 方案收敛）
> **基线：** 652 测试通过 · P0/P1/P3 基础框架已完成
> **核心原则：** 代码实现不阻塞于环境；验证阶段才需要 Docker。每个任务足够小，可独立验证和提交。

---

## 架构约定

本任务清单遵循以下约束：

| 约束 | 说明 |
|------|------|
| **存储抽象复用** | 审计 Sink 通过 `StateRepository.append_audit_record()` 和 `ObjectStore.put_bytes()` 写数据，**不**在 observability 层直接写 SQL / boto3 |
| **工厂注入** | 配置通过 `configure_audit_sinks()` 注入，连接池复用 RuntimeFactory 创建的后端连接 |
| **数据库 Schema** | 已有 `postgres.py:initialize_schema()` 内联建表（`audit_record` 已存在），**不**引入独立迁移框架；如需新增列用 `DO $$ ... IF NOT EXISTS ... END $$` 包裹：`DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='audit_record' AND column_name='col') THEN ALTER TABLE audit_record ADD COLUMN col TEXT; END IF; END $$` |
| **OTEL 语义约定** | Span 属性名使用点号分隔（`workflow.id`），遵循 OTel 语义约定；已有 `tracing.py` 已遵循此规范 |
| **审计降级策略** | db sink 失败 → 不丢事件（log sink 先写），但需增加失败计数器 |
| **OTEL 降级** | `tracing.py` 已有完整 no-op 机制，Collector 不可用时不影响业务 |

---

## 工作流概览

```
M4-A 基础设施就绪         ≠ 阻断任何开发
M4-B TODO/文档修正        可立即执行
M4-C OTEL 细粒度 Span     代码不依赖 Docker · E2E 验证依赖 M4-A
M4-D 沙箱安全验证         代码不依赖 Docker · 集成测试依赖 M4-A
M4-E 审计落库             PG 走 CI container · 迁移检查依赖现有 Schema
M4-F 配置/文档/指标同步   依赖 M4-C、M4-E 输出
```

---

## M4-A：基础设施就绪 🔧（不阻断其他工作流）

> **目标：** Docker Compose 文档化 + CI 修复 + `/health` 增强 + OTEL Collector Compose 集成
> **阻断：** 不阻断任何开发工作流。M4-C/M4-D 代码实现可与 M4-A 并行。

### M4-A.1 — CI 基准修复

- [x] **M4-A.1.1** 验证并修复 CI `REDIS_URL` 配置
  - 文件：`.github/workflows/ci.yml` 第 66、80、104 行
  - 验证：读取三处当前值，如为 `redis://localhost:***@localhost:5432/agentmanager_test`（密码占位符 + PostgreSQL 端口）则修复为 `redis://localhost:6379/0`
  - 如已为正确值，跳过此任务（确认无需修改即可通过 M4-A.1.2）

- [x] **M4-A.1.2** 验证 CI Redis 连接正常
  - 验证：Redis service container 可达
  - **✅ 实测（2026-06-02）：** GitHub Actions run `26769717318` 中 `test (3.10/3.11/3.12)` 的 `Initialize containers` 与 `Run unit tests with coverage` 步骤均成功，`REDIS_URL=redis://localhost:6379` 和 Postgres service container 可用于测试步骤；该 run 整体仍因覆盖率阈值 / mypy core 失败而失败。

### M4-A.2 — Docker Compose 文档化验证

- [x] **M4-A.2.1** `docker compose config` — 验证 compose 文件语法
  - 工作目录：`agentManager/`
  - 验证标准：退出码 0，无 ERROR

- [x] **M4-A.2.2** `docker compose build agentmanager` — 验证开发镜像构建
  - 验证标准：构建成功，镜像大小 < 600MB

  **✅ 实测（2026-06-01）：** 构建成功，~150s（含 `[dev,otel]` 依赖），镜像已存在

- [x] **M4-A.2.3** `docker compose up -d` — 启动全部 7 个服务
  - 验证标准：`docker compose ps` 显示所有服务 `healthy` 或 `running`

  **✅ 实测（2026-06-01）：**
  | 服务 | 状态 | 说明 |
  |------|------|------|
  | agentmanager-api | healthy | OTEL 已上报，6 种 span 类型 |
  | postgres | healthy | |
  | redis | healthy | |
  | qdrant | healthy | |
  | minio | healthy | |
  | otel-collector | running | OTLP gRPC 4317 / HTTP 4318 |
  | jaeger | running | UI http://localhost:16686 |

  `/health` 返回 `{"status": "ok", "dependencies": {"redis": "ok"}}`
  Jaeger 链路：100 条，涵盖 `GET /health`、`POST /tasks`、`scheduler.add_task`

- [x] **M4-A.2.4** `docker build -f Dockerfile.prod -t agentmanager:prod .` — 生产镜像构建
  - 验证标准：构建成功，镜像大小 < 500MB
  - **✅ 实测（2026-06-02）：** 通过 WSL Docker 执行 `docker build -f Dockerfile.prod -t agentmanager:prod .` 成功；`docker image inspect agentmanager:prod --format '{{.Size}}'` 返回 `117826839` bytes（约 112.4 MiB），低于 500MB。

- [x] **M4-A.2.5** `docker compose down` — 干净关闭
  - 验证标准：退出码 0，`docker ps` 和 `docker compose ps` 无残留容器

  **✅ 实测（2026-06-01）：** 退出码 0，7 容器 + 1 网络全部清理

- [x] **M4-A.2.6** 记录验证结果到 `docs/reports/docker-compose-verification-2026-06-01.md`

### M4-A.3 — `/health` 端点增强

- [x] **M4-A.3.1** 实现依赖连通性检查
  - 文件：`agentManager/api.py`
  - 逻辑：当 `DATABASE_URL` 配置时，尝试 `SELECT 1`；当 `REDIS_URL` 配置时，尝试 `PING`
  - 返回格式：`{"status": "ok|degraded|unhealthy", "dependencies": {"postgres": "ok|degraded", "redis": "ok|degraded"}}`
  - **非 strict 模式**（默认）：依赖不可用时仍返回 HTTP 200，`status` 标记为 `"degraded"`
  - **strict 模式**（`?strict=true`）：依赖不可用时返回 HTTP 503，`status` 标记为 `"unhealthy"`
  - 负载均衡器可通过 `strict=true` 检查判断是否将流量路由到该实例
  - 只检查**必需的**依赖（由环境变量是否配置决定），不检查 OTEL Collector / MinIO

### M4-A.4 — OTEL Collector Compose 集成

- [x] **M4-A.4.1** 在 `docker-compose.yml` 中添加 `otel-collector` 和 `jaeger` 服务
  - otel-collector：加载 `monitoring/otel-collector-config.yml`，暴露 OTLP gRPC (4317) 和 HTTP (4318)
  - jaeger：暴露 UI 端口 16686
  - 验证：`docker compose up -d` 后 Jaeger UI 可访问

### M4-A.5 — CI Docker 验证 Job

- [x] **M4-A.5.1** 在 `.github/workflows/ci.yml` 添加 `docker-verify` job
  - 内容：`docker compose config` + `docker build -f Dockerfile.prod` + `docker build -f Dockerfile.dev`
  - 条件：仅在 `ubuntu-latest` runner 上运行

---

## M4-B：TODO/文档修正 📝（可立即执行）

> **目标：** 路线图标记如实反映完成状态，Obsidian 审查项映射到具体 task
> **依赖：** 无

- [x] **M4-B.1** 修正 TODO.md 路线图标记
  - 当前：#4 "生产安全与观测" 标记 ✅ 但 P2-1.4/P2-2.2/P2-4.2 未完成
  - 修改：`✅ 基础框架 / ⏳ 细粒度 span + 审计落库待完成`
  - 验证：`git diff TODO.md`

- [x] **M4-B.2** 将 Obsidian 审查待修复项映射到 task 编号
  - 第 56 行（Docker Compose 全流程）→ M4-A.2
  - 第 57 行（CI 支持的测试状态）→ M4-A.5
  - 第 58 行（WorkerSandbox 强化）→ M4-D
  - 第 59 行（审计事件落库）→ M4-E
  - 第 60 行（OTEL 细粒度 span）→ M4-C
  - 在每条 Obsidian 审查项后添加 `→ M4-*.x` 映射标注

- [x] **M4-B.3** 更新 Docker/Compose 状态描述
  - 当前第 49-52 行：最后更新 2026-05-31
  - 修改：反映 M4-A.2 验证结果

---

## M4-C：OTEL 细粒度 Span 覆盖 📡（P1）

> **目标：** 从「基础设施已有但零接入」→ 核心路径 8+ 模块有 span
> **前置审计发现：** `trace_workflow` / `trace_task` / `create_span` 全代码库零调用
> **原则：** C1（核心引擎）优先于 C2（外围模块）；代码不依赖 Docker；E2E 验证依赖 M4-A.4

### M4-C.1 — 核心引擎 Span 覆盖（优先）

- [x] **M4-C.1.1** 为 `agentManager/engine/scheduler.py` 添加 span
  - 注入点：`schedule_task()`、`execute_next()`、调度循环入口
  - 属性：`task.id`, `task.type`, `queue.depth`, `scheduler.concurrency`

- [x] **M4-C.1.2** 为 `agentManager/engine/state_manager.py` 添加 span
  - 注入点：`transition()`、`get_state()`
  - 属性：`task.id`, `state.from`, `state.to`, `transition.reason`

- [x] **M4-C.1.3** 为 `agentManager/runtime/task_executor.py` 添加 span
  - 注入点：`execute_task()` 入口
  - 复用已有 `trace_task(task_id, task_type)` context manager
  - 属性：`task.id`, `task.type`, `task.duration_ms`

- [x] **M4-C.1.4** 为 `agentManager/runtime/workflow_coordinator.py` 添加 span
  - 注入点：`execute_workflow()` → 复用已有 `trace_workflow(workflow_id)` context manager
  - 注入点：`_execute_scheduled_task()`、`resume_workflow()`
  - 属性：`workflow.id`, `workflow.task_count`

### M4-C.2 — API 层 OTEL Middleware

- [x] **M4-C.2.1** 添加 FastAPI OTEL instrumentation middleware
  - 文件：`agentManager/api.py`
  - **方案：使用 `opentelemetry-instrumentation-fastapi`**（推荐）
    - 与项目已有 OTEL SDK 集成一致，自动注入请求级 span
    - 在 `setup_tracing()` 中调用 `from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor; FastAPIInstrumentor.instrument_app(app)`
    - span 属性：`http.method`, `http.url`, `http.status_code`, `http.route`（自动注入）
  - 在 `pyproject.toml` 新增 `otel` extra：`opentelemetry-instrumentation-fastapi`
  - 如 `opentelemetry-instrumentation-fastapi` 不可用，降级为自定义 `@app.middleware("http")`（手动设置 span 属性）

### M4-C.3 — 外围模块 Span 覆盖

- [x] **M4-C.3.1** 为 `agentManager/engine/checkpoint.py` 添加 span
  - 注入点：`save_checkpoint()`、`load_checkpoint()`
  - 属性：`workflow.id`, `task.id`, `checkpoint.size_bytes`

- [x] **M4-C.3.2** 为 `agentManager/memory/` 添加 span
  - 注入点：`store()`、`search()`、`retrieve()`
  - 属性：`memory.type`（engineering/episodic/semantic），`result.count`

- [x] **M4-C.3.3** 为 `agentManager/sandbox/worker_sandbox.py` 添加 span
  - 注入点：`create()`、`execute()`、`destroy()`
  - 属性：`sandbox.worker_id`, `sandbox.image`, `sandbox.command`（截断到 100 字符）

- [x] **M4-C.3.4** 为 `agentManager/defect_repair/` 添加 span
  - 注入点：流水线入口、分析阶段、修复阶段、验证阶段
  - 属性：`defect.type`, `repair.strategy`, `files.modified`

### M4-C.4 — 单元测试

- [x] **M4-C.4.1** 编写 span 属性正确性测试
  - 文件：`tests/unit/test_tracing_spans.py`
  - 覆盖：各组件 span 的属性名遵循 OTel 语义约定（点号分隔）
  - 覆盖：no-op 模式下不抛异常、不泄漏 span
  - 验证：`python -m pytest tests/unit/test_tracing_spans.py -v --no-cov`

### M4-C.5 — E2E Span 验证（依赖 M4-A.4）

- [x] **M4-C.5.1** 端到端验证 span 输出
  - 方式：启动 `docker compose up -d`（含 OTEL Collector + Jaeger）
  - 运行一个简单工作流（`POST /workflow → POST /tasks → 执行`）
  - 检查 Jaeger UI（`http://localhost:16686`）中可以看到完整 span 链路
  - 验证标准：至少 5 个不同 span 类型的 trace 可见

  **✅ 已闭环（2026-06-01，commit `2bed02e`）：**

  > **根因修复：** Dockerfile.dev 只装 `[dev]` extra，未装 `[otel]` 包。修复为 `pip install -e ".[dev,otel]"`，重建镜像后重启容器。

  | 指标 | 结果 |
  |------|------|
  | Jaeger 服务 | `agentManager`（opentelemetry-instrumentation-fastapi v0.63b1） |
  | 链路总数 | 10 条 |
  | Span 类型 | `GET /health`, `GET /status`, `GET /tasks/ready`, `POST /tasks`, `scheduler.add_task`, ASGI `http send/receive` |
  | 验证命令 | `curl "http://localhost:16686/api/traces?service=agentManager"` |
  | 关联 commit | `2bed02e` — M4-C.5.1: Enable OTEL tracing E2E + fix stderr test syntax |

  **补充修复：** `api.py` 中 `setup_tracing()` 有两处调用（第 30 行模块加载和第 38 行），合并为单次调用（移到 `setup_logging()` 之后），避免重复初始化日志处理器。

---

## M4-D：沙箱安全验证 🛡️（P1）

> **前置审计发现：** `cap_drop=["ALL"]` 已硬编码在 `worker_sandbox.py:197`。
> 本工作流为**验证已有实现**，非新增功能。

### M4-D.1 — 安全参数验证测试

- [x] **M4-D.1.1** 在 `tests/integration/test_sandbox_docker.py` 中添加安全断言
  - `test_cap_drop_all` — 验证 `HostConfig.CapDrop` 包含 `ALL`
  - `test_readonly_rootfs` — 验证 `HostConfig.ReadonlyRootfs` 为 `true`
  - `test_network_disabled` — 验证 `NetworkSettings.Networks` 为空或 none
  - `test_no_new_privileges` — 验证 SecurityOpt 包含 `no-new-privileges:true`
  - 实现方式：创建容器后 `docker inspect` 检查 JSON 输出

- [x] **M4-D.1.2** 运行 Docker 集成测试验证安全参数
  - 命令：`python -m pytest tests/integration/test_sandbox_docker.py -v --no-cov -m integration`
  - 验证标准：新增 4 个测试全部通过（或标记为 skip 当 Docker 不可用时）
  - **✅ 实测（2026-06-02）：** 本地 PowerShell `.venv312` 运行该命令为 `13 skipped`（本地 shell 无 Docker）；GitHub Actions run `26769717318` 的 `sandbox-integration` job 成功，`Pull sandbox image` 与 `Run Docker sandbox integration tests` 步骤均为 success。

### M4-D.2 — CI 集成测试 Job

- [x] **M4-D.2.1** 评估 CI Docker-in-Docker 可行性
  - 试验 GitHub Actions `ubuntu-latest` 的 Docker 可用性
  - 备选方案 A：使用 runner 自带 Docker socket
  - 备选方案 B：mock 测试（`unittest.mock.patch('docker.from_env')`）验证逻辑
  - 备选方案 C：使用 `testcontainers-python` 替代直接 Docker API 调用

- [x] **M4-D.2.2** 在 `.github/workflows/ci.yml` 添加 `sandbox-integration` job
  - 内容：`pytest tests/integration/test_sandbox_docker.py -v -m integration`
  - 条件：根据 M4-D.2.1 的可行性决定具体条件

---

## M4-E：审计落库 🗄️（P1）

> **前置审计发现：** `audit_record` 表已在 `postgres.py:130-137` 通过 `initialize_schema()` 内联创建。
> 现有 schema：`id BIGSERIAL, action TEXT, entity_id TEXT, payload JSONB, timestamp TIMESTAMPTZ`
> **原则：** 复用 `StateRepository.append_audit_record()` 和 `ObjectStore.put_bytes()`

### M4-E.1 — Schema 对齐检查

- [x] **M4-E.1.1** 定义 `AuditEvent` → `audit_record` 显式映射规则
  - **显式映射**（直接写列）：
    | AuditEvent 字段 | audit_record 列 | 说明 |
    |-----------------|-----------------|------|
    | `timestamp` | `timestamp` | ✅ 直接映射 |
    | `event_type.value` | `action` | 枚举值转字符串 TEXT |
    | `resource` | `entity_id` | 审计资源 ID |
  - **JSONB 字段**（放入 `payload`）：
    | AuditEvent 字段 | payload 中的 key |
    |-----------------|------------------|
    | `actor` | `"actor"` |
    | `outcome` | `"outcome"` |
    | `detail` | `"detail"` |
  - `payload` 列上建 GIN 索引：`CREATE INDEX IF NOT EXISTS idx_audit_payload ON audit_record USING GIN (payload)`
  - `action` 列上建索引：`CREATE INDEX IF NOT EXISTS idx_audit_action ON audit_record (action)`
  - 在 `postgres.py:initialize_schema()` 中添加上述两个索引的 `CREATE INDEX IF NOT EXISTS` 语句
  - 验证：查询 `SELECT action, entity_id, payload->>'actor' FROM audit_record` 可直接拿到关键字段

### M4-E.2 — PostgresAuditSink 实现

- [x] **M4-E.2.1** 实现 `PostgresAuditSink` 类
  - 文件：`agentManager/observability/audit.py`
  - 接受 `StateRepository` 实例（由调用方通过 `configure_audit_sinks` 注入）
  - `write(event)` → 映射 `AuditEvent` → `AuditRecord` → 调用 `repo.append_audit_record()`
  - **不在 audit.py 中直接操作数据库连接**——复用 StateRepository 已有的连接池

### M4-E.3 — ObjectStoreAuditSink 实现

- [x] **M4-E.3.1** 实现 `ObjectStoreAuditSink` 类
  - 文件：`agentManager/observability/audit.py`
  - 接受 `ObjectStore` 实例
  - **当前阶段采用每事件独立文件 + 按小时前缀聚合**：
    - key 格式：`audit/{yyyy-mm-dd}/{hh}/{event_id}.json`
    - 每事件一个文件，无并发写入冲突
    - 查询时通过 key 前缀 `audit/{date}/{hour}/` 批量获取
  - **并发限制说明**：
    - 当前方案**无竞态条件**（每事件独立文件，原子写入）
    - 若未来改用 JSONL 追加模式（GET → 合并 → PUT），多实例部署需加分布式锁，当前阶段不引入此复杂度
  - 降级策略：如 ObjectStore 不可用，事件仍写入 log（已有机制）

### M4-E.4 — 审计事件脱敏

- [x] **M4-E.4.1** 实现审计事件敏感数据脱敏
  - 识别 `AuditEvent.detail` 中的敏感字段（如 `api_key`, `password`, `token`）
  - 脱敏规则：替换为 `***REDACTED***`
  - 配置方式：通过 `AUDIT_REDACT_FIELDS` 环境变量控制
  - 验证：`tests/unit/test_audit_redaction.py`

### M4-E.5 — 降级策略强化

- [x] **M4-E.5.1** 添加审计 Sink 失败计数器
  - 指标：`agentmanager_audit_sink_failures_total{sink="db|object_storage"}`
  - 在 `record_audit_event()` 的 db / object_storage 异常分支中 `inc()`
  - 验证：Prometheus `/metrics` 端点可观测

- [x] **M4-E.5.2** 明确审计写入降级行为文档
  - log sink 始终先写（已实现）
  - db sink 失败 → log fallback + 计数器递增
  - object_storage sink 失败 → 同上
  - **不丢事件**（核心保证）

### M4-E.6 — 测试

- [x] **M4-E.6.1** 编写 PostgresAuditSink 单元测试
  - 文件：`tests/unit/test_audit_sinks.py`
  - mock `StateRepository`，验证 `append_audit_record()` 被正确调用
  - 验证字段映射正确

- [x] **M4-E.6.2** 编写 ObjectStoreAuditSink 单元测试
  - 文件：`tests/unit/test_audit_sinks.py`
  - mock `ObjectStore`，验证按小时聚合 key 格式正确且每事件写入独立文件
  - 验证写入逻辑符合每事件独立文件（非 JSONL 追加）

- [x] **M4-E.6.3** 编写降级策略测试
  - db sink 抛异常时 log sink 不受影响
  - 失败计数器正确递增

- [x] **M4-E.6.4** 移除占位符 WARNING
  - 将 `_write_to_db` 和 `_write_to_object_storage` 从占位符函数改为调用 Sink 类
  - 不再输出 "audit event NOT actually written to DB" WARNING

### M4-E.7 — App Startup 注入

- [x] **M4-E.7.1** 在应用启动时将审计 Sink 注入 RuntimeFactory
  - 文件：`agentManager/api.py`（FastAPI lifespan / startup）
  - 逻辑：根据 `DATABASE_URL` 和 `OBJECT_STORE_*` 环境变量是否存在，创建 `StateRepository` 和 `ObjectStore` 实例，通过 `configure_audit_sinks()` 注入
  - 复用 RuntimeFactory 已有的连接创建模式（`_create_state_machine` / `_create_checkpoint_manager`）
  - 验证：启动应用后 `_get_audit_sinks()` 返回正确值，`/metrics` 包含 `audit_sink_failures` 计数器
  - 状态校准（2026-06-02）：`configure_audit_sinks()` 已存在，但 `agentManager/api.py` 尚未在启动路径注入 repository/object_store。
  - **✅ 已完成（2026-06-02）：** 新增 `configure_runtime_audit_sinks()`，`agentManager/api.py` 启动路径读取 durable backend settings 后注入 audit sink；无 durable env 时保持 log sink，本地测试覆盖 db/object_storage 注入和失败降级。

- [x] **M4-E.7.2** 审计事件防篡改基础
  - 在 `audit_record` 表添加 `content_hash TEXT` 列（可选，DDL 用 `DO $$ ... IF NOT EXISTS ... END $$` 包裹）
  - `PostgresAuditSink.write()` 写入时计算 `hashlib.sha256(json.dumps(payload, sort_keys=True)).hexdigest()` 存入 `content_hash`
  - 验证：读取审计记录时可通过 `content_hash` 校验数据完整性
  - 注意：此为非加密签名，仅防意外篡改；如需防恶意篡改，后续引入 HMAC 密钥签名
  - 状态校准（2026-06-02）：`audit_record` schema 和 `PostgresAuditSink.write()` 尚未实现 `content_hash`。
  - **✅ 已完成（2026-06-02）：** `AuditRecord` 增加 `content_hash`，PostgreSQL schema 通过兼容 DDL 添加 `content_hash TEXT`；`PostgresAuditSink.write()` 对脱敏后的 payload 计算 SHA-256 并写入。

---

## M4-F：配置与文档同步 📋（P2）

> **依赖：** M4-C、M4-E 的输出（新增环境变量和配置项）
> **目标：** 确保配置文件、文档与代码实现一致

### M4-F.1 — 配置文件更新

- [x] **M4-F.1.1** 更新 `.env.example` 新增环境变量
  - `OTEL_TRACING_ENABLED=false`
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`
  - `AUDIT_SINK=log`（默认值）
  - `AUDIT_REDACT_FIELDS=api_key,password,token`

- [x] **M4-F.1.2** 更新 `docker-compose.yml`
  - 新增 OTEL Collector + Jaeger 服务（M4-A.4.1 的输出）
  - 新增 OTEL 相关环境变量到 agentmanager 服务

### M4-F.2 — API 文档更新

- [x] **M4-F.2.1** 更新 `docs/api.md`
  - `/health` 端点新增 `dependencies` 字段说明
  - `/metrics` 端点新增审计失败计数器说明

### M4-F.3 — 性能基准

- [x] **M4-F.3.1** 测量 OTEL span 对关键路径的性能影响
  - 测试对象：高频路径（scheduler, state_manager, task_executor）
  - 比较 OTEL 启用/禁用时的 P50/P99 延迟
  - 预期：开销 < 1ms/span
  - 记录到 `docs/reports/otel-span-performance-benchmark-2026-06-01.md`
  - 状态校准（2026-06-02）：已有 HTTP baseline 报告，但报告明确 `OTEL_TRACING_ENABLED=false`，尚未完成 OTEL 启用/禁用对比。
  - **✅ 实测（2026-06-02）：** 新基准脚本对 scheduler、state_manager、task_executor 的 tracing disabled/enabled 入口做 1000 次本地进程内对比，P99 开销均 < 1ms/span；结果写入报告。

- [x] **M4-F.3.2** 测量审计写入对关键路径的性能影响
  - 测试对象：`record_audit_event()` 在 log / db / object_storage 三种 sink 下的延迟
  - 比较审计启用/禁用时的 P50/P99 延迟
  - 预期：log sink 开销 < 0.1ms/event，db sink < 5ms/event，object_storage sink < 50ms/event
  - 记录到 `docs/reports/audit-write-performance-benchmark-2026-06-01.md`
  - **✅ 实测（2026-06-02）：** 新基准脚本对 disabled/log/db/object_storage 模式各运行 1000 次，log/db/object_storage P99 均低于阈值；db/object_storage 使用 mock 后端隔离外部网络延迟。

---

## M4-G：回退与降级方案（预案，条件触发）

> **不主动执行，作为预案记录。** 各工作流失败时触发对应降级。

| 失败场景 | 降级方案 | 影响 |
|----------|----------|------|
| Docker Compose 无法在 WSL 中启用 | 用 Windows Docker Desktop TCP 暴露 (`tcp://localhost:2375`) 替代 Unix socket | 安全隐患（仅本地开发） |
| Docker Hub 镜像拉取失败 | 配置 Daocloud 镜像加速器 (`docker.m.daocloud.io`) | 文档标注「使用镜像源」 |
| OTEL Collector 不可用 | `tracing.py` 已有完整 no-op 机制，不影响业务 | 丢失 E2E span 验证能力 |
| PostgreSQL 审计写入失败 | log sink 先写 → 计数器递增 → 不丢事件 | 丢失持久化审计记录 |
| ObjectStore 审计写入失败 | 同上 | 丢失归档审计记录 |
| 审计 db sink 持续失败（>N次） | `AUDIT_SINK` 自动降级为 `log` 模式 | 运维需收到告警 |

---

## 验证矩阵

每个工作流完成后运行对应的验证命令：

```bash
# M4-A 完成后
docker compose config
docker compose build agentmanager
docker compose up -d
curl -s http://127.0.0.1:8000/health
docker compose down
# CI 修复验证：检查 GitHub Actions 中 redis 连接正常

# M4-B 完成后
git diff TODO.md

# M4-C 完成后
python -m pytest tests/unit/test_tracing_spans.py -v --no-cov
# E2E：docker compose up -d → 运行工作流 → 检查 Jaeger UI http://localhost:16686

# M4-D 完成后
python -m pytest tests/integration/test_sandbox_docker.py -v --no-cov -m integration

# M4-E 完成后
python -m pytest tests/unit/test_audit_sinks.py -v --no-cov
python -m pytest tests/unit/test_audit_redaction.py -v --no-cov
python -m pytest -q --no-cov  # 回归测试全过

# M4-F 完成后
git diff .env.example docker-compose.yml docs/api.md
```

---

## 建议提交顺序

按依赖关系最小化，可部分并行：

### 第一批：无依赖（可立即开始）
1. `fix: CI REDIS_URL placeholder → real value`（M4-A.1.1）
2. `docs: update TODO.md roadmap status markers`（M4-B.1）
3. `docs: map Obsidian review items to task IDs`（M4-B.2）

### 第二批：代码实现（不依赖 Docker）
4. `feat: add OTEL spans to scheduler + state_manager + task_executor`（M4-C.1）
5. `feat: add FastAPI OTEL instrumentation middleware`（M4-C.2）
6. `feat: add OTEL spans to checkpoint + memory + sandbox + defect_repair`（M4-C.3）
7. `test: add security assertions to sandbox docker integration tests`（M4-D.1.1）
8. `feat: implement PostgresAuditSink (reuses StateRepository)`（M4-E.2.1）
9. `feat: implement ObjectStoreAuditSink with hourly aggregation`（M4-E.3.1）

### 第三批：测试与验证（需要基础设施）
10. `test: add span coverage unit tests`（M4-C.4.1）
11. `test: add audit sink unit tests + degradation tests`（M4-E.6）
12. `feat: add /health dependency check`（M4-A.3.1）
13. `infra: add OTEL Collector + Jaeger to docker-compose.yml`（M4-A.4.1）

### 第四批：CI 与文档（收尾）
14. `ci: add docker-verify job`（M4-A.5.1）
15. `ci: add sandbox-integration job`（M4-D.2.2）
16. `docs: update .env.example + docker-compose.yml + api.md`（M4-F）

---

## 里程碑依赖图

```
M4-A.1.1 (CI 修复)  ← 独立
    │
M4-A (基础设施)      ← 不阻断任何开发
    ├── M4-A.2 (Docker Compose 验证)
    ├── M4-A.3 (/health 增强)
    ├── M4-A.4 (OTEL Collector Compose)
    └── M4-A.5 (CI Docker job)

M4-B (TODO 修正)     ← 独立，可立即执行
    ├── M4-B.1 (路线图标记)
    ├── M4-B.2 (Obsidian 映射)
    └── M4-B.3 (Docker 状态更新) ← 依赖 M4-A.2 结果

M4-C (OTEL Span)     ← 不依赖 Docker
    ├── M4-C.1 (核心引擎)    ← 优先
    ├── M4-C.2 (API middleware)
    ├── M4-C.3 (外围模块)
    ├── M4-C.4 (单元测试)
    └── M4-C.5 (E2E 验证)    ← 依赖 M4-A.4

M4-D (沙箱安全)      ← 不依赖 Docker
    ├── M4-D.1 (安全断言测试)
    └── M4-D.2 (CI job)      ← 依赖 CI 可行性评估

M4-E (审计落库)      ← 不依赖 Docker
    ├── M4-E.1 (Schema 检查)
    ├── M4-E.2 (PostgresAuditSink)
    ├── M4-E.3 (ObjectStoreAuditSink)
    ├── M4-E.4 (脱敏)
    ├── M4-E.5 (降级)
    ├── M4-E.6 (测试)
    └── M4-E.7 (App Startup 注入)

M4-F (配置同步)      ← 依赖 M4-C、M4-E 输出
    ├── M4-F.1 (配置文件)
    ├── M4-F.2 (API 文档)
    └── M4-F.3 (性能基准)
```

---

> **下一步：** M4 剩余开发与验证项已闭环。当前仍需另行处理的是 CI run `26769717318` 的整体失败：Python 3.10/3.12 覆盖率阈值失败，以及 Python 3.11 `mypy agentManager/runtime/ agentManager/storage/ agentManager/config/ --ignore-missing-imports` 失败；这不属于本清单剩余勾选项的功能实现缺口。
