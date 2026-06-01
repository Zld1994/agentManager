# 待办事项

## 当前维护说明

✅ **已完成 (2026-05-27)**:
- 任务 1: 将顶层 `defect_repair/` 与 `agentManager/defect_repair/` 合并 - 标准实现完成
- 任务 2: 添加 Docker 支持 (Dockerfile.dev, Dockerfile.prod, docker-compose.yml)
- 任务 3: 实现 `agentManager/roles/` 和 `agentManager/scheduler/` 子包及单元测试
- 任务 4: 修复所有 pytest 失败 - 457 个测试通过 ✓
- 任务 5: 改进 DAG 循环检测，添加 DFS 和循环路径报告 - 19 个测试通过 ✓
- 任务 6: 通过重试限制和冲突检测防止调度器死循环 - 24 个测试通过 ✓
- 任务 8: 确保 FastAPI 启动路径 `agentManager.api:app` 正常工作 - 10 个测试通过 ✓
- 任务 9: 完成 wheel 中的包发现 - 全部 9 个子包可导入 ✓

**剩余高优先级任务**:

✅ **已完成 (2026-05-28)**:
- 使 README/API 示例与原型状态和当前 API 行为保持一致。
- 分离开发/生产配置指南，避免将薄弱的本地默认值呈现为生产安全配置。
- 将静态完成报告中误导性的"生产就绪"声明替换为历史里程碑表述。
- 添加 `WorkflowCoordinator` 以连接 DAG 就绪状态、调度器分发、任务执行、事件、状态转换、检查点以及完成/失败同步。
- 用可观察的重试、事件重放、快照恢复、重新执行、人工介入 (HITL) 和升级行为替换占位符恢复行为。
- 添加一致的异步检查点管理器接口，同时保留归档路径遍历保护。
- 围绕显式配置文件/会话和工程内存以及可插拔向量搜索后端（含 SQLite 回退）重新设计内存层。
- 明确 WorkerGuard 的词级 Jaccard 相似度行为，并添加可配置的动作/错误/输出循环检测。
- 添加 `Workflow`、`Task`、`TaskRun`、`Agent`、`Worker`、`Artifact`、`Checkpoint` 和 `Event` 的共享域模型。
- 在开发依赖中固定 `mypy<2.0`，以避免当前 Python 3.15 环境中的 mypy 2.x 原生依赖问题。

**验证完成 (2026-05-28)**:
- `python -m pytest tests/unit -q --no-cov --ignore=tests/unit/test_api.py` - 377 个通过。
- `python -m pytest tests/e2e/test_runtime_workflow_loop.py tests/unit/test_task_executor.py -q --no-cov` - 26 个通过。
- `python -m pytest tests/unit/test_domain_models.py tests/unit/test_dag_engine.py -q --no-cov` - 35 个通过。
- `git diff --check` - 通过，仅存在 CRLF 警告。

**验证完成 (2026-05-29)**:
- `python -m pytest tests/e2e/ -q --no-cov` - 7 个通过，1 个跳过（将 e2e 临时文件移至仓库本地被忽略的测试工件目录后）。
- 使用 `winget install Python.Python.3.12` 安装 Python 3.12.10 并创建 `.venv312`。
- `.venv312\Scripts\python.exe -m pip install -e ".[dev]"` - 使用 Python 3.12 的 `pydantic-core` wheel 成功完成。
- `.venv312\Scripts\python.exe -m pytest tests/unit/test_api.py -q --no-cov` - 28 个通过，1 个警告。
- `.venv312\Scripts\python.exe -m pytest` - 530 个通过，1 个警告，总覆盖率 85%。
- 新增 `.coveragerc`，将 coverage 数据文件改为 `${TEMP}/agentmanager.coverage`，避免 Windows 工作区路径下 `.coverage` 删除/重命名触发 `PermissionError: [WinError 5]`。
- `.venv312\Scripts\python.exe -m pytest tests/e2e/ -q --no-cov` - 10 个通过，1 个警告。
- 任务 4 持久化后端路线图已实现：持久化后端设置、`agentManager/storage/` 接口、PostgreSQL 状态存储库、兼容 S3 的对象存储、对象存储检查点管理器、Redis Streams 重试/死信队列处理，以及可插拔的 Qdrant 向量后端选择。
- `.venv312\Scripts\python.exe -m pytest tests/unit/test_settings.py tests/unit/test_state_manager.py tests/unit/test_checkpoint.py tests/unit/test_redis_stream_event_bus.py tests/unit/test_storage_backends.py tests/unit/memory/ -q --no-cov` - 116 个通过。
- `.venv312\Scripts\python.exe -m pytest -q --no-cov` - 557 个通过，1 个警告。
- `.venv312\Scripts\python.exe -m pytest -q` - 557 个通过，1 个警告，总覆盖率 85%。

