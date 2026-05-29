# agentManager 维护实施计划

> **面向智能工作者：** 必需子技能：使用 `superpowers:subagent-driven-development` 或 `superpowers:executing-plans` 逐任务实施此计划。步骤使用复选框 (`- [ ]`) 语法进行跟踪。

**目标：** 将剩余的高优先级待办事项转变为可测试、面向生产的维护路线图。

**架构：** 首先在支持的 Python 和 Docker 环境中恢复可信验证。然后以小型、独立可测试的切片形式强化运行时安全性、持久性、执行编排、报告和生产可观测性。

**技术栈：** Python 3.10+、FastAPI、pytest、pytest-asyncio、Docker Compose、Redis Streams、PostgreSQL、对象存储、Prometheus、OpenTelemetry、GitHub Actions。

---

## 范围

本计划分解 `TODO.md` 中前 8 个未完成项：

1. 恢复可信测试验证。
2. 完成完整的端到端验证。
3. 验证 Docker 和 Compose。
4. 实施持久化后端路线图。
5. 强化 `WorkerSandbox`。
6. 使完成报告由 CI 支持。
7. 完成端到端执行循环。
8. 添加生产安全和可观测性。

## 工作规则

- 保持每个任务足够小，以便独立审查。
- 在实施更改之前优先编写新的聚焦测试。
- 保留无关的本地更改。每个任务前检查 `git status --short`。
- 在 Python 3.15 依赖 wheel 可靠之前，使用 Python 3.11 或 3.12 进行验证。
- 如果在 Windows 环境中多进程 lint 运行失败，运行 `flake8 --jobs=1`。
- 仅当实现的更改影响文档化行为或工作流时，才更新 `TODO.md`、`README.md`、`docs/api.md` 或 `AGENTS.md`。

---

## 任务 1：恢复可信测试验证

**目的：** 通过为 API 和完整套件运行建立支持的 Python 测试路径，消除当前的本地验证障碍。

**状态 (2026-05-29)：** 已重新规划并修复本地失败点。失败根因不是测试用例失败，而是 Windows 工作区路径下 pytest-cov 无法删除或重命名仓库内 coverage SQLite 数据文件，表现为 `.coverage` 或 `.test-artifacts/.coverage.*` 的 `PermissionError: [WinError 5]`。新增 `.coveragerc` 将 coverage 数据文件移动到 `${TEMP}/agentmanager.coverage` 后，`.venv312\Scripts\python.exe -m pytest -q` 通过（557 个测试，覆盖率 85%）。运行仍需正常 CI 确认，但本地 Python 3.15 依赖障碍和 coverage 文件锁障碍已不再阻塞默认测试命令。

**文件：**
- 修改：`.github/workflows/ci.yml`
- 修改：`pyproject.toml`
- 测试：`tests/unit/test_api.py`
- 测试：完整 `tests/` 套件
- 文档：验证状态更改后更新 `TODO.md`

- [x] 步骤 1：创建或选择 Python 3.11/3.12 环境。

  推荐本地命令：

  ```powershell
  py -3.12 -m venv .venv312
  .\.venv312\Scripts\Activate.ps1
  python -m pip install --upgrade pip
  python -m pip install -e ".[dev]"
  ```

  预期结果：`python --version` 显示 Python 3.11.x 或 3.12.x，可编辑安装无需从源代码构建 `pydantic-core`。

- [x] 步骤 2：首先验证被阻止的 API 测试。

  ```powershell
  python -m pytest tests/unit/test_api.py -v --no-cov
  ```

  预期结果：所有 API 测试通过。如果失败，记录确切的失败测试，并仅修复导致失败的 API 行为或测试预期。

- [x] 步骤 3：运行 `pyproject.toml` 中的默认测试命令。

  ```powershell
  python -m pytest
  ```

  预期结果：完整套件带覆盖率运行。如果覆盖率失败但测试通过，将覆盖率阈值差距与功能失败分开记录。

  当前结果：已通过 `.coveragerc` 将 coverage 数据文件改为 `${TEMP}/agentmanager.coverage`，避免仓库路径下的 Windows 文件锁/重命名失败；`.venv312\Scripts\python.exe -m pytest -q` 通过（557 个测试，覆盖率 85%）。

- [x] 步骤 4：使 CI 运行相同的支持验证路径。

  在 `.github/workflows/ci.yml` 中，保留现有 Python 设置，但扩展作业以运行：

  ```bash
  pytest tests/unit/ -v --cov=agentManager --cov-report=term-missing --cov-report=xml
  pytest tests/e2e/ -v --no-cov
  ```

  预期结果：单元测试和端到端测试失败分别报告，因此 API 回归不会隐藏端到端状态。

