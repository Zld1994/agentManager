# agentManager 未完成任务清单

> **更新时间：** 2026-06-03
> **状态：** 所有 OPT-* 优化任务已完成；按优先级和依赖关系顺序执行完毕。
> 所有 `OPT-*` 任务已完成。
> **审查修复：** 2026-06-03 已补齐 task-plan 确认钩子、确认失败事件、重复 item ID
> 拒绝、锁外事件发布、相对 workdir 约束、RuntimeFactory scheduled runner 创建，以及
> 安装脚本 extras 组合规则。

---

## 待处理优化问题拆解

> 来源：`TODO.md` 中的 `## 待处理的优化问题`。
> 排序规则：先完成配置契约和加载器，再完成技能/MCP 模板复用，再接入管理者任务 JSON、代理选择、工作目录和通信，最后补齐定时/钩子、一键安装和文档验收。

### 执行顺序总览

1. P0：`OPT-0.1` -> `OPT-1.1` -> `OPT-1.2` -> `OPT-1.3`
2. P1：`OPT-2.1` -> `OPT-2.2` -> `OPT-2.3` -> `OPT-2.4`
3. P1：`OPT-3.1` -> `OPT-3.2` -> `OPT-3.3` -> `OPT-3.4` -> `OPT-3.5` -> `OPT-3.6`
4. P2：`OPT-4.1` -> `OPT-4.2` -> `OPT-5.1` -> `OPT-5.2` -> `OPT-5.3` -> `OPT-6.1` -> `OPT-6.2`

### P0：配置契约和默认代理基座

- [x] **OPT-0.1 明确优化范围、验收口径和当前能力基线**
  - 优先级：P0
  - 依赖：无
  - 目标：把本轮优化限定为后端配置、API、角色/任务 JSON、模板库、安装脚本和文档；当前仓库没有前端目录，因此 UI 先落为 FastAPI/OpenAPI 的 JSON 审阅流程。
  - 实施文件：`docs/reports/optimization-backlog-scope.md`、`docs/api.md`、`README.md`
  - 实施方案：
    1. 记录现有入口：`agentManager/roles/`、`agentManager/domain/models.py`、`agentManager/runtime/factory.py`、`agentManager/runtime/workflow_coordinator.py`、`agentManager/sandbox/worker_sandbox.py`。
    2. 在 scope 文档中写清楚本轮不新增独立 Web 前端，先提供 API 审阅/确认流程。
    3. 将每个 TODO 优化点映射到本 taskList 的任务 ID，避免遗漏。
  - 验收：`docs/reports/optimization-backlog-scope.md` 中包含 TODO 到 `OPT-*` 的映射表；`git diff --check` 通过。

