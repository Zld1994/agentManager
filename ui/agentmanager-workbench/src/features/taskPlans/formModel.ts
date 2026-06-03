import type { TaskPlanItemRequest, TaskPlanRequest, TaskPlanUpdateRequest } from "../../api/types";

export type EditableTaskPlanItem = {
  id: string;
  title: string;
  description: string;
  priority: number;
  dependenciesText: string;
  assignee: string;
  requiredSkillsText: string;
  workdir: string;
  verification: string;
};

export type EditablePlanDraft = {
  planId: string;
  sourceTaskId: string;
  items: EditableTaskPlanItem[];
};

export function createBlankItem(index: number): EditableTaskPlanItem {
  return {
    id: `item-${index}`,
    title: "",
    description: "",
    priority: 0,
    dependenciesText: "",
    assignee: "",
    requiredSkillsText: "",
    workdir: "",
    verification: ""
  };
}

export function parseCsv(value: string): string[] {
  return value
    .split(",")
    .map((entry) => entry.trim())
    .filter(Boolean);
}

export function updateItemField<K extends keyof EditableTaskPlanItem>(
  item: EditableTaskPlanItem,
  key: K,
  value: EditableTaskPlanItem[K]
): EditableTaskPlanItem {
  return {
    ...item,
    [key]: value
  };
}

function itemToRequest(item: EditableTaskPlanItem): TaskPlanItemRequest {
  return {
    id: item.id.trim(),
    title: item.title.trim(),
    description: item.description.trim(),
    priority: Number.isFinite(item.priority) ? item.priority : 0,
    dependencies: parseCsv(item.dependenciesText),
    assignee: item.assignee.trim(),
    required_skills: parseCsv(item.requiredSkillsText),
    workdir: item.workdir.trim(),
    verification: item.verification.trim(),
    metadata: {}
  };
}

export function buildCreatePlanPayload(draft: EditablePlanDraft): TaskPlanRequest {
  return {
    plan_id: draft.planId.trim(),
    source_task_id: draft.sourceTaskId.trim(),
    items: draft.items.map(itemToRequest)
  };
}

export function buildUpdatePlanPayload(items: EditableTaskPlanItem[]): TaskPlanUpdateRequest {
  return {
    items: items.map(itemToRequest)
  };
}

export function requestItemToEditable(item: TaskPlanItemRequest): EditableTaskPlanItem {
  return {
    id: item.id,
    title: item.title,
    description: item.description,
    priority: item.priority,
    dependenciesText: item.dependencies.join(", "),
    assignee: item.assignee,
    requiredSkillsText: item.required_skills.join(", "),
    workdir: item.workdir,
    verification: item.verification
  };
}
