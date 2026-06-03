# agentManager 安装指南

支持 Linux、Windows、macOS 三平台。

## 前置条件

- Python 3.10 或更高版本
- pip（随 Python 安装）
- Git（可选，用于克隆仓库）

可选依赖：
- Docker（用于沙箱执行）
- Redis（用于持久化事件总线）
- PostgreSQL（用于持久化状态存储）

## 快速安装

### 一键安装脚本

```bash
# Linux/macOS
bash scripts/install.sh

# Windows PowerShell
.\scripts\install.ps1
```

### 手动安装

```bash
# 创建虚拟环境
python -m venv .venv
# 激活
# Linux/macOS: source .venv/bin/activate
# Windows: .venv\Scripts\activate

# 安装基础包
pip install -e .

# 安装开发依赖（测试、lint、type check）
pip install -e ".[dev]"

# 可选：安装开发依赖和沙箱支持
pip install -e ".[dev,sandbox]"

# 可选：安装开发依赖和 OTEL 追踪
pip install -e ".[dev,otel]"
```

一键安装脚本默认安装 `dev` extra。使用 `--with-sandbox` 或 `--with-otel` 时，
脚本会组合 extras，例如 `python scripts/install.py --with-sandbox --with-otel`
会执行 editable install `.[dev,sandbox,otel]`。只有显式传入 `--no-dev` 时才跳过
开发依赖。

## 验证安装

```bash
# API 导入检查
python -c "from agentManager.api import app; print('OK')"

# 运行 smoke 测试
pytest tests/unit/test_api.py -q --no-cov
```

## 环境变量

| 变量 | 说明 | 默认值 |
|---|---|---|
| `DATABASE_URL` | PostgreSQL 连接 | 空（使用内存） |
| `REDIS_URL` | Redis 连接 | 空（使用内存） |
| `AGENTMANAGER_AGENT_CONFIG_DIR` | 代理配置目录 | 空（使用默认） |
| `HOOKS_ENABLED` | 启用运行时钩子 | `false` |
| `DOCS_ENABLED` | 启用 API 文档 | `true` |
| `METRICS_ENABLED` | 启用 Prometheus 指标 | `true` |
| `LOG_LEVEL` | 日志级别 | `INFO` |

## 开发环境

```bash
# 安装所有开发依赖
pip install -e ".[dev]"

# 运行测试
pytest -q --no-cov

# 代码检查
flake8 agentManager/ tests/ --max-line-length=100

# 类型检查
mypy agentManager/runtime/ agentManager/storage/ agentManager/config/ --ignore-missing-imports
```

## 故障排除

- **Docker 不可用**: 沙箱功能需要 Docker，但不影响核心功能
- **Windows 路径问题**: 使用 `.venv312\Scripts\python.exe` 运行测试
- **postgres/redis 连接失败**: 后端服务不可用时系统降级到内存模式