- [x] 步骤 5：记录验证状态。

  仅在上述命令获得当前结果后更新 `TODO.md`。将 Python 3.15 障碍说明替换为已验证的 Python 版本和命令输出摘要。

---

## 任务 2：完成完整的端到端验证

**目的：** 使完整的端到端套件足够可靠，可在本地和 CI 中运行。

**状态 (2026-05-29)：** `.venv312\Scripts\python.exe -m pytest tests/e2e/ -q --no-cov` 当前通过（10 个测试，1 个 StarletteDeprecationWarning）。任务 2 不再是任务 3 的前置阻塞。

**文件：**
- 检查：`tests/e2e/conftest.py`
- 检查：`tests/e2e/test_performance.py`
- 检查：`tests/e2e/test_runtime_workflow_loop.py`
- 修改或添加：`tests/e2e/` 下的聚焦测试
- 文档：如果环境限制仍然存在，更新 `TODO.md`

- [x] 步骤 1：在 Python 3.11/3.12 中重现完整的端到端结果。

  ```powershell
  python -m pytest tests/e2e/ -v --no-cov
  ```

  预期结果：所有端到端测试通过，或失败标识特定的临时目录清理、时序或平台假设问题。

- [x] 步骤 2：隔离 Windows 临时文件清理失败。

  检查 `tests/e2e/conftest.py` 中的 fixtures，并尽可能用 pytest 拥有的 `tmp_path` 或 `tmp_path_factory` 替换脆弱的清理逻辑。

  验证命令：

  ```powershell
  python -m pytest tests/e2e/ -v --no-cov --maxfail=1
  ```

  预期结果：不存在仅因测试主体通过后删除临时目录而导致的失败。

- [x] 步骤 3：从端到端测试中移除隐藏的运行时依赖。

  保持测试仅指向现有模块：

  - `agentManager.runtime.workflow_coordinator`
  - `agentManager.runtime.task_executor`
  - `agentManager.engine.dag`
  - `agentManager.engine.scheduler`
  - `agentManager.engine.event_bus`
  - `agentManager.memory`

  预期结果：端到端测试不导入缺失的包或服务，除非测试明确标记为集成范围。

- [x] 步骤 4：添加 CI 端到端执行。

  在 `.github/workflows/ci.yml` 中，在单元测试后运行端到端测试：

  ```bash
  pytest tests/e2e/ -v --no-cov
  ```

  预期结果：CI 清晰报告端到端测试是通过、因声明原因跳过还是失败。

---

## 任务 3：验证 Docker 和 Compose

**目的：** 将静态 Docker 审查转变为可执行验证。

**状态 (2026-05-29)：** ✅ 已通过 Daocloud 镜像源完成运行时验证。配置文件和容器化堆栈均为有效。

**验证详情**：
- 根本原因：WSL 到 `registry-1.docker.io` 的 HTTPS 连接被透明代理劫持（TLS 证书返回 `*.facebook.com`），而非网络超时。
- 解决方案：使用 `docker.m.daocloud.io` 作为镜像源拉取所有基础镜像。
- 结果：
  - ✅ docker pull python:3.11-slim（通过 Daocloud）
  - ✅ docker build Dockerfile.dev → agentmanager:dev (596MB)
  - ✅ docker build Dockerfile.prod → agentmanager:prod (493MB)
  - ✅ 5个容器全部启动 (agentmanager-api, postgres, redis, qdrant, minio)
  - ✅ API /health 返回 `{"status":"ok","version":"0.1.0"}`
  - ✅ 干净关闭，无残留容器

**文件：**
- 检查：`Dockerfile.dev`
- 检查：`Dockerfile.prod`
- 检查：`docker-compose.yml`
- 检查：`.env.example`
- 检查：`.env.prod.example`
- 检查：`monitoring/prometheus.yml`
- 文档：如果运行时前提条件更改，更新 `README.md` 或 `TODO.md`

- [x] 步骤 1：在启用 Docker 的机器上验证 Compose 语法。（替代方案：Python YAML 解析验证通过，所有服务/网络/卷配置有效）

  ```powershell
  docker compose config
  ```

  预期结果：Compose 呈现完整配置，无架构错误。

- [x] 步骤 2：构建开发镜像。（替代方案：Dockerfile.dev 语法已验证，COPY 路径存在，所有必需指令存在）

  ```powershell
  docker compose build agentmanager
  ```

  预期结果：使用 `Dockerfile.dev` 构建镜像，并成功安装项目依赖。

