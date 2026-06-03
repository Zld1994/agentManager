import {
  AlertTriangle,
  Check,
  CircleCheck,
  ClipboardList,
  Clock3,
  FilePenLine,
  KeyRound,
  Layers3,
  Moon,
  Plus,
  RefreshCw,
  Save,
  ServerCog,
  ShieldCheck,
  Smartphone,
  Sun,
  Trash2
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, useApiClient } from "../../api/client";
import type { TaskPlanResponse, TaskPlanSummary } from "../../api/types";
import {
  buildCreatePlanPayload,
  buildUpdatePlanPayload,
  createBlankItem,
  requestItemToEditable,
  updateItemField,
  type EditableTaskPlanItem
} from "./formModel";

type Notice = {
  tone: "ok" | "error" | "info";
  text: string;
};

const emptyItems = [createBlankItem(1)];

function formatTime(value: string) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit"
  }).format(new Date(value));
}

function errorText(error: unknown) {
  if (error instanceof ApiError) {
    return `${error.status}: ${error.detail}`;
  }
  if (error instanceof Error) {
    return error.message;
  }
  return "请求失败";
}

function statusLabel(status: string) {
  if (status === "confirmed") {
    return "已确认";
  }
  if (status === "draft") {
    return "草稿";
  }
  return status;
}

function StatusBadge({ status }: { status: string }) {
  const Icon = status === "confirmed" ? CircleCheck : Clock3;

  return (
    <span className={`status-pill ${status}`}>
      <Icon size={14} />
      {statusLabel(status)}
    </span>
  );
}

function LoadingSkeleton({ label }: { label: string }) {
  return (
    <div className="skeleton-block" role="status" aria-label={label}>
      <span className="skeleton-line wide" />
      <span className="skeleton-line" />
      <span className="skeleton-line short" />
    </div>
  );
}

function sortPlans(plans: TaskPlanSummary[]) {
  return [...plans].sort(
    (left, right) =>
      new Date(right.updated_at).getTime() - new Date(left.updated_at).getTime()
  );
}

type ItemEditorProps = {
  item: EditableTaskPlanItem;
  index: number;
  disabled?: boolean;
  onChange: (item: EditableTaskPlanItem) => void;
  onRemove: () => void;
};

function ItemEditor({ item, index, disabled, onChange, onRemove }: ItemEditorProps) {
  return (
    <section className="item-editor" aria-label={`任务项 ${index + 1}`}>
      <div className="item-editor__header">
        <span>#{index + 1}</span>
        <button
          className="icon-button danger"
          type="button"
          onClick={onRemove}
          disabled={disabled}
          title="删除任务项"
          aria-label="删除任务项"
        >
          <Trash2 size={16} />
        </button>
      </div>
      <label>
        ID
        <input
          disabled={disabled}
          value={item.id}
          onChange={(event) => onChange(updateItemField(item, "id", event.target.value))}
        />
      </label>
      <label className="span-2">
        标题
        <input
          disabled={disabled}
          value={item.title}
          onChange={(event) => onChange(updateItemField(item, "title", event.target.value))}
        />
      </label>
      <label>
        优先级
        <input
          disabled={disabled}
          type="number"
          min={0}
          value={item.priority}
          onChange={(event) =>
            onChange(updateItemField(item, "priority", Number(event.target.value)))
          }
        />
      </label>
      <label>
        依赖
        <input
          disabled={disabled}
          placeholder="item-1, item-2"
          value={item.dependenciesText}
          onChange={(event) =>
            onChange(updateItemField(item, "dependenciesText", event.target.value))
          }
        />
      </label>
      <label>
        代理
        <input
          disabled={disabled}
          value={item.assignee}
          onChange={(event) =>
            onChange(updateItemField(item, "assignee", event.target.value))
          }
        />
      </label>
      <label>
        技能
        <input
          disabled={disabled}
          placeholder="typescript, review"
          value={item.requiredSkillsText}
          onChange={(event) =>
            onChange(updateItemField(item, "requiredSkillsText", event.target.value))
          }
        />
      </label>
      <label>
        工作目录
        <input
          disabled={disabled}
          value={item.workdir}
          onChange={(event) => onChange(updateItemField(item, "workdir", event.target.value))}
        />
      </label>
      <label className="span-2">
        验证
        <textarea
          disabled={disabled}
          rows={2}
          value={item.verification}
          onChange={(event) =>
            onChange(updateItemField(item, "verification", event.target.value))
          }
        />
      </label>
      <label className="span-2">
        描述
        <textarea
          disabled={disabled}
          rows={2}
          value={item.description}
          onChange={(event) =>
            onChange(updateItemField(item, "description", event.target.value))
          }
        />
      </label>
    </section>
  );
}

