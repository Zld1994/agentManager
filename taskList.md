# agentManager 未完成任务清单

> **更新时间：** 2026-06-02
> **状态：** 已归档完成项；当前仅保留新发现的未完成问题。
> 已完成内容已移动到 `taskList-finished.md`。

---

## 未完成任务

### CI-1：修复覆盖率阈值失败

- [ ] **CI-1.1** 修复 GitHub Actions Python 3.10/3.12 `coverage report --fail-under=80` 失败
  - 现象：GitHub Actions run `26769717318` 中 `test (3.10)` 和 `test (3.12)` 的 `Run unit tests with coverage` 成功，但 `Check coverage threshold` 失败。
  - 目标：确认当前覆盖率缺口来源，补充合理测试或调整误纳入覆盖统计的范围，使 `coverage report --fail-under=80` 在 Python 3.10 和 3.12 上通过。
  - 验证：本地运行与 CI 对齐的覆盖率命令，并在后续 GitHub Actions run 中确认 `Check coverage threshold` 通过。

### CI-2：修复 core mypy 失败

- [ ] **CI-2.1** 修复 GitHub Actions Python 3.11 core mypy 阻塞失败
  - 现象：GitHub Actions run `26769717318` 中 `test (3.11)` 的 unit/e2e 步骤成功，但 `mypy agentManager/runtime/ agentManager/storage/ agentManager/config/ --ignore-missing-imports` 失败。
  - 目标：读取 mypy 失败输出，修复 runtime/storage/config 核心模块类型问题，不把 core mypy 降级为 advisory。
  - 验证：本地运行 `mypy agentManager/runtime/ agentManager/storage/ agentManager/config/ --ignore-missing-imports`，并在后续 GitHub Actions run 中确认 `Run mypy type checking (core modules)` 通过。

### CI-3：修复全仓库 flake8 失败

- [ ] **CI-3.1** 清理全仓库 flake8 既有违规
  - 现象：本地运行 `.venv312\Scripts\python.exe -m flake8 agentManager tests docs/reports/otel-span-performance-benchmark-2026-06-01.py docs/reports/audit-write-performance-benchmark-2026-06-01.py --max-line-length=100 --jobs=1` 时，触发大量既有问题，包括 unused imports、blank line contains whitespace、line too long、bare except、unused local variable 等。
  - 目标：分批清理 `tests/benchmarks/`、`tests/e2e/`、顶层测试文件和少量 `agentManager/` 既有 flake8 违规；避免把范围扩大到无关重构。
  - 验证：本地运行 `flake8 agentManager tests --max-line-length=100 --jobs=1`，并在后续 GitHub Actions run 中确认 `Run flake8 code style check` 通过。

### CI-4：处理测试依赖弃用警告

- [ ] **CI-4.1** 处理 FastAPI TestClient 的 StarletteDeprecationWarning
  - 现象：`.venv312\Scripts\python.exe -m pytest -q --no-cov` 通过，但持续输出 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`
  - 目标：确认 FastAPI/Starlette/httpx 兼容路径，选择升级依赖、安装 `httpx2`、或调整测试客户端用法，避免后续依赖升级导致测试破坏。
  - 验证：本地运行 `.venv312\Scripts\python.exe -m pytest -q --no-cov`，确认测试通过且该弃用警告消失。

## 外部状态说明

- 最新已检查 GitHub Actions run `26769717318` 整体仍为 failure：`docker-verify` 与 `sandbox-integration` 成功，但 Python 3.10/3.12 覆盖率阈值失败，Python 3.11 core mypy 失败。
- 上述 CI 失败已作为 `CI-1` 和 `CI-2` 加入未完成任务。
- 本地验证中额外暴露的全仓库 flake8 失败和 pytest 弃用警告已作为 `CI-3` 和 `CI-4` 加入未完成任务。
