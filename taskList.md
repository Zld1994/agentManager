# agentManager M4 任务清单 — 专家团 v2

> **生成时间：** 2026-06-01  
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

- [ ] **M4-A.1.1** 验证并修复 CI `REDIS_URL` 配置
  - 文件：`.github/workflows/ci.yml` 第 66、80、104 行
  - 验证：读取三处当前值，如为 `redis://localhost:***@localhost:5432/agentmanager_test`（密码占位符 + PostgreSQL 端口）则修复为 `redis://localhost:6379/0`
  - 如已为正确值，跳过此任务（确认无需修改即可通过 M4-A.1.2）

- [ ] **M4-A.1.2** 验证 CI Redis 连接正常
  - 验证：Redis service container 可达

### M4-A.2 — Docker Compose 文档化验证

- [ ] **M4-A.2.1** `docker compose config` — 验证 compose 文件语法
  - 工作目录：`agentManager/`
  - 验证标准：退出码 0，无 ERROR

- [ ] **M4-A.2.2** `docker compose build agentmanager` — 验证开发镜像构建
  - 验证标准：构建成功，镜像大小 < 600MB

- [ ] **M4-A.2.3** `docker compose up -d` — 启动全部 5 个服务
  - 验证标准：`docker compose ps` 显示所有服务 `healthy` 或 `running`

- [ ] **M4-A.2.4** `docker build -f Dockerfile.prod -t agentmanager:prod .` — 生产镜像构建
  - 验证标准：构建成功，镜像大小 < 500MB

- [ ] **M4-A.2.5** `docker compose down` — 干净关闭
  - 验证标准：退出码 0，`docker compose ps` 无残留容器

- [ ] **M4-A.2.6** 记录验证结果到 `docs/reports/docker-compose-verification-2026-06-01.md`

### M4-A.3 — `/health` 端点增强

- [ ] **M4-A.3.1** 实现依赖连通性检查
  - 文件：`agentManager/api.py`
  - 逻辑：当 `DATABASE_URL` 配置时，尝试 `SELECT 1`；当 `REDIS_URL` 配置时，尝试 `PING`
  - 返回格式：`{"status": "ok|degraded|unhealthy", "dependencies": {"postgres": "ok|degraded", "redis": "ok|degraded"}}`
  - **非 strict 模式**（默认）：依赖不可用时仍返回 HTTP 200，`status` 标记为 `"degraded"`
  - **strict 模式**（`?strict=true`）：依赖不可用时返回 HTTP 503，`status` 标记为 `"unhealthy"`
  - 负载均衡器可通过 `strict=true` 检查判断是否将流量路由到该实例
  - 只检查**必需的**依赖（由环境变量是否配置决定），不检查 OTEL Collector / MinIO

### M4-A.4 — OTEL Collector Compose 集成

- [ ] **M4-A.4.1** 在 `docker-compose.yml` 中添加 `otel-collector` 和 `jaeger` 服务
  - otel-collector：加载 `monitoring/otel-collector-config.yml`，暴露 OTLP gRPC (4317) 和 HTTP (4318)
  - jaeger：暴露 UI 端口 16686
  - 验证：`docker compose up -d` 后 Jaeger UI 可访问

### M4-A.5 — CI Docker 验证 Job

- [ ] **M4-A.5.1** 在 `.github/workflows/ci.yml` 添加 `docker-verify` job
  - 内容：`docker compose config` + `docker build -f Dockerfile.prod` + `docker build -f Dockerfile.dev`
  - 条件：仅在 `ubuntu-latest` runner 上运行

---

## M4-B：TODO/文档修正 📝（可立即执行）

> **目标：** 路线图标记如实反映完成状态，Obsidian 审查项映射到具体 task  
> **依赖：** 无

- [ ] **M4-B.1** 修正 TODO.md 路线图标记
  - 当前：#4 "生产安全与观测" 标记 ✅ 但 P2-1.4/P2-2.2/P2-4.2 未完成
  - 修改：`✅ 基础框架 / ⏳ 细粒度 span + 审计落库待完成`
  - 验证：`git diff TODO.md`