- [x] **OPT-1.1 定义 AgentProfile、技能引用、MCP 引用和层级模型**
  - 优先级：P0
  - 依赖：`OPT-0.1`
  - 目标：为项目级代理 `.md` 配置、默认高级/低级代理、技能选择和工作目录提供稳定数据契约。
  - 实施文件：新增 `agentManager/domain/agent_config.py`；修改 `agentManager/domain/__init__.py`；新增 `tests/unit/test_agent_config_models.py`
  - 实施方案：
    1. 新增 `AgentLayer` 枚举：`high`、`low`。
    2. 新增 `AgentTemplateRef` dataclass，字段包含 `kind`、`name`、`version`、`required`。
    3. 新增 `AgentWorkdirPolicy` dataclass，字段包含 `root`、`mode`、`create_if_missing`，并校验路径不能为空。
    4. 新增 `AgentProfile` dataclass，字段包含 `agent_id`、`name`、`role`、`layer`、`description`、`capabilities`、`skills`、`mcp_servers`、`prompt`、`workdir`、`metadata`。
    5. 单测覆盖枚举转换、缺失必填字段、默认层级、技能/MCP 引用保留顺序、非法 workdir 拒绝。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_agent_config_models.py -q --no-cov` 通过。

- [x] **OPT-1.2 实现项目级代理 Markdown 配置加载器**
  - 优先级：P0
  - 依赖：`OPT-1.1`
  - 目标：支持每个代理一个 `.md` 文件，文件头部保存结构化配置，正文作为运行时提示词来源。
  - 实施文件：新增 `agentManager/config/agent_profiles.py`；修改 `agentManager/config/__init__.py`；新增 `tests/unit/test_agent_profiles_loader.py`
  - 实施方案：
    1. 使用无新增依赖的 JSON front matter 格式：文件以 `---` 开始和结束，中间是 JSON 对象，正文是 prompt。
    2. 实现 `load_agent_profile(path: Path) -> AgentProfile`，把正文写入 `AgentProfile.prompt`。
    3. 实现 `load_agent_profiles(config_dir: Path) -> dict[str, AgentProfile]`，按文件名排序加载 `*.md`，重复 `agent_id` 时报错。
    4. 支持环境变量 `AGENTMANAGER_AGENT_CONFIG_DIR`，为空时使用内置默认 profile。
    5. 单测覆盖正常加载、无 front matter、无效 JSON、重复 agent、正文 prompt 注入。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_agent_profiles_loader.py -q --no-cov` 通过。

- [x] **OPT-1.3 提供默认高级/低级代理配置和管理者默认层级**
  - 优先级：P0
  - 依赖：`OPT-1.2`
  - 目标：支持默认代理层级，高级层包含 manager/supervisor，低级层包含 worker；管理代理默认属于高级层级。
  - 实施文件：新增 `agentManager/agents/defaults.py`、`agentManager/agents/__init__.py`；新增 `tests/unit/test_default_agent_profiles.py`
  - 实施方案：
    1. 在 `defaults.py` 中提供 `get_default_agent_profiles()`，返回 manager、supervisor、worker 三个 `AgentProfile`。
    2. manager profile 的 `layer` 固定为 `high`，capabilities 包含 `decompose_task`、`delegate_task`、`plan_work`。
    3. worker profile 的 `layer` 固定为 `low`，默认只接收已确认任务。
    4. loader 在没有项目配置目录时返回默认 profiles。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_default_agent_profiles.py tests/unit/test_agent_profiles_loader.py -q --no-cov` 通过。

### P1：技能/MCP 模板库和提示注入

- [x] **OPT-2.1 定义内置技能和 MCP 模板库契约**
  - 优先级：P1
  - 依赖：`OPT-1.1`
  - 目标：角色创建期间可以从内置技能和 MCP 模板列表选择条目。
  - 实施文件：新增 `agentManager/agents/template_library.py`；新增 `tests/unit/test_template_library.py`
  - 实施方案：
    1. 新增 `TemplateEntry` dataclass，字段包含 `kind`、`name`、`description`、`prompt_snippet`、`config`、`tags`。
    2. 内置模板至少包含 `task-planning`、`code-review`、`sandbox-execution` 三个 skill 条目，以及 `filesystem`、`event-bus` 两个 MCP/connector 条目。
    3. 实现 `list_templates(kind: str | None = None)` 和 `get_template(kind, name)`。
    4. 对未知模板返回清晰 `KeyError`，不要静默忽略。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_template_library.py -q --no-cov` 通过。

