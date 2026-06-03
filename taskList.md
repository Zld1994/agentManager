# agentManager 未完成任务清单

> **更新时间：** 2026-06-04
> **状态：** Task Plan Workbench 角色模板、计划级 Agent 快照、CLI 生成与 Skill 仓库优化待实施。
> **执行约束：** 本清单只记录开发任务，不代表功能已实现。历史完成项保留在 [taskList-finished.md](taskList-finished.md)。

---

## Task Plan Workbench 角色模板与 CLI 生成优化

- [ ] TPW-0.1 明确角色模板与计划级 Agent 快照模型
  - 优先级：P0
  - 依赖：无
  - 目标：冻结产品与数据模型，避免角色模板、任务内角色配置、agent、model 和 skill 绑定关系混在一起。
  - 目标文件/模块：`agentManager/domain/agent_config.py`、`agentManager/domain/task_plan.py`、`ui/agentmanager-workbench/src/api/types.ts`、`docs/api.md`
  - 实施步骤：
    1. 定义 `RoleTemplate` 语义：模板只保存可复用默认值，不直接代表某个已创建任务中的实际执行角色。
    2. 定义 `PlanAgentConfig` 语义：每个 task plan 保存一组计划级冻结快照，包含角色名称、角色定义、framework、model、skills 和模板来源。
    3. 定义任务项引用规则：`TaskPlanItem.metadata.agent_config_id` 指向计划级 `agent_configs` 中的一项；保留 `assignee` 字符串以兼容旧 API。
    4. 明确模板更新语义：更新角色模板只影响未来选择该模板的新 task/plan，不影响已经配置好的 task/plan 中的 `agent_configs` 快照。
    5. 在 API 类型与文档中写清模板、快照、任务项引用、CLI/model/skill 解耦的边界。
  - 验收方式：
    - 文档能直接指导后端模型和前端表单实现。
    - 评审确认旧 task-plan payload 不需要新增字段也能继续工作。

- [ ] TPW-1.1 后端角色模板持久化与 CRUD API
  - 优先级：P0
  - 依赖：TPW-0.1
  - 目标：提供可持久化的角色模板管理能力，并复用现有 AgentProfile / AgentRegistry 设计。
  - 目标文件/模块：`agentManager/domain/agent_config.py`、`agentManager/config/agent_profiles.py`、`agentManager/agents/registry.py`、`agentManager/api.py`、`tests/unit/test_agent_registry.py`、`tests/unit/test_api.py`
  - 实施步骤：
    1. 新增角色模板读写服务，优先读取 `AGENTMANAGER_AGENT_CONFIG_DIR`，未配置时使用项目级 `.agentmanager/` 作为配置根。
    2. 将角色模板保存为 Markdown profile：front matter 保存 `template_id`、`name`、`role`、`layer`、`framework_id`、`model`、`skills`、`metadata`，正文保存角色定义。
    3. 新增 `GET /role-templates`，返回内置模板和项目模板，并标记 `source=builtin|project|override`。
    4. 新增 `POST /role-templates`，创建项目模板并校验模板 ID、名称、角色定义和 skill 引用。
    5. 新增 `GET /role-templates/{template_id}`、`PUT /role-templates/{template_id}`、`DELETE /role-templates/{template_id}`。
    6. 内置模板不直接删除；当项目 override 被删除时，接口恢复展示内置默认模板。
    7. 保留 `GET /agents` 或新增兼容别名，让前端下拉能继续用“agents/roles”概念读取模板列表。
  - 验收方式：
    - 单测覆盖创建、读取、编辑、删除、内置模板 override、删除 override 后恢复默认模板。
    - 单测覆盖 API 鉴权开启时未带 token 返回 401。