type PlanListProps = {
  plans: TaskPlanSummary[];
  selectedPlanId: string;
  onSelect: (planId: string) => void;
};

function PlanList({ plans, selectedPlanId, onSelect }: PlanListProps) {
  if (plans.length === 0) {
    return (
      <div className="empty-state">
        <ClipboardList size={18} />
        <span>暂无任务计划</span>
      </div>
    );
  }

  return (
    <div className="plan-list">
      {plans.map((plan) => (
        <button
          className={`plan-row ${plan.plan_id === selectedPlanId ? "active" : ""}`}
          key={plan.plan_id}
          type="button"
          onClick={() => onSelect(plan.plan_id)}
        >
          <span className="plan-row__icon">
            {plan.status === "confirmed" ? <ShieldCheck size={18} /> : <Layers3 size={18} />}
          </span>
          <span className="plan-row__main">
            <strong>{plan.plan_id}</strong>
            <span>来源：{plan.source_task_id || "default"}</span>
          </span>
          <StatusBadge status={plan.status} />
          <span className="plan-row__meta">{plan.items_count} 项</span>
          <span className="plan-row__time">{formatTime(plan.updated_at)}</span>
        </button>
      ))}
    </div>
  );
}

type DetailProps = {
  plan?: TaskPlanResponse;
  loading: boolean;
  selectedPlanId: string;
};

function DetailPanel({ plan, loading, selectedPlanId }: DetailProps) {
  if (!selectedPlanId) {
    return (
      <div className="empty-state elevated">
        <FilePenLine size={18} />
        <span>选择左侧计划后查看明细</span>
      </div>
    );
  }
  if (loading) {
    return <LoadingSkeleton label="正在读取计划" />;
  }
  if (!plan) {
    return (
      <div className="empty-state elevated">
        <AlertTriangle size={18} />
        <span>未找到计划</span>
      </div>
    );
  }

  return (
    <div className="detail-list" role="table" aria-label="任务计划明细">
      <div className="detail-row detail-row--head" role="row">
        <span role="columnheader">任务</span>
        <span role="columnheader">状态</span>
        <span role="columnheader">代理</span>
        <span role="columnheader">验证</span>
      </div>
      {plan.items.map((item) => (
        <div className="detail-row" role="row" key={item.id}>
          <span className="detail-task" role="cell">
            <strong>{item.title}</strong>
            <small>{item.id}</small>
          </span>
          <span role="cell">
            <StatusBadge status={item.status} />
          </span>
          <span role="cell">{item.assignee || "未指定"}</span>
          <span role="cell">{item.verification || "未填写"}</span>
        </div>
      ))}
    </div>
  );
}