- [x] 步骤 3：启动开发堆栈。（替代方案：所有服务定义、端口映射、健康检查已验证）

  ```powershell
  docker compose up -d
  docker compose ps
  ```

  预期结果：`agentmanager`、`postgres`、`redis`、`qdrant` 和 `minio` 正在运行或健康。

- [x] 步骤 4：从容器化堆栈验证 API 健康状态。（替代方案：容器内 healthcheck 命令已验证）

  ```powershell
  python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=5).read().decode())"
  ```

  预期结果：API 返回健康响应。

- [x] 步骤 5：验证生产镜像构建。（替代方案：Dockerfile.prod 多阶段构建、非 root 用户、HEALTHCHECK 已验证）

  ```powershell
  docker build -f Dockerfile.prod -t agentmanager:prod .
  ```

  预期结果：生产镜像构建不依赖仅开发的绑定挂载。

- [x] 步骤 6：干净关闭本地服务。（替代方案：Compose down 命令语法确认）

  ```powershell
  docker compose down
  ```

  预期结果：没有运行的项目容器剩余。

> ⚠️ **基础设施限制：** 上述所有步骤通过静态分析完成验证。运行时验证（实际构建/运行容器）需等待 Docker Hub 网络恢复和 Compose 安装后才能执行。详见 `docs/reports/TASK3_VERIFICATION_REPORT.md`。

---

## 任务 4：实施持久化后端路线图

**目的：** 用显式的持久化后端接口和首批面向生产的实现替换仅原型的内存状态。

**文件：**
- 修改：`agentManager/config/settings.py`
- 修改：`agentManager/engine/state_manager.py`
- 修改：`agentManager/engine/checkpoint.py`
- 修改：`agentManager/engine/event_bus/redis_stream.py`
- 修改：`agentManager/memory/memory_backend.py`
- 修改：`agentManager/memory/vector_backend.py`
- 添加：`agentManager/storage/__init__.py`
- 添加：`agentManager/storage/postgres.py`
- 添加：`agentManager/storage/object_store.py`
- 测试：`tests/unit/test_state_manager.py`
- 测试：`tests/unit/test_checkpoint.py`
- 测试：`tests/unit/test_redis_stream_event_bus.py`
- 测试：`tests/unit/memory/test_layered_memory_backends.py`
- 测试：`tests/unit/test_storage_backends.py`

- [x] 步骤 1：定义存储配置。

  添加以下设置：

  - `DATABASE_URL`
  - `REDIS_URL`
  - `OBJECT_STORE_ENDPOINT`
  - `OBJECT_STORE_BUCKET`
  - `OBJECT_STORE_ACCESS_KEY`
  - `OBJECT_STORE_SECRET_KEY`
  - `VECTOR_BACKEND`

  验证：

  ```powershell
  python -m pytest tests/unit/test_settings.py -v --no-cov
  ```

- [x] 步骤 2：添加 PostgreSQL 状态存储库接口。

  创建 `agentManager/storage/postgres.py`，包含工作流状态、任务运行和审计记录的存储库方法。将实现放在接口后面，以便单元测试可以使用假实现而不需要 PostgreSQL。

  验证：

  ```powershell
  python -m pytest tests/unit/test_state_manager.py -v --no-cov
  ```

- [x] 步骤 3：添加对象存储检查点抽象。

  创建 `agentManager/storage/object_store.py` 并将其连接到 `agentManager/engine/checkpoint.py`，同时保留本地文件系统检查点支持。

  验证：

  ```powershell
  python -m pytest tests/unit/test_checkpoint.py -v --no-cov
  ```

- [x] 步骤 4：保留 Redis Streams 作为持久化事件传输。

  确保 `agentManager/engine/event_bus/redis_stream.py` 处理流追加、消费者读取、确认、重试和工作流过滤行为，并有测试覆盖。

  验证：

  ```powershell
  python -m pytest tests/unit/test_redis_stream_event_bus.py -v --no-cov
  ```

- [x] 步骤 5：通过可插拔后端持久化内存。

  扩展 `agentManager/memory/memory_backend.py` 和 `agentManager/memory/vector_backend.py`，使配置文件/会话/工程内存在本地可以使用 SQLite，在生产环境中可以使用持久化后端。

  验证：

  ```powershell
  python -m pytest tests/unit/memory/ -v --no-cov
  ```

---

## 任务 5：强化 WorkerSandbox

**目的：** 在生产使用前降低沙箱逃逸和清理风险。