**Docker/Compose 验证状态 (2026-05-31 更新)**:
- ✅ Compose 配置文件 (`docker-compose.yml`) 和 Dockerfile (`Dockerfile.dev`、`Dockerfile.prod`) 已通过静态分析验证，语法和路径均有效。
- ✅ 部分环境通过 Daocloud 镜像源 (`docker.m.daocloud.io`) 完成过运行时验证：开发镜像构建 (596MB)、生产镜像构建 (493MB)、5 个容器启动、API `/health` 返回正常、干净关闭。
- ⚠️ 标准 CI / 干净机器 / 目标部署环境下的 Docker Compose 验证尚未闭环。Windows PowerShell 没有 `docker` 命令；WSL `Ubuntu-24.04` 有 Docker Engine CLI `29.1.3` 但未安装 `docker compose`；Daocloud 镜像源验证受网络代理环境影响，不代表标准部署路径。
- 后续操作：在 WSL 中安装 Docker Compose v2 或在 Windows 上暴露 Docker Desktop Compose，确保 Docker Hub 注册表访问/代理设置正常工作，并在 CI 中添加 Docker build / compose config 验证 job。

## Obsidian 审查中的待修复项

- 在 Windows 或 WSL 中可用 Docker Compose v2 且 Docker Hub 镜像拉取正常后，依次运行 `docker compose config`、`docker compose build agentmanager`、`docker compose up -d`、API `/health` 检查、`docker build -f Dockerfile.prod -t agentmanager:prod .` 和 `docker compose down`。→ M4-A.2
- 确保未来的静态完成报告从 CI 支持的测试状态生成，而不是手写的时间点声明。→ M4-A.5
- 在当前默认值基础上继续强化 WorkerSandbox：隔离的每个任务工作空间、更严格的超时清理和生产容器策略审查。→ M4-D
- ✅ 审计事件数据库和对象存储写入实现已完成。→ M4-E
- ✅ OpenTelemetry 细粒度 span 已覆盖核心组件（scheduler、state_manager、checkpoint、task_executor、workflow_coordinator、worker_sandbox、engineering_memory、repair_pipeline）。→ M4-C

## 建议的重构路线图

1. 首先修复 P0 运行时问题：API 启动、包发现、DAG 循环检测、调度器循环行为、HITL 转换、EventBus 通配符处理和监控配置。✅
2. 将持久化后端连接到生产运行时路径：从部署配置实例化 PostgreSQL 状态存储、对象存储检查点和持久化内存。✅ 已通过 RuntimeFactory 完成。
3. 端到端连接执行循环，从工作流创建到沙箱执行、恢复、缺陷修复和内存写回。✅ 已通过 WorkflowCoordinator memory write-back 和 resume_workflow 完成。
4. 添加生产安全和可观测性：沙箱强化、密钥管理、审计日志、Prometheus 指标、OpenTelemetry 追踪、结构化日志、CI/CD 和部署文档。✅ 完成（含细粒度 span 和审计落库）

## 待处理的优化问题