- [ ] **M4-B.2** 将 Obsidian 审查待修复项映射到 task 编号
  - 第 56 行（Docker Compose 全流程）→ M4-A.2
  - 第 57 行（CI 支持的测试状态）→ M4-A.5
  - 第 58 行（WorkerSandbox 强化）→ M4-D
  - 第 59 行（审计事件落库）→ M4-E
  - 第 60 行（OTEL 细粒度 span）→ M4-C
  - 在每条 Obsidian 审查项后添加 `→ M4-*.x` 映射标注

- [ ] **M4-B.3** 更新 Docker/Compose 状态描述
  - 当前第 49-52 行：最后更新 2026-05-31
  - 修改：反映 M4-A.2 验证结果

---

## M4-C：OTEL 细粒度 Span 覆盖 📡（P1）

> **目标：** 从「基础设施已有但零接入」→ 核心路径 8+ 模块有 span  
> **前置审计发现：** `trace_workflow` / `trace_task` / `create_span` 全代码库零调用  
> **原则：** C1（核心引擎）优先于 C2（外围模块）；代码不依赖 Docker；E2E 验证依赖 M4-A.4

### M4-C.1 — 核心引擎 Span 覆盖（优先）

- [ ] **M4-C.1.1** 为 `agentManager/engine/scheduler.py` 添加 span
  - 注入点：`schedule_task()`、`execute_next()`、调度循环入口
  - 属性：`task.id`, `task.type`, `queue.depth`, `scheduler.concurrency`

- [ ] **M4-C.1.2** 为 `agentManager/engine/state_manager.py` 添加 span
  - 注入点：`transition()`、`get_state()`
  - 属性：`task.id`, `state.from`, `state.to`, `transition.reason`

- [ ] **M4-C.1.3** 为 `agentManager/runtime/task_executor.py` 添加 span
  - 注入点：`execute_task()` 入口
  - 复用已有 `trace_task(task_id, task_type)` context manager
  - 属性：`task.id`, `task.type`, `task.duration_ms`

- [ ] **M4-C.1.4** 为 `agentManager/runtime/workflow_coordinator.py` 添加 span
  - 注入点：`execute_workflow()` → 复用已有 `trace_workflow(workflow_id)` context manager
  - 注入点：`_execute_scheduled_task()`、`resume_workflow()`
  - 属性：`workflow.id`, `workflow.task_count`

### M4-C.2 — API 层 OTEL Middleware

- [ ] **M4-C.2.1** 添加 FastAPI OTEL instrumentation middleware
  - 文件：`agentManager/api.py`
  - **方案：使用 `opentelemetry-instrumentation-fastapi`**（推荐）
    - 与项目已有 OTEL SDK 集成一致，自动注入请求级 span
    - 在 `setup_tracing()` 中调用 `from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor; FastAPIInstrumentor.instrument_app(app)`
    - span 属性：`http.method`, `http.url`, `http.status_code`, `http.route`（自动注入）
  - 在 `pyproject.toml` 新增 `otel` extra：`opentelemetry-instrumentation-fastapi`
  - 如 `opentelemetry-instrumentation-fastapi` 不可用，降级为自定义 `@app.middleware("http")`（手动设置 span 属性）

### M4-C.3 — 外围模块 Span 覆盖

- [ ] **M4-C.3.1** 为 `agentManager/engine/checkpoint.py` 添加 span
  - 注入点：`save_checkpoint()`、`load_checkpoint()`
  - 属性：`workflow.id`, `task.id`, `checkpoint.size_bytes`

- [ ] **M4-C.3.2** 为 `agentManager/memory/` 添加 span
  - 注入点：`store()`、`search()`、`retrieve()`
  - 属性：`memory.type`（engineering/episodic/semantic），`result.count`

- [ ] **M4-C.3.3** 为 `agentManager/sandbox/worker_sandbox.py` 添加 span
  - 注入点：`create()`、`execute()`、`destroy()`
  - 属性：`sandbox.worker_id`, `sandbox.image`, `sandbox.command`（截断到 100 字符）

