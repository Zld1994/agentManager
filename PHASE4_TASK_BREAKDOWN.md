# Phase 4 任务分解：生产安全与观测

**总体目标**: 补齐安全、隔离、可观测性  
**总工作量**: ~630 行代码  
**预计时间**: 2-3 周  
**交付方式**: 6 个独立任务，逐个交付

---

## Task 4.1: WorkerSandbox 安全加固 (~150 行)

### 问题描述
WorkerSandbox 使用 Docker 创建容器，但安全隔离不足：
- 无 rootless 模式
- 无 readonly root filesystem
- 无 cap drop
- 无 seccomp
- 无 network policy
- 无 pids_limit

### 需求

**文件**: `agentManager/sandbox/worker_sandbox.py`

**修改内容**:
```python
# 在 create_container() 中添加安全选项
self.container = self.docker_client.containers.create(
    self.config.image,
    command="/bin/bash",
    stdin_open=True,
    tty=True,
    environment=environment,
    volumes=volumes,
    name=f"worker-{self.config.worker_id}",
    cpu_quota=int(self.config.cpu_limit * 100000),
    cpu_period=100000,
    mem_limit=self.config.memory_limit,
    memswap_limit=self.config.memory_limit,
    network_disabled=True,  # 默认禁用网络
    read_only=True,  # readonly root filesystem
    cap_drop=["ALL"],  # 删除所有 capabilities
    security_opt=[
        "no-new-privileges:true",
    ],
    pids_limit=256,  # 进程数限制
)
```

### 验收标准
- ✅ 容器内无法访问宿主 Docker socket
- ✅ 默认无法访问公网
- ✅ 无法写 root filesystem
- ✅ 超时后能正确 kill
- ✅ 所有现有测试通过

---

## Task 4.2: 命令执行 stdout/stderr 分离 (~30 行)

### 问题描述
exec_run() 使用 Docker exec_run()，但 stdout/stderr 被合并，stderr 永远是空字符串。

### 需求

**文件**: `agentManager/sandbox/worker_sandbox.py`

**修改 exec_in() 方法**:
```python
def exec_in(self, command: str, timeout: int = 300) -> tuple[int, str, str]:
    """Execute command in container and return exit code, stdout, stderr."""
    exit_code, output = self.container.exec_run(
        command,
        stdout=True,
        stderr=True,
        demux=True,  # 分离 stdout/stderr
        timeout=timeout,
    )
    
    stdout_bytes, stderr_bytes = output or (b"", b"")
    
    stdout = stdout_bytes.decode("utf-8", errors="replace") if stdout_bytes else ""
    stderr = stderr_bytes.decode("utf-8", errors="replace") if stderr_bytes else ""
    
    return exit_code, stdout, stderr
```

### 验收标准
- ✅ stdout 和 stderr 分开返回
- ✅ 能正确处理 UTF-8 编码
- ✅ 所有现有测试通过

---

## Task 4.3: Checkpoint 安全提取 (~50 行)

### 问题描述
load_checkpoint_with_recovery() 直接调用 tar.extractall()，没有路径穿越校验。

### 需求

**文件**: `agentManager/engine/checkpoint.py`

**添加 safe_extract() 函数**:
```python
def safe_extract(tar: tarfile.TarFile, path: Path) -> None:
    """Safely extract tar file with path traversal protection."""
    path = path.resolve()
    
    for member in tar.getmembers():
        target = (path / member.name).resolve()
        if not str(target).startswith(str(path)):
            raise ValueError(f"Unsafe tar path detected: {member.name}")
    
    tar.extractall(path)
```

**修改 load_checkpoint_with_recovery()**:
```python
# Python 3.12+
with tarfile.open(snapshot_file, "r:gz") as tar:
    tar.extractall(restore_path_obj, filter="data")

# 或使用 safe_extract()
with tarfile.open(snapshot_file, "r:gz") as tar:
    safe_extract(tar, restore_path_obj)
```

### 验收标准
- ✅ tar 包含 `../../evil.py` 时必须抛异常
- ✅ 正常 checkpoint 能恢复
- ✅ 所有现有测试通过

---

## Task 4.4: 密钥管理 (~100 行)

### 问题描述
docker-compose.yml 暴露默认弱密码，.env.example 包含示例密钥。

### 需求

**文件 1**: `.env.example`
```
POSTGRES_USER=
POSTGRES_PASSWORD=
POSTGRES_DB=
REDIS_URL=
QDRANT_API_KEY=
MINIO_ACCESS_KEY=
MINIO_SECRET_KEY=
SECRET_KEY=
```

**文件 2**: `.env.prod.example`
```
# 生产环境模板（需要用户填充强密码）
POSTGRES_USER=agentmanager_prod
POSTGRES_PASSWORD=<generate-strong-password>
POSTGRES_DB=agentmanager_prod
REDIS_URL=redis://redis:6379/0
QDRANT_API_KEY=<generate-api-key>
MINIO_ACCESS_KEY=<generate-access-key>
MINIO_SECRET_KEY=<generate-secret-key>
SECRET_KEY=<generate-secret-key>
```

