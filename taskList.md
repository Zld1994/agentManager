# agentManager 未闭合任务 — 专家团输出

> **生成时间：** 2026-06-01  
> **来源：** 专家团评审（独立评审 → 交叉质询 → 方案收敛）  
> **基线：** 652 测试通过 · P0/P1/P3 基础框架已完成  
> **原则：** 每个任务足够小，可独立验证和提交

---

## M4.1：Docker/Compose 验证闭环 🔴 P0

> **目标：** 任何干净机器 clone 后 `docker compose up` 能启动完整服务  
> **阻断：** 不完成此里程碑，不进入后续任务

### M4.1.1 — 环境准备：WSL 中启用 docker compose

- [ ] **M4.1.1.1** 验证 Docker Desktop 的 compose 插件可用性  
  命令：`docker compose version`（注意没有横杠）  
  预期：输出 Docker Compose version v2.x.x  
  若失败：从 GitHub releases 下载 `docker-compose-linux-x86_64` → `~/.docker/cli-plugins/docker-compose` → `chmod +x`

- [ ] **M4.1.1.2** 确认 Docker Hub 镜像拉取正常  
  命令：`docker pull hello-world`  
  若超时：配置 Docker Desktop proxy 设置或 Daocloud 镜像加速器

- [ ] **M4.1.1.3** 确认 WSL 中 Docker socket 可访问  
  命令：`docker info 2>&1 | head -5`  
  预期：输出 Server Version 等信息  
  若 `permission denied`：`sudo usermod -aG docker $USER` 并重新登录

### M4.1.2 — 本地 Docker Compose 全流程验证

- [ ] **M4.1.2.1** `docker compose config` — 验证 compose 文件语法  
  工作目录：`agentManager/`  
  验证标准：退出码 0，无 ERROR

- [ ] **M4.1.2.2** `docker compose build agentmanager` — 验证开发镜像构建  
  验证标准：构建成功，镜像大小 < 600MB

- [ ] **M4.1.2.3** `docker compose up -d` — 启动全部 5 个服务  
  验证标准：`docker compose ps` 显示所有服务 `healthy` 或 `running`

- [ ] **M4.1.2.4** API `/health` 检查  
  命令：`curl -s http://127.0.0.1:8000/health`  
  验证标准：返回 `{"status": "ok"}`

- [ ] **M4.1.2.5** `docker build -f Dockerfile.prod -t agentmanager:prod .` — 生产镜像构建  
  验证标准：构建成功，镜像大小 < 500MB

- [ ] **M4.1.2.6** `docker compose down` — 干净关闭  
  验证标准：退出码 0，`docker compose ps` 无残留容器

- [ ] **M4.1.2.7** 记录完整验证结果到 `docs/reports/docker-compose-verification-2026-06-01.md`  
  内容：每个步骤的命令、输出、耗时、遇到的问题和解决方案

### M4.1.3 — CI Docker 验证 Job

- [ ] **M4.1.3.1** 在 `.github/workflows/ci.yml` 添加 `docker-verify` job  
  内容：`docker compose config` + `docker build -f Dockerfile.prod` + `docker build -f Dockerfile.dev`  
  条件：仅在 ubuntu-latest runner 上运行

- [ ] **M4.1.3.2** 本地模拟 CI 环境验证  
  命令：在 WSL 中依次执行 CI job 的三个命令  
  验证标准：全部通过

- [ ] **M4.1.3.3** 推送并触发 GitHub Actions，确认 CI job 通过  
  命令：`git push` 后检查 Actions 结果

---

## M4.2：TODO.md 状态修正 🟡 P1

> **目标：** 路线图标记如实反映完成状态，不再有"全 ✅ 但子任务未完成"的误导

- [ ] **M4.2.1** 检查 TODO.md 第 62-68 行路线图标记  
  当前：#4 "生产安全与观测" 标记 ✅ 但 P2-1.4/P2-2.2/P2-4.2 未完成  
  修改：✅ 基础框架 → `✅ 基础框架 / ⏳ 细粒度 span + 审计落库待完成`