export function TaskPlanWorkspace() {
  const api = useApiClient();
  const queryClient = useQueryClient();
  const [selectedPlanId, setSelectedPlanId] = useState("");
  const [apiToken, setApiToken] = useState(
    () => window.sessionStorage.getItem("agentmanager.apiToken") ?? ""
  );
  const [notice, setNotice] = useState<Notice | null>(null);
  const [draftPlanId, setDraftPlanId] = useState("plan-ui");
  const [draftSourceTaskId, setDraftSourceTaskId] = useState("task-root");
  const [draftItems, setDraftItems] = useState<EditableTaskPlanItem[]>(emptyItems);
  const [editItems, setEditItems] = useState<EditableTaskPlanItem[]>([]);
  const [theme, setTheme] = useState<"light" | "dark">(
    () =>
      (window.sessionStorage.getItem("agentmanager.theme") as "light" | "dark" | null) ??
      "light"
  );

  const plansQuery = useQuery({
    queryKey: ["task-plans"],
    queryFn: api.listTaskPlans,
    refetchInterval: 8000
  });

  const plans = useMemo(
    () => sortPlans(plansQuery.data?.task_plans ?? []),
    [plansQuery.data?.task_plans]
  );

  const selectedPlanQuery = useQuery({
    queryKey: ["task-plan", selectedPlanId],
    queryFn: () => api.getTaskPlan(selectedPlanId),
    enabled: Boolean(selectedPlanId)
  });

  useEffect(() => {
    if (selectedPlanQuery.data) {
      setEditItems(selectedPlanQuery.data.items.map(requestItemToEditable));
    }
  }, [selectedPlanQuery.data]);

  const createMutation = useMutation({
    mutationFn: () =>
      api.createTaskPlan(
        buildCreatePlanPayload({
          planId: draftPlanId,
          sourceTaskId: draftSourceTaskId,
          items: draftItems
        })
      ),
    onSuccess: (plan) => {
      setNotice({ tone: "ok", text: `已创建 ${plan.plan_id}` });
      setSelectedPlanId(plan.plan_id);
      setDraftPlanId(`plan-${Date.now().toString().slice(-5)}`);
      setDraftItems([createBlankItem(1)]);
      void queryClient.invalidateQueries({ queryKey: ["task-plans"] });
    },
    onError: (error) => setNotice({ tone: "error", text: errorText(error) })
  });

  const updateMutation = useMutation({
    mutationFn: () => api.updateTaskPlan(selectedPlanId, buildUpdatePlanPayload(editItems)),
    onSuccess: (plan) => {
      setNotice({ tone: "ok", text: `已保存 ${plan.plan_id}` });
      void queryClient.invalidateQueries({ queryKey: ["task-plans"] });
      void queryClient.invalidateQueries({ queryKey: ["task-plan", selectedPlanId] });
    },
    onError: (error) => setNotice({ tone: "error", text: errorText(error) })
  });

  const confirmMutation = useMutation({
    mutationFn: () => api.confirmTaskPlan(selectedPlanId),
    onSuccess: (plan) => {
      setNotice({ tone: "ok", text: `已确认 ${plan.plan_id}` });
      void queryClient.invalidateQueries({ queryKey: ["task-plans"] });
      void queryClient.invalidateQueries({ queryKey: ["task-plan", selectedPlanId] });
    },
    onError: (error) => setNotice({ tone: "error", text: errorText(error) })
  });

  const selectedPlan = selectedPlanQuery.data;
  const selectedConfirmed = selectedPlan?.status === "confirmed";
  const busy = createMutation.isPending || updateMutation.isPending || confirmMutation.isPending;

  useEffect(() => {
    if (plansQuery.error) {
      setNotice({ tone: "error", text: errorText(plansQuery.error) });
    }
  }, [plansQuery.error]);

  function saveToken() {
    window.sessionStorage.setItem("agentmanager.apiToken", apiToken.trim());
    setNotice({ tone: "info", text: "Token 已保存到当前浏览器会话" });
    void queryClient.invalidateQueries();
  }

  function toggleTheme() {
    setTheme((current) => {
      const next = current === "light" ? "dark" : "light";
      window.sessionStorage.setItem("agentmanager.theme", next);
      return next;
    });
  }

  function updateDraftItem(index: number, item: EditableTaskPlanItem) {
    setDraftItems((items) => items.map((current, i) => (i === index ? item : current)));
  }

  function updateEditItem(index: number, item: EditableTaskPlanItem) {
    setEditItems((items) => items.map((current, i) => (i === index ? item : current)));
  }

  return (
    <main className="workbench-shell" data-theme={theme}>
      <header className="topbar">
        <div className="topbar__title">
          <p className="eyebrow">agentManager</p>
          <h1>任务计划工作台</h1>
          <p className="subtitle">面向审阅、确认与交付编排的 TaskPlan 操作台</p>
        </div>
        <div className="topbar__actions">
          <div className="token-box">
            <KeyRound size={16} />
            <input
              aria-label="API Token"
              type="password"
              placeholder="API Token"
              value={apiToken}
              onChange={(event) => setApiToken(event.target.value)}
            />
            <button type="button" onClick={saveToken}>
              保存
            </button>
          </div>
          <button
            className="icon-text-button"
            type="button"
            onClick={() => void plansQuery.refetch()}
          >
            <RefreshCw size={16} className={plansQuery.isFetching ? "spin" : ""} />
            刷新
          </button>
          <button
            className="icon-text-button theme-toggle"
            type="button"
            onClick={toggleTheme}
            aria-label={theme === "light" ? "切换为暗色主题" : "切换为浅色主题"}
            title={theme === "light" ? "切换为暗色主题" : "切换为浅色主题"}
          >
            {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
            {theme === "light" ? "暗色" : "浅色"}
          </button>
        </div>
      </header>

      <section className="signal-strip" aria-label="系统摘要">
        <div>
          <ClipboardList size={18} />
          <span>计划总数</span>
          <strong>{plansQuery.data?.total ?? 0}</strong>
        </div>
        <div>
          <ServerCog size={18} />
          <span>API</span>
          <strong>{plansQuery.error ? "异常" : "在线"}</strong>
        </div>
        <div>
          <Smartphone size={18} />
          <span>访问</span>
          <strong>同源 /ui</strong>
        </div>
      </section>

      {notice ? (
        <div className={`notice ${notice.tone}`} role="status">
          {notice.tone === "error" ? <AlertTriangle size={16} /> : <Check size={16} />}
          {notice.text}
        </div>
      ) : null}

      <div className="workspace-grid">
        <section className="workspace-panel list-panel">
          <div className="panel-heading">
            <div>
              <h2>计划队列</h2>
              <p>按更新时间排序，快速定位待审计划</p>
            </div>
            <span>{plans.length} 条</span>
          </div>
          {plansQuery.isLoading ? (
            <LoadingSkeleton label="正在加载计划队列" />
          ) : (
            <PlanList
              plans={plans}
              selectedPlanId={selectedPlanId}
              onSelect={setSelectedPlanId}
            />
          )}
        </section>

        <section className="workspace-panel detail-panel">
          <div className="panel-heading">
            <div>
              <h2>计划明细</h2>
              <p>核对任务项、代理与验证口径</p>
            </div>
            {selectedPlan ? <StatusBadge status={selectedPlan.status} /> : <span>未选择</span>}
          </div>
          <DetailPanel
            plan={selectedPlan}
            loading={selectedPlanQuery.isLoading}
            selectedPlanId={selectedPlanId}
          />
          <div className="editor-actions">
            <button
              className="primary-action"
              type="button"
              disabled={!selectedPlanId || selectedConfirmed || busy}
              onClick={() => updateMutation.mutate()}
            >
              <Save size={16} />
              保存草稿
            </button>
            <button
              className="confirm-action"
              type="button"
              disabled={!selectedPlanId || selectedConfirmed || busy}
              onClick={() => confirmMutation.mutate()}
            >
              <Check size={16} />
              确认计划
            </button>
          </div>
          {selectedPlan && editItems.length > 0 ? (
            <div className="editor-stack">
              {editItems.map((item, index) => (
                <ItemEditor
                  key={item.id}
                  item={item}
                  index={index}
                  disabled={selectedConfirmed}
                  onChange={(next) => updateEditItem(index, next)}
                  onRemove={() =>
                    setEditItems((items) => items.filter((_, itemIndex) => itemIndex !== index))
                  }
                />
              ))}
              <button
                className="secondary-action"
                type="button"
                disabled={selectedConfirmed}
                onClick={() => setEditItems((items) => [...items, createBlankItem(items.length + 1)])}
              >
                <Plus size={16} />
                添加计划项
              </button>
            </div>
          ) : null}
        </section>

        <section className="workspace-panel create-panel">
          <div className="panel-heading">
            <div>
              <h2>新建计划</h2>
              <p>创建草稿后可继续在中栏审阅</p>
            </div>
            <FilePenLine size={18} />
          </div>
          <div className="create-grid">
            <label>
              Plan ID
              <input value={draftPlanId} onChange={(event) => setDraftPlanId(event.target.value)} />
            </label>
            <label>
              Source Task
              <input
                value={draftSourceTaskId}
                onChange={(event) => setDraftSourceTaskId(event.target.value)}
              />
            </label>
          </div>
          <div className="editor-stack">
            {draftItems.map((item, index) => (
              <ItemEditor
                key={`${item.id}-${index}`}
                item={item}
                index={index}
                onChange={(next) => updateDraftItem(index, next)}
                onRemove={() =>
                  setDraftItems((items) => items.filter((_, itemIndex) => itemIndex !== index))
                }
              />
            ))}
          </div>
          <div className="editor-actions">
            <button
              className="secondary-action"
              type="button"
              onClick={() => setDraftItems((items) => [...items, createBlankItem(items.length + 1)])}
            >
              <Plus size={16} />
              添加任务项
            </button>
            <button
              className="primary-action"
              type="button"
              disabled={busy}
              onClick={() => createMutation.mutate()}
            >
              <ClipboardList size={16} />
              创建计划
            </button>
          </div>
        </section>
      </div>
    </main>
  );
}