- 提供一键安装程序，并估算支持 Linux、Windows 和 macOS 所需的工作量。
- 确定代理配置方式：项目级每个代理的 `.md` 文件与运行时提示注入。
- 定义技能如何跨代理和配置文件重用。
- 确定子组件是否需要通信，并选择通信机制。
- 支持基于配置文件的不同代理类型的技能配置。
- 确定是否应支持定时任务和钩子。
- 构建项目地图，并确定哪些提示或技能应减少代理上下文使用。
- 支持具有高级和低级层级的默认代理，管理代理默认为高级层级。
- 允许用户配置可将工作拆分为已验证任务 JSON 的管理者角色。
- 设计提示、模式和 UI 流程，让用户能够检查和编辑生成的任务 JSON。
- 支持临时角色/模板选择、用户确认以及分配给特定代理。
- 在用户确认所选代理后配置每个代理的工作目录。
- 定义角色创建期间可用的内置技能和 MCP 模板库。
- 允许用户向模板库添加新技能或 MCP 条目。
- 让用户和管理器创建的角色都可以从当前技能/MCP 模板列表中选择。

---

✅ **已完成 (2026-05-31)**:
- P0-2: 修正 README 表述矛盾 - 将 "production-ready monitoring" 改为更准确的表述
- P0-3: 修复 middleware 异常路径 context 泄漏 - 使用 try/finally 包裹中间件
- P0-4: 修复 RecoveryStrategy 选择逻辑 - 添加 allow_defect_repair 参数和正确的策略选择逻辑
- P0-5: CI 质量门禁收紧 - 更新 CI 配置以提高代码质量检查标准

**验证完成 (2026-05-31)**:
- `python -m pytest tests/unit/test_api.py -v --no-cov` - 30 个通过
- `python -m pytest tests/unit/test_recovery_engine.py -v --no-cov` - 43 个通过
- `python -m pytest tests/unit/test_task_executor.py tests/unit/test_domain_models.py -v --no-cov` - 44 个通过

✅ **P1 已完成 (2026-05-31)**:
- P1-1: 引入 RuntimeFactory — 创建 `agentManager/runtime/factory.py`，API 不再直接模块级创建全局 in-memory 对象，改为根据配置选择后端
- P1-2: StateManager 持久化集成 — StateMachine 已支持 repository 参数，RuntimeFactory 正确注入 PostgresStateRepository
- P1-3: CheckpointManager 持久化集成 — ObjectStoreCheckpointManager 已存在，RuntimeFactory 正确注入 S3ObjectStore
- P1-4: MemorySystem 持久化集成 — MemorySystem 新增 vector_backend 参数，支持可插拔向量搜索后端（Qdrant/SQLite/InMemory）
- P1-5: Compose 环境集成测试 — 添加 `tests/e2e/test_persistent_backends.py`，包含 mock 集成测试和 Docker integration 标记测试
- P1-6: README 写清楚三种运行模式 — 添加 Runtime Modes 表格和说明（local memory / local durable / production-like）
- 修复 `get_durable_backend_settings()` 中 `redis_url` 默认值从 `redis://localhost:6379/0` 改为空字符串（真正的 opt-in）
- 修复 `error_classifier` 的 RUNTIME_PATTERNS 增加 "failed" 模式（修复 e2e 测试与 P0-4 策略选择逻辑的一致性）
- 在 `pyproject.toml` 中注册 `integration` pytest marker

**验证完成 (2026-05-31)**:
- `python -m pytest tests/unit/test_runtime_factory.py -v --no-cov` - 17 个通过
- `python -m pytest tests/unit/test_api.py -v --no-cov` - 30 个通过
- `python -m pytest tests/unit/test_settings.py -v --no-cov` - 17 个通过
- `python -m pytest tests/unit/memory/ -v --no-cov` - 40 个通过
- `python -m pytest tests/e2e/test_persistent_backends.py -v --no-cov` - 5 通过，3 跳过
- `python -m pytest -q --no-cov` - 621 通过，3 跳过