**文件 3**: `agentManager/config/settings.py`

**添加 validate_settings() 函数**:
```python
def validate_settings(settings: dict) -> None:
    """Validate settings for weak defaults."""
    weak_values = {
        "password", "admin", "minioadmin", 
        "your-secret-key-change-in-production",
        "test", "demo"
    }
    
    for key, value in settings.items():
        if isinstance(value, str) and value.lower() in weak_values:
            raise RuntimeError(
                f"Weak default secret detected: {key}={value}. "
                f"Please set a strong value in .env file."
            )
```

### 验收标准
- ✅ 弱密码检测能识别常见弱密码
- ✅ 生产环境必须使用强密码
- ✅ 所有现有测试通过

---

## Task 4.5: Prometheus Metrics (~200 行)

### 问题描述
Prometheus 配置引用了不存在的 monitoring 文件。

### 需求

**文件 1**: `monitoring/prometheus.yml`
```yaml
global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: "agentManager-api"
    static_configs:
      - targets: ["localhost:8000"]
    metrics_path: "/metrics"
```

**文件 2**: `agentManager/api.py`

**添加 metrics 端点**:
```python
from prometheus_client import Counter, Histogram, generate_latest
from fastapi import Response

# 定义指标
TASK_COUNTER = Counter(
    "agentmanager_tasks_total",
    "Total tasks",
    ["status"]
)

TASK_DURATION = Histogram(
    "agentmanager_task_duration_seconds",
    "Task duration in seconds"
)

ERROR_COUNTER = Counter(
    "agentmanager_errors_total",
    "Total errors",
    ["error_type"]
)

REPAIR_COUNTER = Counter(
    "agentmanager_repairs_total",
    "Total repairs",
    ["repair_level", "status"]
)

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")
```

**在任务执行时更新指标**:
```python
# 在 create_task 时
TASK_COUNTER.labels(status="created").inc()

# 在任务完成时
TASK_COUNTER.labels(status="completed").inc()

# 在错误时
ERROR_COUNTER.labels(error_type="timeout").inc()
```

### 验收标准
- ✅ `/metrics` 端点返回 Prometheus 格式
- ✅ 能看到 agentmanager_* 指标
- ✅ 所有现有测试通过

---

## Task 4.6: GitHub Actions CI/CD (~100 行)

### 问题描述
测试报告可信度不足，需要自动化 CI/CD。

### 需求

**文件**: `.github/workflows/ci.yml`

```yaml
name: CI

on:
  push:
    branches: [main, master]
  pull_request:
    branches: [main, master]

jobs:
  test:
    runs-on: ubuntu-latest
    
    services:
      redis:
        image: redis:7-alpine
        options: >-
          --health-cmd "redis-cli ping"
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 6379:6379
      
      postgres:
        image: postgres:15-alpine
        env:
          POSTGRES_USER: agentmanager
          POSTGRES_PASSWORD: test
          POSTGRES_DB: agentmanager_test
        options: >-
          --health-cmd pg_isready
          --health-interval 10s
          --health-timeout 5s
          --health-retries 5
        ports:
          - 5432:5432
    
    steps:
      - uses: actions/checkout@v4
      
      - uses: actions/setup-python@v5
        with:
          python-version: "3.10"
      
      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install -e ".[dev]"
      
      - name: Run tests
        run: pytest tests/unit/ --cov=agentManager --cov-fail-under=80
      
      - name: Type check
        run: mypy agentManager
      
      - name: Code style
        run: flake8 agentManager tests
      
      - name: Upload coverage
        uses: codecov/codecov-action@v3
        with:
          files: ./coverage.xml
```

### 验收标准
- ✅ PR 不能带失败测试合并
- ✅ 覆盖率 ≥80%
- ✅ 所有检查通过

---

## 📊 任务执行顺序

```
Week 1:
  Day 1-2: Task 4.1 (WorkerSandbox 安全)
  Day 3: Task 4.2 (stdout/stderr 分离)
  Day 4: Task 4.3 (Checkpoint 安全)
  Day 5: Task 4.4 (密钥管理)

Week 2:
  Day 1-3: Task 4.5 (Prometheus Metrics)
  Day 4-5: Task 4.6 (GitHub Actions)

Week 3:
  集成测试、文档、最终验收
```

---

## 🎯 总体验收标准

- ✅ 所有 6 个任务完成
- ✅ 所有单元测试通过 (≥176)
- ✅ 代码风格 0 违规
- ✅ 覆盖率 ≥80%
- ✅ GitHub Actions 通过
- ✅ 所有代码推送到 GitHub

---

**准备好了吗？我现在委托给 Claude Code 开发！**