- [ ] **M4.2.2** 检查 TODO.md 第 49-52 行 Docker/Compose 状态  
  当前：已记录阻塞状态，但最后更新时间是 2026-05-31  
  修改：更新为"✅ 2026-06-01 Docker Compose v2 验证完成"（在 M4.1 完成后）

- [ ] **M4.2.3** 将 Obsidian 审查中的待修复项（第 54-60 行）对应到具体 task 编号  
  第 56 行 → M4.1.2  
  第 57 行 → M4.2.1  
  第 58 行 → M4.3.1  
  第 59 行 → M4.3.4  
  第 60 行 → M4.3.2

---

## M4.3：观测与安全补全 🟡 P1

> **目标：** 细粒度 tracing + 审计落库 + 沙箱安全验证  
> **依赖：** M4.1 完成后 Docker 环境可用

### M4.3.1 — 沙箱安全参数验证

- [ ] **M4.3.1.1** 在 `tests/integration/test_sandbox_docker.py` 中添加安全断言  
  新增测试：  
  - `test_cap_drop_all` — 验证 `HostConfig.CapDrop` 包含 `ALL`  
  - `test_readonly_rootfs` — 验证 `HostConfig.ReadonlyRootfs` 为 `true`  
  - `test_network_disabled` — 验证 `NetworkSettings.Networks` 为空或 none  
  实现方式：创建容器后 `docker inspect` 检查 JSON 输出

- [ ] **M4.3.1.2** 运行 Docker 集成测试验证安全参数  
  命令：`python -m pytest tests/integration/test_sandbox_docker.py -v --no-cov -m integration`  
  验证标准：新增 3 个测试全部通过

### M4.3.2 — OpenTelemetry 细粒度 Span 覆盖

- [ ] **M4.3.2.1** 为 `agentManager/engine/checkpoint.py` 添加 span  
  注入点：`save_checkpoint()`、`load_checkpoint()`  
  属性：workflow_id, task_id, checkpoint_size_bytes

- [ ] **M4.3.2.2** 为 `agentManager/memory/` 添加 span  
  注入点：`store()`、`search()`、`retrieve()`  
  属性：memory_type (engineering/episodic/semantic), result_count

- [ ] **M4.3.2.3** 为 `agentManager/sandbox/worker_sandbox.py` 添加 span  
  注入点：`create()`、`execute()`、`destroy()`  
  属性：worker_id, image, command_preview（截断到 100 字符）

- [ ] **M4.3.2.4** 为 `agentManager/defect_repair/` 添加 span  
  注入点：流水线入口、分析阶段、修复阶段、验证阶段  
  属性：defect_type, repair_strategy, files_modified

- [ ] **M4.3.2.5** 编写 span 覆盖单元测试  
  文件：`tests/unit/test_tracing_spans.py`  
  测试：验证各组件 span 属性正确设置、无 span 泄漏

- [ ] **M4.3.2.6** 端到端验证 span 输出  
  方式：启动 OTEL collector + Jaeger，运行一个简单工作流，检查 Jaeger UI 中是否出现所有 span  
  验证标准：4 个组件（checkpoint/memory/sandbox/defect_repair）的 span 全部可见

### M4.3.3 — CI 集成测试 Job

- [ ] **M4.3.3.1** 在 `.github/workflows/ci.yml` 添加 `integration-tests` job  
  内容：Docker 沙箱集成测试（`tests/integration/test_sandbox_docker.py`）  
  条件：`services: docker` + `if: runner.os == 'Linux'`  
  验证标准：CI job 在 PR 上自动运行并通过

### M4.3.4 — 审计落库真实实现

- [ ] **M4.3.4.1** 创建 PostgreSQL audit_record 表 migration  
  文件：`agentManager/storage/migrations/003_create_audit_table.sql`  
  字段：id, timestamp, event_type, actor, resource, action, details (JSONB), severity

- [ ] **M4.3.4.2** 实现 `PostgresAuditSink`  
  文件：`agentManager/observability/audit.py`（扩展现有占位符）  
  实现：`write(event: AuditEvent)` → INSERT INTO audit_record