- [ ] TPW-1.2 扩展 task-plan 计划级 `agent_configs` 快照
  - 优先级：P0
  - 依赖：TPW-1.1
  - 目标：让 task plan 保存当次角色配置快照，不受后续角色模板更新影响。
  - 目标文件/模块：`agentManager/domain/task_plan.py`、`agentManager/api.py`、`tests/unit/test_task_plan_models.py`、`tests/unit/test_api.py`、`ui/agentmanager-workbench/src/api/types.ts`
  - 实施步骤：
    1. 新增 `PlanAgentConfig` dataclass，字段包含 `agent_config_id`、`name`、`role_definition`、`framework_id`、`model`、`skills`、`source`、`template_id`、`metadata`。
    2. 扩展 `TaskPlan`，新增 `agent_configs: list[PlanAgentConfig] = field(default_factory=list)`。
    3. 扩展 FastAPI `TaskPlanRequest`、`TaskPlanUpdateRequest`、`TaskPlanResponse`，新增可选 `agent_configs`。
    4. 创建计划时允许从模板填充 `agent_configs`，也允许直接传手写配置快照。
    5. 更新计划时允许修改 `agent_configs`，但 confirmed 计划继续禁止修改。
    6. confirm 时保留旧 `assignee` 行为，同时把 `metadata.agent_config_id` 保留到响应中。
    7. 增加测试：先创建计划并保存 `agent_configs`，再更新原角色模板，旧计划中的快照内容不变。
  - 验收方式：
    - 旧 `/task-plans` payload 仍可创建计划。
    - 新 payload 可保存并返回 `agent_configs`。
    - 模板更新不影响已创建计划快照的测试通过。

- [ ] TPW-2.1 框架检测与模型/Skill 列表 API
  - 优先级：P1
  - 依赖：TPW-0.1
  - 目标：检测 Codex、Claude、Hermes、Trae 的可用状态，供角色模板和计划快照选择 framework/model/skills。
  - 目标文件/模块：`agentManager/agents/frameworks.py`、`agentManager/api.py`、`tests/unit/test_agent_frameworks.py`
  - 实施步骤：
    1. 新增 framework detector，定义 `codex`、`claude`、`hermes`、`trae` 四个框架的 CLI 名称、常见配置目录、skills 目录和模型来源。
    2. 使用 `shutil.which` 检查 CLI 是否可用，返回 `cli_status=available|missing`。
    3. 检查配置目录是否存在，返回 `config_status=available|missing`。
    4. 读取框架内部 skills 目录，只扫描 Markdown skill 文件和目录名，不执行任何脚本。
    5. 读取模型列表；读不到明确模型时返回 `framework default` 作为可选项，并标记 `source=fallback`。
    6. 新增 `GET /agent-frameworks`，返回 framework id、显示名、推荐状态、可用状态和隐藏/待办标记。
    7. 新增 `GET /agent-frameworks/{id}/models` 与 `GET /agent-frameworks/{id}/skills`。
  - 验收方式：
    - 单测 mock `shutil.which` 和目录结构，覆盖 available、partial、missing 三类结果。
    - 不存在的 framework id 返回 404。

- [ ] TPW-2.2 安全 CLI 生成服务
  - 优先级：P1
  - 依赖：TPW-2.1
  - 目标：统一封装 Codex/Claude/Hermes/Trae CLI 调用，用于生成角色草稿、任务项草稿和角色匹配提案。
  - 目标文件/模块：`agentManager/agents/cli_generation.py`、`agentManager/api.py`、`tests/unit/test_cli_generation.py`
  - 实施步骤：
    1. 建立框架命令白名单，每个 framework 只能使用预定义可执行文件和参数模板。
    2. 使用 `subprocess.run(args, shell=False, timeout=...)`，禁止 shell 字符串拼接。
    3. 设置默认超时 60 秒、stdout/stderr 最大字节数、最小环境变量集合和当前工作目录限制。
    4. 要求 CLI 输出 JSON；解析失败时返回结构化错误和截断后的可审阅摘要。
    5. 校验 JSON schema：角色草稿、任务项草稿、角色匹配提案分别使用明确 schema。
    6. 记录 framework、model、prompt_strategy、duration_ms、exit_code、output_truncated 到响应 metadata 或日志。
    7. CLI 不可用、超时、输出过大、JSON 无效时均不得创建或修改 task plan。
  - 验收方式：
    - 单测覆盖成功 JSON、无效 JSON、超时、CLI 不存在、输出过大。
    - 测试确认失败路径不会写入 `_task_plans` 或角色模板目录。