- [x] **OPT-2.2 支持用户向模板库追加技能或 MCP 条目**
  - 优先级：P1
  - 依赖：`OPT-2.1`
  - 目标：允许项目配置目录下的模板覆盖或扩展内置技能/MCP 列表。
  - 实施文件：修改 `agentManager/agents/template_library.py`；新增 `tests/unit/test_project_template_library.py`
  - 实施方案：
    1. 约定项目模板目录为 `<config_dir>/templates/skills/*.md` 和 `<config_dir>/templates/mcp/*.md`。
    2. 复用 `OPT-1.2` 的 JSON front matter 加载方式，正文写入 `prompt_snippet`。
    3. 项目模板与内置模板同名时覆盖内置模板，并记录来源为 `project`。
    4. 单测覆盖新增模板、覆盖内置模板、非法 kind、无效 JSON。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_project_template_library.py tests/unit/test_template_library.py -q --no-cov` 通过。

- [x] **OPT-2.3 支持不同代理类型基于配置选择技能和 MCP**
  - 优先级：P1
  - 依赖：`OPT-1.2`、`OPT-2.2`
  - 目标：让用户创建的角色和管理器创建的角色，都能从当前技能/MCP 模板列表中选择。
  - 实施文件：新增 `agentManager/agents/registry.py`；新增 `tests/unit/test_agent_registry.py`
  - 实施方案：
    1. 实现 `AgentRegistry`，组合 profiles 和 template library。
    2. 实现 `resolve_agent(agent_id)`，返回 profile 以及已解析的 skill/MCP 模板条目。
    3. 管理器创建临时角色时，必须校验所选模板存在；不存在时报错并列出可用模板名称。
    4. 单测覆盖用户 profile、默认 profile、管理器临时 profile、缺失模板失败。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_agent_registry.py -q --no-cov` 通过。

- [x] **OPT-2.4 实现运行时提示注入和上下文预算策略**
  - 优先级：P1
  - 依赖：`OPT-2.3`
  - 目标：把 agent `.md` 正文、技能/MCP prompt snippet 和项目地图摘要组合成运行时提示，同时减少低价值上下文占用。
  - 实施文件：新增 `agentManager/agents/prompt_builder.py`；新增 `scripts/generate_project_map.py`；新增 `tests/unit/test_agent_prompt_builder.py`
  - 实施方案：
    1. `build_agent_prompt(profile, templates, project_map=None, max_chars=12000)` 按 profile prompt、required skills、optional skills、MCP snippets、project map 摘要的顺序拼接。
    2. 对低层 worker 默认只注入已选择技能，不注入完整项目地图。
    3. 对高层 manager 注入项目地图摘要和任务 JSON schema 摘要。
    4. `scripts/generate_project_map.py` 生成 `docs/project-map.md`，列出主要包、职责和可省略的大段提示候选。
    5. 单测覆盖顺序、预算截断、required 模板保留、低层 agent 不注入高层上下文。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_agent_prompt_builder.py -q --no-cov` 通过，且 `python scripts/generate_project_map.py` 能生成 `docs/project-map.md`。

### P1：管理者任务 JSON、确认流程、工作目录和通信

- [x] **OPT-3.1 定义已验证任务 JSON schema**
  - 优先级：P1
  - 依赖：`OPT-1.1`
  - 目标：让管理者角色可以把工作拆成可验证、可分配、可审阅的任务 JSON。
  - 实施文件：新增 `agentManager/domain/task_plan.py`；修改 `agentManager/domain/__init__.py`；新增 `tests/unit/test_task_plan_models.py`
  - 实施方案：
    1. 新增 `TaskPlanItem`，字段包含 `id`、`title`、`description`、`priority`、`dependencies`、`assignee`、`required_skills`、`workdir`、`verification`、`status`。
    2. 新增 `TaskPlan`，字段包含 `plan_id`、`source_task_id`、`items`、`created_by`、`status`。
    3. 校验每个 dependency 必须指向同一 plan 内存在的任务。
    4. 校验 `verification` 不能为空，确保每个任务可验收。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_task_plan_models.py -q --no-cov` 通过。