- [ ] **M4.3.4.3** 实现 `ObjectStoreAuditSink`  
  文件：`agentManager/observability/audit.py`  
  实现：`write(event: AuditEvent)` → 序列化 JSON → 写入 S3/MinIO `audit/{date}/{event_id}.json`

- [ ] **M4.3.4.4** 编写审计落库集成测试  
  文件：`tests/integration/test_audit_sinks.py`  
  测试：Postgres sink 写入读取、对象存储 sink 写入读取、fallback 行为

- [ ] **M4.3.4.5** 移除占位符 WARNING  
  将 `_AUDIT_SINKS` 中的 `db` 和 `object_storage` 从占位符改为真实实现  
  不再输出 "audit event NOT actually written to DB" WARNING

---

## M4.4：M4.1 失败回退方案（条件触发）

> **触发条件：** M4.1.1（Docker Compose 启用）失败且无法在合理时间内修复  
> **不主动执行，作为预案记录**

- [ ] **M4.4.1** 如果 Docker Compose 无法在 WSL 中启用  
  回退：在 Windows 原生 PowerShell 中验证 Docker Compose  
  前提：Docker Desktop for Windows 已安装且 `docker compose` 可用

- [ ] **M4.4.2** 如果 Docker Hub 镜像拉取持续失败  
  回退：配置 Daocloud 镜像加速器（`/etc/docker/daemon.json` 中的 `registry-mirrors`）  
  仅在标准 Docker Hub 不可用时使用，确保文档中标注"使用镜像源"

- [ ] **M4.4.3** 如果 WSL Docker socket 权限不可修复（无 sudo）  
  回退：使用 Docker Desktop 的 TCP 暴露（`tcp://localhost:2375`）替代 Unix socket  
  风险：TCP 暴露无 TLS = 安全隐患，仅限本地开发使用

---

## 验证矩阵

每个里程碑完成后运行：

```bash
# M4.1 完成后
docker compose config
docker compose build agentmanager
docker compose up -d
curl -s http://127.0.0.1:8000/health
docker compose down

# M4.2 完成后
git diff TODO.md

# M4.3 完成后
python -m pytest tests/integration/test_sandbox_docker.py -v -m integration
python -m pytest tests/unit/test_tracing_spans.py -v --no-cov
python -m pytest tests/integration/test_audit_sinks.py -v
python -m pytest -q --no-cov  # 确保回归测试全过
```

---

## 建议提交顺序

### M4.1 Docker 闭环（先做）
1. `env: enable docker compose v2 in WSL and verify docker hub access`
2. `verify: docker compose full lifecycle (config → build → up → health → down)`
3. `ci: add docker-verify job (compose config + prod/dev build)`

### M4.2 TODO.md 修正
4. `docs: update roadmap status markers to reflect actual completion state`
5. `docs: map Obsidian review items to concrete task IDs`

### M4.3 观测与安全补全
6. `test: add security assertions to sandbox docker integration tests`
7. `feat: add fine-grained OTEL spans to checkpoint/memory/sandbox/defect_repair`
8. `test: add unit tests for span coverage`
9. `ci: add integration test job to CI workflow`
10. `feat: implement real PostgreSQL audit sink (replace placeholder)`
11. `feat: implement real ObjectStore audit sink (replace placeholder)`
12. `test: add integration tests for audit sinks`

---

## 里程碑依赖图

```
M4.1 (Docker 闭环) 🔴
├── M4.2.2 (更新 Docker 状态描述)
│
├── M4.2 (TODO 修正) 🟡
│   ├── M4.2.1 (路线图标记修正)
│   └── M4.2.3 (Obsidian 审查映射)
│
└── M4.3 (观测与安全补全) 🟡
    ├── M4.3.1 (沙箱安全验证) ← 需要 Docker
    ├── M4.3.2 (OTEL span) ← 不依赖 Docker
    ├── M4.3.3 (CI job) ← 需要 Docker
    └── M4.3.4 (审计落库) ← 需要 Docker (PostgreSQL)
```

---

> **下一步：** 按 M4.1 → M4.2 → M4.3 顺序执行，每个任务独立提交。M4.1 失败则触发 M4.4 回退方案。