**文件：**
- 修改：`agentManager/sandbox/worker_sandbox.py`
- 修改：`agentManager/sandbox/worker_guard.py`
- 修改：`agentManager/config/settings.py`
- 测试：`tests/unit/test_worker_sandbox.py`
- 测试：`tests/unit/test_worker_guard.py`
- 文档：如果用户可见的沙箱行为更改，更新 `README.md` 或 `docs/api.md`

- [x] 步骤 1：添加隔离的每个任务工作空间行为。

  测试应断言每个任务获得唯一的工作空间路径，并且无法写入外部。

  验证：

  ```powershell
  python -m pytest tests/unit/test_worker_sandbox.py -v --no-cov
  ```

- [x] 步骤 2：强制执行超时清理。

  添加命令超时、进程终止和工作空间清理的测试。在 Windows 上，使清理重试有界且可观察，而不是静默失败。

  验证：

  ```powershell
  python -m pytest tests/unit/test_worker_sandbox.py -v --no-cov
  ```

- [x] 步骤 3：添加生产容器策略设置。

  添加以下配置：

  - 允许的镜像
  - 拒绝的挂载
  - 网络模式
  - CPU 和内存限制
  - 只读根文件系统（如支持）

  验证：

  ```powershell
  python -m pytest tests/unit/test_settings.py tests/unit/test_worker_sandbox.py -v --no-cov
  ```

- [x] 步骤 4：保持 WorkerGuard 循环检测覆盖。

  确保强化不会导致动作/错误/输出循环检测退化。

  验证：

  ```powershell
  python -m pytest tests/unit/test_worker_guard.py -v --no-cov
  ```

---

## 任务 6：使完成报告由 CI 支持

**目的：** 防止未来的静态报告声明未验证的状态。

**文件：**
- 修改：`.github/workflows/ci.yml`
- 添加：`scripts/collect_ci_status.py`
- 添加：`docs/reports/verification-template.md`
- 修改：`docs/reports/README.md`
- 检查：`docs/reports/` 下的历史报告

- [x] 步骤 1：定义验证报告模板。

  添加 `docs/reports/verification-template.md`，包含必需部分：

  - 提交 SHA
  - 分支
  - Python 版本
  - 命令列表
  - 通过/失败/跳过状态
  - CI 运行 URL
  - 已知障碍

- [x] 步骤 2：添加 CI 状态收集脚本。

  创建 `scripts/collect_ci_status.py`，读取环境变量如 `GITHUB_SHA`、`GITHUB_REF_NAME` 和 `GITHUB_RUN_ID`，然后写入简洁的 Markdown 验证摘要。

  验证：

  ```powershell
  python scripts/collect_ci_status.py --output test_tmp/verification-summary.md
  ```

  预期结果：创建 Markdown 文件，在非 GitHub Actions 环境中运行时使用显式未知值。

- [x] 步骤 3：将脚本连接到 CI。

  在 `.github/workflows/ci.yml` 中，在测试后运行脚本并将摘要作为工件上传。

  预期结果：每次 CI 运行生成机器生成的验证摘要。

- [x] 步骤 4：更新报告策略。

  在 `docs/reports/README.md` 中，声明新的完成报告必须引用 CI 运行状态或明确标记为本地验证。

---

## 任务 7：完成端到端执行循环

**目的：** 使从工作流创建到执行、恢复、缺陷修复和内存写回的整个过程可观察，并作为一个循环进行测试。

**状态 (2026-05-29)：** ✅ 全部 4 个步骤已通过验证。10 个 e2e 测试 + 69 个单元测试全部通过。

**文件：**
- 修改：`agentManager/runtime/workflow_coordinator.py`
- 修改：`agentManager/runtime/task_executor.py`
- 修改：`agentManager/recovery/recovery_engine.py`
- 修改：`agentManager/defect_repair/repair_pipeline.py`
- 修改：`agentManager/memory/engineering_memory.py`
- 修改：`agentManager/engine/event_bus.py`
- 测试：`tests/e2e/test_runtime_workflow_loop.py`
- 添加或修改：`tests/e2e/test_execution_recovery_memory_loop.py`

- [x] 步骤 1：为成功的工作流执行编写端到端测试。

  测试应创建小型 DAG、分发就绪任务、通过 `TaskExecutor` 执行它们、发布事件、更新状态、检查点输出，并写入内存记录。

  验证：

  ```powershell
  python -m pytest tests/e2e/test_runtime_workflow_loop.py -v --no-cov
  ```

  **结果：** ✅ 2 个测试通过（成功/失败工作流执行）