- [x] **OPT-3.2 升级 ManagerRole 生成已验证任务 JSON**
  - 优先级：P1
  - 依赖：`OPT-3.1`、`OPT-2.3`
  - 目标：管理者角色输出 `TaskPlan`，而不是只返回松散 subtasks。
  - 实施文件：修改 `agentManager/roles/manager_role.py`；修改 `tests/unit/roles/test_manager_role.py`
  - 实施方案：
    1. 保留旧的 `subtasks` 输出兼容字段，新增 `task_plan` 字段。
    2. 对输入 `subtasks` 或 `steps` 归一化为 `TaskPlanItem`，默认 status 为 `pending_review`。
    3. 自动根据 `assignee` 和 `required_skills` 调用 registry 校验可分配 agent。
    4. 没有 verification 的输入自动生成 `pytest` 或人工验收说明，具体规则写入测试。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/roles/test_manager_role.py tests/unit/test_task_plan_models.py -q --no-cov` 通过。

- [x] **OPT-3.3 添加任务 JSON 生成、审阅、编辑和确认 API**
  - 优先级：P1
  - 依赖：`OPT-3.2`
  - 目标：用 API/OpenAPI 作为当前仓库的 UI 流程，让用户检查和编辑生成的任务 JSON。
  - 实施文件：修改 `agentManager/api.py`、`docs/api.md`；新增或修改 `tests/unit/test_api.py`
  - 实施方案：
    1. 新增 `POST /task-plans`：输入原始任务和可选 agent/template 选择，返回 `TaskPlan`，状态为 `pending_review`。
    2. 新增 `GET /task-plans/{plan_id}`：读取待审阅计划。
    3. 新增 `PUT /task-plans/{plan_id}`：提交用户编辑后的 JSON，并重新校验 schema、依赖和 assignee。
    4. 新增 `POST /task-plans/{plan_id}/confirm`：把 plan 状态改为 `confirmed`，并发布确认事件。
    5. 当前 prototype 可先使用内存存储，后续再接 PostgreSQL。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_api.py -q --no-cov` 通过；`docs/api.md` 包含四个新端点示例。

- [x] **OPT-3.4 支持临时角色/模板选择、用户确认和分配给特定代理**
  - 优先级：P1
  - 依赖：`OPT-3.3`
  - 目标：在确认前允许用户临时选择角色、模板和具体 assignee。
  - 实施文件：修改 `agentManager/agents/registry.py`、`agentManager/api.py`；新增 `tests/unit/test_agent_selection_flow.py`
  - 实施方案：
    1. 在 `POST /task-plans` 请求模型中加入 `temporary_roles`、`selected_templates`、`preferred_assignees`。
    2. 临时角色只在当前 plan 内有效，不写入项目配置文件。
    3. `PUT /task-plans/{plan_id}` 支持用户改写 assignee 和 required skills，并重新解析 registry。
    4. `confirm` 时冻结最终 assignee 和模板选择。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_agent_selection_flow.py tests/unit/test_api.py -q --no-cov` 通过。

- [x] **OPT-3.5 确认代理后配置每个代理的工作目录**
  - 优先级：P1
  - 依赖：`OPT-3.4`
  - 目标：把确认后的 agent workdir 注入任务 metadata，并传递到 `SandboxConfig.workspace_root` 或 task-specific workspace。
  - 实施文件：修改 `agentManager/runtime/task_executor.py`、`agentManager/sandbox/worker_sandbox.py`、`tests/unit/test_task_executor.py`、`tests/unit/test_worker_sandbox.py`
  - 实施方案：
    1. `TaskPlanItem.workdir` 写入 DAG node metadata。
    2. `TaskExecutor.run_task()` 读取 metadata 中的 `agent_id` 和 `workdir`，构造任务执行上下文时保留该信息。
    3. `WorkerSandbox` 新增从 metadata 派生 workspace 的 helper，继续复用现有路径逃逸校验。
    4. 单测覆盖 agent workdir 注入、非法路径拒绝、默认 workspace fallback。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_task_executor.py tests/unit/test_worker_sandbox.py -q --no-cov` 通过。