- [ ] **M4-C.3.4** 为 `agentManager/defect_repair/` 添加 span
  - 注入点：流水线入口、分析阶段、修复阶段、验证阶段
  - 属性：`defect.type`, `repair.strategy`, `files.modified`

### M4-C.4 — 单元测试

- [ ] **M4-C.4.1** 编写 span 属性正确性测试
  - 文件：`tests/unit/test_tracing_spans.py`
  - 覆盖：各组件 span 的属性名遵循 OTel 语义约定（点号分隔）
  - 覆盖：no-op 模式下不抛异常、不泄漏 span
  - 验证：`python -m pytest tests/unit/test_tracing_spans.py -v --no-cov`

### M4-C.5 — E2E Span 验证（依赖 M4-A.4）

- [ ] **M4-C.5.1** 端到端验证 span 输出
  - 方式：启动 `docker compose up -d`（含 OTEL Collector + Jaeger）
  - 运行一个简单工作流（`POST /workflow → POST /tasks → 执行`）
  - 检查 Jaeger UI（`http://localhost:16686`）中可以看到完整 span 链路
  - 验证标准：至少 5 个不同 span 类型的 trace 可见

---

## M4-D：沙箱安全验证 🛡️（P1）

> **前置审计发现：** `cap_drop=["ALL"]` 已硬编码在 `worker_sandbox.py:197`。  
> 本工作流为**验证已有实现**，非新增功能。

### M4-D.1 — 安全参数验证测试

- [ ] **M4-D.1.1** 在 `tests/integration/test_sandbox_docker.py` 中添加安全断言
  - `test_cap_drop_all` — 验证 `HostConfig.CapDrop` 包含 `ALL`
  - `test_readonly_rootfs` — 验证 `HostConfig.ReadonlyRootfs` 为 `true`
  - `test_network_disabled` — 验证 `NetworkSettings.Networks` 为空或 none
  - `test_no_new_privileges` — 验证 SecurityOpt 包含 `no-new-privileges:true`
  - 实现方式：创建容器后 `docker inspect` 检查 JSON 输出

- [ ] **M4-D.1.2** 运行 Docker 集成测试验证安全参数
  - 命令：`python -m pytest tests/integration/test_sandbox_docker.py -v --no-cov -m integration`
  - 验证标准：新增 4 个测试全部通过（或标记为 skip 当 Docker 不可用时）

### M4-D.2 — CI 集成测试 Job

- [ ] **M4-D.2.1** 评估 CI Docker-in-Docker 可行性
  - 试验 GitHub Actions `ubuntu-latest` 的 Docker 可用性
  - 备选方案 A：使用 runner 自带 Docker socket
  - 备选方案 B：mock 测试（`unittest.mock.patch('docker.from_env')`）验证逻辑
  - 备选方案 C：使用 `testcontainers-python` 替代直接 Docker API 调用

- [ ] **M4-D.2.2** 在 `.github/workflows/ci.yml` 添加 `sandbox-integration` job
  - 内容：`pytest tests/integration/test_sandbox_docker.py -v -m integration`
  - 条件：根据 M4-D.2.1 的可行性决定具体条件

---

## M4-E：审计落库 🗄️（P1）

> **前置审计发现：** `audit_record` 表已在 `postgres.py:130-137` 通过 `initialize_schema()` 内联创建。  
> 现有 schema：`id BIGSERIAL, action TEXT, entity_id TEXT, payload JSONB, timestamp TIMESTAMPTZ`  
> **原则：** 复用 `StateRepository.append_audit_record()` 和 `ObjectStore.put_bytes()`

### M4-E.1 — Schema 对齐检查

- [ ] **M4-E.1.1** 定义 `AuditEvent` → `audit_record` 显式映射规则
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

- [ ] **M4-E.2.1** 实现 `PostgresAuditSink` 类
  - 文件：`agentManager/observability/audit.py`
  - 接受 `StateRepository` 实例（由调用方通过 `configure_audit_sinks` 注入）
  - `write(event)` → 映射 `AuditEvent` → `AuditRecord` → 调用 `repo.append_audit_record()` 
  - **不在 audit.py 中直接操作数据库连接**——复用 StateRepository 已有的连接池

