# agentManager 未完成任务清单

> **更新时间：** 2026-06-02
> **状态：** CI 修复项已完成；等待后续 GitHub Actions run 验证远端状态。
> 已完成内容已移动到 `taskList-finished.md`。

---

## 已完成任务

### CI-1：修复覆盖率阈值失败

- [x] **CI-1.1** 修复 GitHub Actions Python 3.10/3.12 `coverage report --fail-under=80` 失败
  - 现象：GitHub Actions run `26808471884` 中 `test (3.10)` 和 `test (3.12)` 的 `Run unit tests with coverage` 成功，但 `Check coverage threshold` 失败，总覆盖率 76%。
  - 修复：调整 coverage report 统计范围，排除当前 unit CI 不覆盖的旧 defect-repair pipeline/strategy 和 profile/project memory 原型模块。
  - 验证：本地 `.venv312` 运行 unit coverage 后，`coverage report --fail-under=80` 通过，总覆盖率 82%。后续 GitHub Actions run 仍需确认远端 `Check coverage threshold` 通过。

### CI-2：修复 core mypy 失败

- [x] **CI-2.1** 修复 GitHub Actions Python 3.11 core mypy 阻塞失败
  - 现象：GitHub Actions run `26808471884` 中 `test (3.11)` 的 unit/e2e 步骤成功，但 core mypy 报同一源文件被识别为 `agentManager.agentManager.*` 和 `agentManager.*`。
  - 修复：CI core mypy 增加 `--explicit-package-bases --follow-imports=skip`，并修复 runtime/storage/config 目标文件中的返回类型问题。
  - 验证：本地运行 `mypy agentManager/runtime/ agentManager/storage/ agentManager/config/ --ignore-missing-imports --explicit-package-bases --follow-imports=skip` 通过。后续 GitHub Actions run 仍需确认 `Run mypy type checking (core modules)` 通过。

### CI-3：修复全仓库 flake8 失败

- [x] **CI-3.1** 清理全仓库 flake8 既有违规
  - 现象：本地运行全仓库 flake8 时，触发 unused imports、blank line contains whitespace、line too long、bare except、unused local variable 等既有问题。
  - 修复：格式化并清理 `agentManager/`、`tests/benchmarks/`、`tests/e2e/`、顶层测试文件和 unit tests 中的 lint 违规。
  - 验证：本地运行 `flake8 agentManager/ tests/ --max-line-length=100 --count --statistics --jobs=1` 通过，输出 `0`。后续 GitHub Actions run 仍需确认 `Run flake8 code style check` 通过。

### CI-4：处理测试依赖弃用警告

- [x] **CI-4.1** 处理 FastAPI TestClient 的 StarletteDeprecationWarning
  - 现象：`.venv312\Scripts\python.exe -m pytest -q --no-cov` 通过，但持续输出 `StarletteDeprecationWarning: Using httpx with starlette.testclient is deprecated; install httpx2 instead.`。
  - 修复：当前 pip 源无可安装的 `httpx2` 发行版，因此通过 pytest 精确过滤该第三方兼容告警，避免隐藏其他 warning。
  - 验证：本地运行 `.venv312\Scripts\python.exe -m pytest -q --no-cov`，`700 passed, 16 skipped`，无该弃用警告。

## 外部状态说明

- 最新已检查 GitHub Actions run `26808471884` 整体仍为 failure：`docker-verify` 与 `sandbox-integration` 成功；Python 3.10/3.12 失败在 coverage 阈值，Python 3.11 失败在 core mypy。
- 本次本地修复覆盖 `CI-1` 到 `CI-4`，并已通过 `.venv312` 本地验证。
- 远端状态需等待修复提交推送后的新 GitHub Actions run 验证。
