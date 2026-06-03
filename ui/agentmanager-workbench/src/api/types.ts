export type TaskPlanItemRequest = {
  id: string;
  title: string;
  description: string;
  priority: number;
  dependencies: string[];
  assignee: string;
  required_skills: string[];
  workdir: string;
  verification: string;
  metadata: Record<string, unknown>;
};

export type TaskPlanRequest = {
  plan_id: string;
  source_task_id: string;
  items: TaskPlanItemRequest[];
  temporary_roles?: string[];
  selected_templates?: string[];
  preferred_assignees?: string[];
  metadata?: Record<string, unknown>;
};

export type TaskPlanUpdateRequest = {
  items?: TaskPlanItemRequest[];
  metadata?: Record<string, unknown>;
};

export type TaskPlanItemResponse = TaskPlanItemRequest & {
  status: string;
};

export type TaskPlanResponse = {
  plan_id: string;
  source_task_id: string;
  items: TaskPlanItemResponse[];
  created_by: string;
  status: string;
  temporary_roles: string[];
  selected_templates: string[];
  preferred_assignees: string[];
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
};

export type TaskPlanSummary = {
  plan_id: string;
  source_task_id: string;
  status: string;
  items_count: number;
  updated_at: string;
};

export type TaskPlanListResponse = {
  task_plans: TaskPlanSummary[];
  total: number;
};