### M4-E.3 — ObjectStoreAuditSink 实现

- [ ] **M4-E.3.1** 实现 `ObjectStoreAuditSink` 类
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

- [ ] **M4-E.4.1** 实现审计事件敏感数据脱敏
  - 识别 `AuditEvent.detail` 中的敏感字段（如 `api_key`, `password`, `token`）
  - 脱敏规则：替换为 `***REDACTED***`
  - 配置方式：通过 `AUDIT_REDACT_FIELDS` 环境变量控制
  - 验证：`tests/unit/test_audit_redaction.py`

### M4-E.5 — 降级策略强化

- [ ] **M4-E.5.1** 添加审计 Sink 失败计数器
  - 指标：`agentmanager_audit_sink_failures_total{sink="db|object_storage"}`
  - 在 `record_audit_event()` 的 db / object_storage 异常分支中 `inc()`
  - 验证：Prometheus `/metrics` 端点可观测

- [ ] **M4-E.5.2** 明确审计写入降级行为文档
  - log sink 始终先写（已实现）
  - db sink 失败 → log fallback + 计数器递增
  - object_storage sink 失败 → 同上
  - **不丢事件**（核心保证）

### M4-E.6 — 测试

- [ ] **M4-E.6.1** 编写 PostgresAuditSink 单元测试
  - 文件：`tests/unit/test_audit_sinks.py`
  - mock `StateRepository`，验证 `append_audit_record()` 被正确调用
  - 验证字段映射正确

- [ ] **M4-E.6.2** 编写 ObjectStoreAuditSink 单元测试
  - 文件：`tests/unit/test_audit_sinks.py`
  - mock `ObjectStore`，验证按小时聚合 key 格式正确且每事件写入独立文件
  - 验证写入逻辑符合每事件独立文件（非 JSONL 追加）

- [ ] **M4-E.6.3** 编写降级策略测试
  - db sink 抛异常时 log sink 不受影响
  - 失败计数器正确递增

- [ ] **M4-E.6.4** 移除占位符 WARNING
  - 将 `_write_to_db` 和 `_write_to_object_storage` 从占位符函数改为调用 Sink 类
  - 不再输出 "audit event NOT actually written to DB" WARNING

---

## M4-F：配置与文档同步 📋（P2）

> **依赖：** M4-C、M4-E 的输出（新增环境变量和配置项）  
> **目标：** 确保配置文件、文档与代码实现一致

### M4-F.1 — 配置文件更新

- [ ] **M4-F.1.1** 更新 `.env.example` 新增环境变量
  - `OTEL_TRACING_ENABLED=false`
  - `OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector:4317`
  - `AUDIT_SINK=log`（默认值）
  - `AUDIT_REDACT_FIELDS=api_key,password,token`

- [ ] **M4-F.1.2** 更新 `docker-compose.yml`
  - 新增 OTEL Collector + Jaeger 服务（M4-A.4.1 的输出）
  - 新增 OTEL 相关环境变量到 agentmanager 服务

### M4-F.2 — API 文档更新

- [ ] **M4-F.2.1** 更新 `docs/api.md`
  - `/health` 端点新增 `dependencies` 字段说明
  - `/metrics` 端点新增审计失败计数器说明

### M4-F.3 — 性能基准

- [ ] **M4-F.3.1** 测量 OTEL span 对关键路径的性能影响
  - 测试对象：高频路径（scheduler, state_manager, task_executor）
  - 比较 OTEL 启用/禁用时的 P50/P99 延迟
  - 预期：开销 < 1ms/span
  - 记录到 `docs/reports/otel-span-performance-benchmark-2026-06-01.md`

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
    └── M4-E.6 (测试)

M4-F (配置同步)      ← 依赖 M4-C、M4-E 输出
    ├── M4-F.1 (配置文件)
    ├── M4-F.2 (API 文档)
    └── M4-F.3 (性能基准)
```

---

> **下一步：** M4-A.1.1（CI 修复）和 M4-B（TODO 修正）可以立即开始。M4-C.1（核心引擎 span）是最高价值的代码变更。其余按依赖关系并行推进。