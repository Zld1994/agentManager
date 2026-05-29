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

**剩余障碍 (2026-05-29)**:
- Docker/Compose 验证在本地仍被阻止。Windows PowerShell 没有 `docker` 命令。WSL `Ubuntu-24.04` 正在运行且具有 Docker Engine CLI `29.1.3`，Docker 守护进程可响应 `docker info`，但未安装 `docker compose` 或 `docker-compose`。本次尝试执行 `wsl -d Ubuntu-24.04 -- sudo apt-get update` 以安装 Compose v2 时被 Codex 平台提权额度限制拒绝，因此尚未运行 Compose 配置、开发镜像构建、服务启动、API 健康检查或生产镜像构建。后续操作：在 WSL 中安装 Docker Compose v2 或在 Windows 上暴露 Docker Desktop Compose，并确保 Docker Hub 注册表访问/代理设置正常工作。

## Obsidian 审查中的待修复项

- 在 Windows 或 WSL 中可用 Docker Compose v2 且 Docker Hub 镜像拉取正常后，依次运行 `docker compose config`、`docker compose build agentmanager`、`docker compose up -d`、API `/health` 检查、`docker build -f Dockerfile.prod -t agentmanager:prod .` 和 `docker compose down`。
- 确保未来的静态完成报告从 CI 支持的测试状态生成，而不是手写的时间点声明。
- 在当前默认值基础上继续强化 WorkerSandbox：隔离的每个任务工作空间、更严格的超时清理和生产容器策略审查。
- 添加 OpenTelemetry 追踪和部署文档，超越持久化后端接口。

## 建议的重构路线图

1. 首先修复 P0 运行时问题：API 启动、包发现、DAG 循环检测、调度器循环行为、HITL 转换、EventBus 通配符处理和监控配置。
2. 将持久化后端连接到生产运行时路径：从部署配置实例化 PostgreSQL 状态存储、对象存储检查点和持久化内存。
3. 端到端连接执行循环，从工作流创建到沙箱执行、恢复、缺陷修复和内存写回。
4. 添加生产安全和可观测性：沙箱强化、密钥管理、审计日志、Prometheus 指标、OpenTelemetry 追踪、结构化日志、CI/CD 和部署文档。

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