- [ ] TPW-3.1 公共 Skill 仓库 API
  - 优先级：P1
  - 依赖：TPW-1.1、TPW-2.1
  - 目标：统一展示内置、项目、框架和平台安装的 skills，并支持手动新增与一键安装。
  - 目标文件/模块：`agentManager/agents/template_library.py`、`agentManager/agents/skill_repository.py`、`agentManager/api.py`、`tests/unit/test_template_library.py`、`tests/unit/test_skill_repository.py`
  - 实施步骤：
    1. 复用 `TemplateEntry` 表达通用 skill，新增返回字段 `source`、`enabled`、`framework_id`、`provenance`、`content_hash`。
    2. 新增 `GET /skills`，合并内置 templates、项目 `<config_dir>/templates/skills/*.md`、框架 skills 目录和已安装平台 skills。
    3. 新增 `POST /skills`，按既有 Markdown front matter 格式手动创建项目 skill。
    4. 新增 `POST /skills/install`，从允许的 provider 下载 skill 到项目仓库，记录来源 URL、provider、hash 和安装时间。
    5. 新增 `POST /skills/open-directory`，只允许打开配置根下 `templates/skills/` 目录。
    6. 明确安装行为：在 Skill 管理页新增只进入仓库，不自动注入任何角色；在角色创建页新增后立即选入当前角色草稿。
  - 验收方式：
    - 单测覆盖合并来源、手动新增、安装记录 hash/source、打开目录路径限制。
    - 新增 skill 后可被角色模板和计划级快照引用。

- [ ] TPW-4.1 角色创建 CLI 辅助
  - 优先级：P1
  - 依赖：TPW-1.1、TPW-2.2、TPW-3.1
  - 目标：角色创建页支持通过 CLI 生成角色草稿，或根据已有角色定义自动匹配 skills。
  - 目标文件/模块：`agentManager/api.py`、`agentManager/agents/cli_generation.py`、`tests/unit/test_api.py`、`tests/unit/test_cli_generation.py`
  - 实施步骤：
    1. 新增 `POST /role-drafts/generate`。
    2. 支持 `mode=concept_to_role`：用户只有概念时，CLI 返回角色名称、角色定义、推荐 skills 和匹配理由。
    3. 支持 `mode=definition_to_skills`：用户已有角色定义时，CLI 只返回推荐 skills 和匹配理由。
    4. 请求必须包含用户选择的 `framework_id` 和 `model`，后端不替用户自动选择。
    5. 返回角色草稿，不直接保存为角色模板，也不写入 task plan。
    6. 前端后续保存模板时复用 TPW-1.1 的 `POST /role-templates`。
  - 验收方式：
    - 单测覆盖两个 mode。
    - 测试确认生成结果可编辑，保存前不会创建模板。

- [ ] TPW-4.2 与代理沟通生成任务和角色
  - 优先级：P1
  - 依赖：TPW-1.2、TPW-2.2、TPW-4.1
  - 目标：自然语言需求生成任务项，并可按策略让代理生成或匹配角色。
  - 目标文件/模块：`agentManager/api.py`、`agentManager/agents/cli_generation.py`、`tests/unit/test_api.py`、`tests/unit/test_cli_generation.py`
  - 实施步骤：
    1. 新增或扩展 `POST /task-plans/generate`，输入自然语言需求、Manager 选择、framework/model、角色生成策略。
    2. 策略 `existing_templates_only`：发送已有模板摘要，CLI 只允许返回模板 ID 和任务项。
    3. 策略 `match_then_create`：发送已有模板摘要和新角色 schema，CLI 先匹配模板，不合适才返回新角色草稿。
    4. 策略 `agent_generated`：CLI 可以返回全新角色草稿，但 framework/model 需要用户后续确认。
    5. 响应返回任务项草稿、agent config 草稿、模板匹配理由和 CLI metadata。
    6. 生成结果只进入前端审阅，不自动调用 `POST /task-plans`。
  - 验收方式：
    - 三种策略都有后端单测。
    - 生成失败不会创建计划或模板。