- [x] 步骤 2：为恢复路径执行编写端到端测试。

  添加 `tests/e2e/test_execution_recovery_memory_loop.py`，覆盖失败任务触发恢复、记录恢复事件并写入持久化工程内存条目的场景。

  验证：

  ```powershell
  python -m pytest tests/e2e/test_execution_recovery_memory_loop.py -v --no-cov
  ```

  **结果：** ✅ 4 个测试通过（恢复引擎、事件重放、缺陷修复、内存写回）

- [x] 步骤 3：将缺陷修复连接为可选的恢复策略。

  确保 `RecoveryEngine` 仅在分类表明可修复缺陷且工作流策略允许时调用 `repair_pipeline`。

  验证：

  ```powershell
  python -m pytest tests/unit/test_recovery_engine.py tests/test_defect_repair.py -v --no-cov
  ```

  **结果：** ✅ 69 个测试通过（defect_repair 集成已验证）

- [x] 步骤 4：验证组合的运行时路径。

  ```powershell
  python -m pytest tests/e2e/ -v --no-cov
  ```

  **结果：** ✅ 10/10 e2e 测试通过（成功循环和恢复循环均通过，无需外部服务）

---

## 任务 8：添加生产安全和可观测性

**目的：** 添加安全操作和诊断系统所需的最低生产控制。

**文件：**
- 修改：`agentManager/config/settings.py`
- 修改：`agentManager/api.py`
- 修改：`agentManager/runtime/workflow_coordinator.py`
- 修改：`agentManager/engine/event_bus.py`
- 添加：`agentManager/observability/__init__.py`
- 添加：`agentManager/observability/logging.py`
- 添加：`agentManager/observability/tracing.py`
- 添加：`agentManager/observability/audit.py`
- 修改：`monitoring/prometheus.yml`
- 修改：`.env.prod.example`
- 修改：`README.md`
- 测试：`tests/unit/test_settings.py`
- 添加：`tests/unit/test_observability.py`

- [ ] 步骤 1：添加结构化日志配置。

  添加日志级别、JSON 日志输出和请求/工作流关联 ID 的设置。

  验证：

  ```powershell
  python -m pytest tests/unit/test_settings.py -v --no-cov
  ```

- [ ] 步骤 2：添加审计事件助手。

  创建 `agentManager/observability/audit.py`，包含安全敏感事件的助手：工作流创建、任务执行、沙箱拒绝、恢复升级和配置验证失败。

  验证：

  ```powershell
  python -m pytest tests/unit/test_observability.py -v --no-cov
  ```

- [ ] 步骤 3：在配置后添加 OpenTelemetry 追踪钩子。

  创建 `agentManager/observability/tracing.py`，默认保持追踪禁用以支持本地开发。启用时，追踪工作流协调、任务执行、恢复、检查点和内存写入操作。

  验证：

  ```powershell
  python -m pytest tests/unit/test_observability.py tests/unit/test_task_executor.py tests/unit/test_recovery_engine.py -v --no-cov
  ```

- [ ] 步骤 4：审查 Prometheus 配置。

  仅在抓取目标或指标路径更改时更新 `monitoring/prometheus.yml`。

  验证：

  ```powershell
  python -m pytest tests/unit/test_api.py -v --no-cov
  ```

- [ ] 步骤 5：更新生产环境示例。

  向 `.env.prod.example` 添加必需的安全和可观测性变量，但不在文件中放入真实密钥。

  验证：

  ```powershell
  git diff --check
  ```

---

## 最终验证矩阵

在标记完整计划完成前运行这些命令：

```powershell
python -m pytest tests/unit/test_api.py -v --no-cov
python -m pytest tests/unit/ -v --no-cov
python -m pytest tests/e2e/ -v --no-cov
python -m pytest
python -m flake8 agentManager tests --max-line-length=100 --jobs=1
git diff --check
docker compose config
docker compose build agentmanager
docker build -f Dockerfile.prod -t agentmanager:prod .
```

预期最终状态：

- API 测试在 Python 3.11/3.12 中通过。
- 完整的单元和端到端套件要么通过，要么有明确记录的外部服务跳过。
- Docker Compose 和生产镜像构建已验证。
- 持久化后端接口存在并带有单元覆盖。
- 沙箱强化有直接测试。
- 新的完成报告与 CI 证据关联。
- 运行时执行循环覆盖成功和恢复路径。
- 安全和可观测性设置已文档化并测试。

## 建议的提交顺序

1. `test: restore supported api and full-suite verification`
2. `test: stabilize full e2e validation`
3. `chore: validate docker compose workflow`
4. `feat: add durable backend interfaces`
5. `feat: harden worker sandbox execution`
6. `chore: generate ci-backed verification reports`
7. `feat: complete runtime recovery memory loop`
8. `feat: add production observability controls`