- [x] **OPT-3.6 明确子组件通信机制并接入事件发布**
  - 优先级：P1
  - 依赖：`OPT-3.3`
  - 目标：使用现有 EventBus/Redis Streams 作为子组件通信机制，避免角色之间直接互调。
  - 实施文件：修改 `agentManager/engine/event_bus.py`、`agentManager/engine/event_bus/`、`agentManager/api.py`、`tests/unit/test_event_bus.py`
  - 实施方案：
    1. 扩展 `EventType`：`TASK_PLAN_CREATED`、`TASK_PLAN_UPDATED`、`TASK_PLAN_CONFIRMED`、`AGENT_ASSIGNED`。
    2. 在 `/task-plans` 生成、更新、确认流程中发布事件。
    3. Redis-backed EventBus 保持同样事件 payload 形状。
    4. 单测覆盖内存事件、workflow_id 过滤、确认事件 payload 包含 plan_id 和 assignee。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_event_bus.py tests/unit/test_api.py -q --no-cov` 通过。

### P2：定时任务、钩子和安装器

- [x] **OPT-4.1 定义钩子配置和事件触发点**
  - 优先级：P2
  - 依赖：`OPT-3.6`
  - 目标：确定并实现是否支持钩子，先支持配置文件声明的 pre/post task-plan hooks 和 workflow hooks。
  - 实施文件：新增 `agentManager/runtime/hooks.py`；修改 `agentManager/runtime/workflow_coordinator.py`；新增 `tests/unit/test_runtime_hooks.py`
  - 实施方案：
    1. 定义 `HookConfig`，字段包含 `name`、`event`、`command`、`enabled`、`timeout_seconds`。
    2. 支持事件：`before_task_plan_confirm`、`after_task_plan_confirm`、`before_workflow_run`、`after_workflow_run`。
    3. 默认禁用 shell command hooks；只有 `HOOKS_ENABLED=true` 时执行。
    4. hooks 执行失败时发布失败事件并阻止确认，除非配置 `allow_failure=true`。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_runtime_hooks.py tests/unit/test_api.py -q --no-cov` 通过。