- [ ] TPW-4.3 已创建计划自动匹配角色
  - 优先级：P2
  - 依赖：TPW-4.2
  - 目标：对已有 draft 计划中的任务项补齐或重配角色，并以提案方式返回。
  - 目标文件/模块：`agentManager/api.py`、`agentManager/agents/cli_generation.py`、`tests/unit/test_api.py`
  - 实施步骤：
    1. 新增 `POST /task-plans/{plan_id}/agent-matches`。
    2. 请求支持匹配策略、可选任务项 ID 范围、可选模板集合。
    3. 后端读取现有 task plan，confirmed 计划直接返回 409。
    4. CLI 返回 agent config 提案和 item-to-agent 映射。
    5. API 只返回提案，不直接修改计划；用户应用后再调用现有 update plan 保存草稿。
  - 验收方式：
    - confirmed 计划不可匹配并返回 409。
    - draft 计划返回可审阅提案。
    - 提案应用路径通过现有 `PUT /task-plans/{plan_id}` 测试覆盖。

- [ ] TPW-5.1 前端导航与设置页
  - 优先级：P1
  - 依赖：TPW-1.1、TPW-3.1
  - 目标：降低 API Token 输入的视觉权重，并把工作台拆成计划、角色、技能、设置多视图。
  - 目标文件/模块：`ui/agentmanager-workbench/src/features/taskPlans/TaskPlanWorkspace.tsx`、`ui/agentmanager-workbench/src/api/client.ts`、`ui/agentmanager-workbench/src/api/types.ts`、`ui/agentmanager-workbench/src/styles.css`、`ui/agentmanager-workbench/src/App.test.tsx`
  - 实施步骤：
    1. 拆分 topbar、计划队列、计划明细、计划创建和编辑区域，避免 `TaskPlanWorkspace.tsx` 继续膨胀。
    2. 新增视图切换：计划、角色、技能、设置。
    3. 将 API Token 输入移到设置页或齿轮弹层。
    4. 保持 `sessionStorage["agentmanager.apiToken"]` key 不变。
    5. 刷新按钮和主题切换继续在顶栏保留，但 Token 不再常驻显示。
  - 验收方式：
    - App 测试更新后通过。
    - API client 测试确认 Bearer token 仍从 sessionStorage 发送。

- [ ] TPW-5.2 前端角色模板与计划快照表单
  - 优先级：P1
  - 依赖：TPW-1.2、TPW-5.1
  - 目标：任务创建时支持手填、模板填充、当前计划内修改和模板更新提醒。
  - 目标文件/模块：`ui/agentmanager-workbench/src/features/taskPlans/TaskPlanWorkspace.tsx`、`ui/agentmanager-workbench/src/features/taskPlans/formModel.ts`、`ui/agentmanager-workbench/src/features/taskPlans/formModel.test.ts`、`ui/agentmanager-workbench/src/App.test.tsx`
  - 实施步骤：
    1. 新建计划表单增加 agent config 区域。
    2. 从 `/role-templates` 加载模板，下拉选择后自动填充角色名称、角色定义、skills、framework、model。
    3. 允许用户在当前计划中修改已填充配置，并标记该 agent config 为 dirty。
    4. 保存 task 时，如果是手动新建角色配置，提示是否另存为角色模板。
    5. 保存 task 时，如果使用模板且有修改，弹出三选一：仅保存到当前计划、更新原模板、另存为新模板。
    6. “更新原模板”弹窗必须提示：不会影响已经配置好的 task/plan 中的角色快照。
  - 验收方式：
    - 前端测试覆盖手填、模板填充、dirty 检测、三选一保存和提醒文案。

