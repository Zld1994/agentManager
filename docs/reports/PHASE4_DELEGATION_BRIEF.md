# Phase 4 委托任务：生产安全与观测

**委托对象**: Claude Code CLI  
**任务类型**: 6 个独立开发任务  
**交付方式**: 逐个任务交付 + 自测  
**验收方式**: Kiro 进行集成测试

---

## 📋 委托清单

### Task 4.1: WorkerSandbox 安全加固
- **文件**: `agentManager/sandbox/worker_sandbox.py`
- **工作量**: ~150 行
- **关键改动**: 
  - 添加 `network_disabled=True`
  - 添加 `read_only=True`
  - 添加 `cap_drop=["ALL"]`
  - 添加 `security_opt=["no-new-privileges:true"]`
  - 添加 `pids_limit=256`
- **测试**: 所有现有测试通过
- **自测**: 运行 `pytest tests/unit/test_worker_sandbox.py -v`

---

### Task 4.2: 命令执行 stdout/stderr 分离
- **文件**: `agentManager/sandbox/worker_sandbox.py`
- **工作量**: ~30 行
- **关键改动**: 
  - 修改 `exec_in()` 方法
  - 使用 `demux=True` 分离 stdout/stderr
  - 正确处理 UTF-8 编码
- **测试**: 所有现有测试通过
- **自测**: 运行 `pytest tests/unit/test_worker_sandbox.py::test_exec_in -v`

---

### Task 4.3: Checkpoint 安全提取
- **文件**: `agentManager/engine/checkpoint.py`
- **工作量**: ~50 行
- **关键改动**: 
  - 添加 `safe_extract()` 函数
  - 验证路径穿越
  - 修改 `load_checkpoint_with_recovery()`
- **测试**: 所有现有测试通过
- **自测**: 运行 `pytest tests/unit/test_checkpoint.py -v`

---

### Task 4.4: 密钥管理
- **文件**: 
  - `.env.example` (新建)
  - `.env.prod.example` (新建)
  - `agentManager/config/settings.py` (修改)
- **工作量**: ~100 行
- **关键改动**: 
  - 创建 `.env.example` 仅包含变量名
  - 创建 `.env.prod.example` 生产模板
  - 添加 `validate_settings()` 函数
- **测试**: 所有现有测试通过
- **自测**: 运行 `pytest tests/unit/test_settings.py -v`

---

### Task 4.5: Prometheus Metrics
- **文件**: 
  - `monitoring/prometheus.yml` (新建)
  - `agentManager/api.py` (修改)
- **工作量**: ~200 行
- **关键改动**: 
  - 创建 Prometheus 配置
  - 添加 `/metrics` 端点
  - 实现 4 个关键指标
  - 在任务执行时更新指标
- **测试**: 所有现有测试通过
- **自测**: 运行 `pytest tests/unit/test_api.py -v` 和 `curl http://localhost:8000/metrics`

---

### Task 4.6: GitHub Actions CI/CD
- **文件**: `.github/workflows/ci.yml` (新建)
- **工作量**: ~100 行
- **关键改动**: 
  - 创建 CI/CD 工作流
  - 配置 pytest + coverage
  - 配置 mypy 类型检查
  - 配置 flake8 代码风格
- **测试**: 本地验证工作流配置
- **自测**: 推送到 GitHub 验证 Actions 运行

---

## 🎯 交付流程

### 第 1 阶段：Task 4.1 + 4.2 (并行)
1. Claude Code 开发 Task 4.1
2. Claude Code 自测 Task 4.1
3. Claude Code 开发 Task 4.2
4. Claude Code 自测 Task 4.2
5. 提交到 GitHub
6. **Kiro 进行集成测试**

### 第 2 阶段：Task 4.3 + 4.4 (并行)
1. Claude Code 开发 Task 4.3
2. Claude Code 自测 Task 4.3
3. Claude Code 开发 Task 4.4
4. Claude Code 自测 Task 4.4
5. 提交到 GitHub
6. **Kiro 进行集成测试**

### 第 3 阶段：Task 4.5 + 4.6 (顺序)
1. Claude Code 开发 Task 4.5
2. Claude Code 自测 Task 4.5
3. Claude Code 开发 Task 4.6
4. Claude Code 自测 Task 4.6
5. 提交到 GitHub
6. **Kiro 进行集成测试**

---

## ✅ 验收标准

### 代码质量
- ✅ 所有单元测试通过 (≥176)
- ✅ 代码风格 0 违规 (flake8)
- ✅ 类型检查通过 (mypy)
- ✅ 覆盖率 ≥80%

### 功能完整性
- ✅ WorkerSandbox 安全隔离
- ✅ stdout/stderr 正确分离
- ✅ Checkpoint 路径穿越防护
- ✅ 密钥管理和验证
- ✅ Prometheus metrics 暴露
- ✅ GitHub Actions 自动化

### 文档完整性
- ✅ 每个任务有验收报告
- ✅ Phase 4 完整总结报告
- ✅ 所有代码推送到 GitHub

---

## 🚀 开始委托

**现在请 Claude Code 开始开发 Phase 4！**

按照上述流程，逐个任务交付。每个任务完成后：
1. 自测通过
2. 提交到 GitHub
3. 通知 Kiro 进行集成测试

---

**预计完成时间**: 2-3 周  
**预计代码量**: ~630 行  
**预计测试数**: ~50 个新测试