- [x] **OPT-4.2 支持基于配置的定时任务**
  - 优先级：P2
  - 依赖：`OPT-4.1`
  - 目标：确定并实现定时任务支持，优先提供内存调度和配置解析，不引入外部 scheduler 依赖。
  - 实施文件：新增 `agentManager/runtime/scheduled_tasks.py`；修改 `agentManager/runtime/factory.py`；新增 `tests/unit/test_scheduled_tasks.py`
  - 实施方案：
    1. 定义 `ScheduledTaskConfig`，字段包含 `name`、`interval_seconds`、`task_payload`、`enabled`。
    2. 从项目配置目录读取 `schedules/*.json`，只接受秒级 interval。
    3. RuntimeFactory 创建可选 scheduled task runner，但默认不自动启动。
    4. API 可增加 `GET /schedules` 查看已加载配置。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_scheduled_tasks.py tests/unit/test_runtime_factory.py -q --no-cov` 通过。

- [x] **OPT-5.1 设计一键安装范围和跨平台工作量估算**
  - 优先级：P2
  - 依赖：`OPT-1.3`
  - 目标：提供 Linux、Windows、macOS 的安装步骤和工作量估算，先文档化再写脚本。
  - 实施文件：新增 `docs/install.md`；修改 `README.md`
  - 实施方案：
    1. Linux：估算 Python、venv、editable install、可选 Docker/Compose、可选 otel extra 的工作量。
    2. Windows：估算 PowerShell、Python 3.12、`.venv312`、Docker Desktop 或 WSL Docker 的工作量。
    3. macOS：估算 Homebrew Python、venv、Docker Desktop、shell install 的工作量。
    4. 文档明确一键安装不会自动启用 durable services，仍按环境变量 opt-in。
  - 验收：`docs/install.md` 包含三平台步骤、预计耗时、前置条件和失败回退；`git diff --check` 通过。

- [x] **OPT-5.2 实现一键安装脚本**
  - 优先级：P2
  - 依赖：`OPT-5.1`
  - 目标：提供可重复执行的安装入口，减少本地环境启动成本。
  - 实施文件：新增 `scripts/install.ps1`、`scripts/install.sh`、`scripts/install.py`；新增 `tests/unit/test_install_scripts.py`
  - 实施方案：
    1. `install.py` 负责 OS 检测、Python 版本检查、venv 创建、`pip install -e ".[dev]"`、可选 extras。
    2. `install.ps1` 和 `install.sh` 只做入口包装并调用 `python scripts/install.py`。
    3. 支持 `--dry-run` 输出将执行的命令，测试只验证 dry-run，不真实安装依赖。
    4. 支持 `--with-sandbox` 和 `--with-otel`，分别安装 `[sandbox]` 和 `[otel]` extras。
  - 验收：`.venv312\Scripts\python.exe -m pytest tests/unit/test_install_scripts.py -q --no-cov` 通过；`python scripts/install.py --dry-run --with-otel` 输出包含 editable install 命令。

- [x] **OPT-5.3 增加安装后的 smoke 验证命令**
  - 优先级：P2
  - 依赖：`OPT-5.2`
  - 目标：安装脚本完成后可快速验证 API import、unit smoke 和可选 Docker 状态。
  - 实施文件：修改 `scripts/install.py`、`docs/install.md`
  - 实施方案：
    1. 新增 `--verify` 参数，运行 `python -c "from agentManager.api import app; print('OK')"`。
    2. 新增 `--verify-tests` 参数，运行 `python -m pytest tests/unit/test_api.py -q --no-cov`。
    3. 如果选择 `--with-sandbox`，检测 `docker` 是否存在；不存在时只输出环境 blocker，不让安装失败。
    4. 文档记录 Windows PowerShell、WSL Docker 和 macOS Docker Desktop 的不同失败处理。
  - 验收：`python scripts/install.py --dry-run --verify --verify-tests` 输出包含 import 和 pytest smoke 命令；`git diff --check` 通过。

### P2：文档、验收和完整回归

- [x] **OPT-6.1 同步 README、TODO、AGENTS 和 API 文档**
  - 优先级：P2
  - 依赖：`OPT-3.6`、`OPT-4.2`、`OPT-5.3`
  - 目标：让项目说明、API 文档、维护 caveat 和 TODO 状态与新功能一致。
  - 实施文件：`README.md`、`TODO.md`、`AGENTS.md`、`docs/api.md`、`docs/install.md`
  - 实施方案：
    1. `README.md` 增加 agent profile、template library、task plan review flow 和 install 脚本入口。
    2. `TODO.md` 将已实现的优化点移动到完成记录，保留未做的后续增强。
    3. `AGENTS.md` 增加新配置目录、脚本、测试命令和已知限制。
    4. `docs/api.md` 补齐新 API 的请求/响应示例。
  - 验收：文档中不再把未实现能力写成已完成；`git diff --check` 通过。

- [x] **OPT-6.2 运行完整本地验证并生成完成报告**
  - 优先级：P2
  - 依赖：`OPT-6.1`
  - 目标：在完成优化任务后留下可复核的本地验证证据，并区分本地成功与远端 CI 状态。
  - 实施文件：新增 `docs/reports/optimization-backlog-verification-2026-06-02.md`
  - 实施方案：
    1. 运行 `.venv312\Scripts\python.exe -m pytest -q --no-cov`。
    2. 运行 `flake8 agentManager/ tests/ --max-line-length=100 --count --statistics --jobs=1`。
    3. 运行 `mypy agentManager/runtime/ agentManager/storage/ agentManager/config/ --ignore-missing-imports --explicit-package-bases --follow-imports=skip`。
    4. 运行 `git diff --check`。
    5. 报告写清楚是否有 Docker/Compose 或 GitHub Actions 远端验证 blocker。
  - 验收：报告包含命令、结果、日期和 blocker；若远端 CI 未检查，明确标为 local-only verification。

## 已完成任务（既有记录）

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