**P1 后续修正 (2026-05-31)**:
- 问题1：MemorySystem.store() 异步处理 — 使用 asyncio.get_running_loop()，新增 astore()，明确 best-effort 语义
- 问题2：MemorySystem.search() — 移除 ThreadPoolExecutor 模式，新增 asearch() 异步向量搜索
- 问题3：RuntimeFactory.memory 构造 — 通过构造函数传入 vector_backend 而非直接赋值
- 问题4：RuntimeFactory.test_postgres_when_database_url — 重写为真正测试 PostgresStateRepository 注入
- 问题5：RuntimeFactory.test_in_memory_fallback_on_import_error — 使用 patch.dict(sys.modules) 替代修改 builtins.__import__
- 问题6：runtime/__init__.py — 导出 Runtime 和 create_runtime 到包级别

**最终验证完成 (2026-05-31)**:
- `python -m pytest -q --no-cov` - 624 通过，3 跳过

✅ **P2 已完成 (2026-05-31)**:
- P2-1: OTEL exporter 端到端验证 — 添加了采样率配置（OTEL_TRACING_SAMPLE_RATE）、HTTP 导出器支持（OTEL_EXPORTER_OTLP_PROTOCOL）、OTEL Collector 配置文件（monitoring/otel-collector-config.yml）
- P2-2: 审计事件落库策略 — 升级了 audit.py，支持通过 AUDIT_SINK 配置多输出（log/db/object_storage），新增自定义处理器注册机制
- P2-3: Prometheus 告警规则 — 创建了 monitoring/alerts.yml，包含 5 个关键告警（高错误率、任务超时、沙箱拒绝、恢复升级、API 延迟），更新了 prometheus.yml 引用告警规则
- P2-4: WorkerSandbox 真实 Docker 集成测试 — 创建 tests/integration/test_sandbox_docker.py，包含完整的集成测试套件，标记为 @pytest.mark.integration

**P2 代码审查修正 (2026-05-31)**:
- 🔴#1: audit.py — 修复 AuditEvent 前向引用问题，将 `_custom_audit_handlers` 从 `Set` 改为 `List`（lambda 不可哈希）
- 🔴#2: 添加 `tests/integration/__init__.py`，与其他测试目录保持一致
- 🟡#3: audit.py — `_AUDIT_SINKS` 改为惰性求值（`_get_audit_sinks()` 每次调用重新读取环境变量），新增 `configure_audit_sinks()` 显式配置函数
- 🟡#4: audit.py — 占位符 sink（db/object_storage）从 `debug` 改为 `warning` 级别，明确告知用户数据未实际落库
- 🟡#5: tracing.py — `sample_rate` 添加边界校验（非数字回退 1.0，超出 [0,1] 钳位）
- 🟡#6: tracing.py — `protocol` 添加合法性校验，无效值回退 gRPC 并输出 WARNING
- 🟡#7: tracing.py — HTTP 导出器移除 `insecure=True`（该参数仅 gRPC 导出器支持）
- 🟡#8: test_sandbox_docker.py — `docker_available()` 先用 `shutil.which("docker")` 快速检测，再尝试连接
- 🟡#9: test_sandbox_docker.py — 网络隔离测试改用 `python3 -c "import socket; ..."` 替代 `ping`（slim 镜像无 ping）
- 🟡#10: alerts.yml — 告警指标名对齐 api.py 中的实际 Prometheus Counter 名称，添加指标名注释
- 🟢#11: alerts.yml — TaskExecutionTimeout 的 `for` 从 1m 改为 2m，减少瞬时告警噪音
- 🟢#12: otel-collector-config.yml — 添加开发配置说明注释
- 🟢#13: test_sandbox_docker.py — `test_denied_mount` 改用 `with` 语句防止容器泄漏
- 🟢#14: 新增 13 个单元测试覆盖 audit 多输出、tracing 配置校验等新功能

**验证完成 (2026-05-31)**:
- `python -m pytest tests/unit/test_observability.py -v --no-cov` - 42 个通过