- [ ] TPW-5.3 前端 Skill 仓库 UI
  - 优先级：P2
  - 依赖：TPW-3.1、TPW-5.1
  - 目标：支持 skill 浏览、手动新增、一键安装，以及角色页即时选择新增 skill。
  - 目标文件/模块：`ui/agentmanager-workbench/src/features/taskPlans/TaskPlanWorkspace.tsx`、`ui/agentmanager-workbench/src/api/client.ts`、`ui/agentmanager-workbench/src/api/types.ts`、`ui/agentmanager-workbench/src/styles.css`、`ui/agentmanager-workbench/src/App.test.tsx`
  - 实施步骤：
    1. 新增 Skill 仓库页面，展示内置、项目、框架、平台来源。
    2. 增加来源筛选、搜索和详情查看。
    3. 增加手动新增 skill 表单，展示 Markdown front matter 格式指引。
    4. 增加一键安装入口，安装后刷新 skill 列表。
    5. 在角色创建页点击新增 skill：创建成功后立即选中到当前角色草稿。
    6. 在 Skill 管理页新增 skill：只进入仓库，不自动注入任何角色。
  - 验收方式：
    - 前端测试覆盖两种新增入口的不同行为。
    - Browser 检查技能列表、详情和表单在移动宽度下不重叠。

- [ ] TPW-5.4 前端对话生成与自动匹配 UI
  - 优先级：P2
  - 依赖：TPW-4.2、TPW-4.3、TPW-5.2
  - 目标：提供“与代理沟通”和“自动匹配角色”的可审阅交互流程。
  - 目标文件/模块：`ui/agentmanager-workbench/src/features/taskPlans/TaskPlanWorkspace.tsx`、`ui/agentmanager-workbench/src/features/taskPlans/formModel.ts`、`ui/agentmanager-workbench/src/api/client.ts`、`ui/agentmanager-workbench/src/styles.css`、`ui/agentmanager-workbench/src/App.test.tsx`
  - 实施步骤：
    1. 添加内嵌对话框，入口包括新建计划区域的“与代理沟通”和已创建 draft 计划的“自动匹配角色”。
    2. 对话框支持选择 Manager、framework、model 和角色生成策略。
    3. 展示生成进度、错误、CLI 输出摘要和重试入口。
    4. 生成结果以可编辑任务项和 agent config 草稿展示。
    5. 用户点击“应用到表单”后才写入当前计划表单。
    6. confirmed 计划隐藏或禁用自动匹配入口。
  - 验收方式：
    - 前端测试覆盖生成成功、生成失败、应用草稿、confirmed 禁用。
    - Browser 检查桌面和移动布局无文字重叠。

- [ ] TPW-6.1 文档、测试与 tracker 收口
  - 优先级：P2
  - 依赖：TPW-1.1、TPW-1.2、TPW-2.1、TPW-2.2、TPW-3.1、TPW-4.1、TPW-4.2、TPW-4.3、TPW-5.1、TPW-5.2、TPW-5.3、TPW-5.4
  - 目标：同步文档、测试命令和 tracker 状态，确保交付描述与实际 API/UI 一致。
  - 目标文件/模块：`README.md`、`docs/api.md`、`AGENTS.md`、`TODO.md`、`taskList.md`、`ui/agentmanager-workbench/src/App.test.tsx`、`tests/unit/test_api.py`
  - 实施步骤：
    1. 更新 `README.md` 的 Workbench 说明，覆盖角色模板、计划级快照、CLI 生成和 Skill 仓库。
    2. 更新 `docs/api.md` 的新增端点、请求响应字段、错误码和兼容性说明。
    3. 更新 `AGENTS.md` 的维护说明，补充角色模板配置目录、CLI 调用安全边界和前端验证命令。
    4. 更新 `TODO.md` 与 `taskList.md`，把已完成的 TPW 任务移入归档或标记完成。
    5. 运行后端 focused tests：`py -3.12 -m pytest tests/unit/test_api.py tests/unit/test_agent_registry.py tests/unit/test_template_library.py -q --no-cov`。
    6. 运行前端验证：`npm --prefix ui/agentmanager-workbench run test`、`npm --prefix ui/agentmanager-workbench run typecheck`、`npm --prefix ui/agentmanager-workbench run build`。
    7. 使用 Browser 检查工作台桌面和移动视口。
  - 验收方式：
    - 文档描述与实际 API/UI 一致。
    - 后端、前端和 Browser 验证结果记录在最终交付说明中。