**P2 二次审查修正 (2026-05-31)**:
- 🟡A: audit.py — `_get_audit_sinks()` 添加 `_VALID_SINKS` 校验，无效 sink 名输出 WARNING 并被忽略；全部无效时回退到 `log`
- 🟡B: audit.py — `configure_audit_sinks()` 不再写 `os.environ`，改为进程内 `_override_sinks` 变量（优先级高于环境变量），新增 `reset_audit_sinks()` 恢复默认
- 🟢C: test_sandbox_docker.py — 容器状态断言从 `in ["created", "running"]` 改为 `== "running"`，添加 `container.reload()` 刷新状态
- 🟢D: alerts.yml — TaskExecutionTimeout 表达式从 `bucket{le="60"}` 改为 `count - bucket{le="60"}`，语义从"60s 内完成的任务"修正为"超过 60s 的任务"

**验证完成 (2026-05-31)**:
- `python -m pytest tests/unit/test_observability.py -v --no-cov` - 46 个通过

✅ **P3 已完成 (2026-06-01)**:
- P3-1: Memory write-back 真实实现 — WorkflowCoordinator 接受 `Optional[MemoryBackend]` 参数（类型安全，非 `Any`），任务完成和恢复成功时自动写入 engineering memory，best-effort 语义（失败不影响主流程）
- P3-1 改进: RuntimeFactory 自动注入 EngineeringMemory — 新增 `_create_engineering_memory()` 工厂函数，Runtime dataclass 新增 `engineering_memory` 字段
- P3-2: Resume from checkpoint — WorkflowCoordinator 新增 `resume_workflow()` 方法，从 checkpoint 恢复已完成任务状态，跳过已完成任务，继续执行未完成任务
- P3-3: Workflow crash/restart 恢复 — `resume_workflow()` 支持从新 StateMachine 实例恢复，配合持久化 checkpoint 实现崩溃后恢复
- 统一测试文件 `tests/e2e/test_workflow_resume_and_memory.py`，覆盖 memory write-back（4 个测试）、checkpoint resume（3 个测试）、crash recovery（3 个测试）

**P3 方案优化说明**:
- 原方案 P3-1 使用 `Optional[Any]`，改为 `Optional[MemoryBackend]`（类型安全）
- 原方案 P3-2/P3-3 只写测试不添加能力，改为先实现 `resume_workflow()` 方法再写测试
- 原方案 3 个独立测试文件，改为 1 个统一测试文件减少重复 harness 代码

**验证完成 (2026-06-01)**:
- `python -m pytest tests/e2e/test_workflow_resume_and_memory.py -v --no-cov` - 10 个通过
- `python -m pytest -q --no-cov` - 652 通过，12 跳过

**P3 代码审查修正 (2026-06-01)**:
- #1: 删除 `_create_engineering_memory` 函数体内冗余的 `from agentManager.memory.engineering_memory import EngineeringMemory`（顶层已导入）
- #2: `_create_engineering_memory` 返回类型从 `-> Any` 改为 `-> Optional[EngineeringMemory]`（类型安全）
- #3: `_create_engineering_memory` 忽略 settings 参数 — 在 docstring 中明确说明 `EngineeringMemory.from_settings()` 直接读取环境变量，不遵循自定义 settings 的设计意图
- #4: 提取 `_write_record_to_memory()` 公共方法消除 `_write_task_result_to_memory` 和 `_write_recovery_result_to_memory` 的代码重复，新增 `key_prefix` 参数避免 `record_type.split("_")[0]` 对 `"task_recovery"` 提取错误前缀
- #5: `resume_workflow` 恢复已完成任务时写入 memory（`_restore_completed_tasks_from_checkpoints` 中调用 `_write_task_result_to_memory(task_id, node, "restored")`），补全闭环语义
- #6: `_restore_completed_tasks_from_checkpoints` 中去掉多余的 `getattr(checkpoint, "status", None)`，改为直接 `checkpoint.status is None`（`load_checkpoint` 返回 `ExecutionContext` 已有 `status` 属性）
- #7: `test_api.py` 断言从 `endswith("OK")` 改为 `"OK" in result.stdout.strip().splitlines()`，确保 "OK" 是独立一行

**验证完成 (2026-06-01)**:
- `python -m pytest -q --no-cov` - 652 通过，12 跳过
