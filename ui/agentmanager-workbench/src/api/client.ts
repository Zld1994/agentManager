import { createContext, useContext } from "react";
import type {
  TaskPlanListResponse,
  TaskPlanRequest,
  TaskPlanResponse,
  TaskPlanUpdateRequest
} from "./types";

type FetchLike = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export class ApiError extends Error {
  status: number;
  detail: string;

  constructor(status: number, detail: string) {
    super(detail);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

export type ApiClient = {
  listTaskPlans: () => Promise<TaskPlanListResponse>;
  getTaskPlan: (planId: string) => Promise<TaskPlanResponse>;
  createTaskPlan: (payload: TaskPlanRequest) => Promise<TaskPlanResponse>;
  updateTaskPlan: (
    planId: string,
    payload: TaskPlanUpdateRequest
  ) => Promise<TaskPlanResponse>;
  confirmTaskPlan: (planId: string) => Promise<TaskPlanResponse>;
};

export type ApiClientOptions = {
  baseUrl?: string;
  tokenProvider?: () => string;
  fetchImpl?: FetchLike;
};

const defaultTokenProvider = () => window.sessionStorage.getItem("agentmanager.apiToken") ?? "";

async function readJson(response: Response): Promise<unknown> {
  const contentType = response.headers.get("Content-Type") ?? "";
  if (!contentType.includes("application/json")) {
    return undefined;
  }
  return response.json();
}

function resolveUrl(baseUrl: string, path: string) {
  if (!baseUrl) {
    return path;
  }
  return `${baseUrl.replace(/\/$/, "")}${path}`;
}

export function createApiClient({
  baseUrl = "",
  tokenProvider = defaultTokenProvider,
  fetchImpl = fetch
}: ApiClientOptions = {}): ApiClient {
  async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
    const token = tokenProvider();
    const normalizedHeaders = new Headers(init.headers);
    const headers: Record<string, string> = {};
    normalizedHeaders.forEach((value, key) => {
      headers[key] = value;
    });
    if (init.body && !normalizedHeaders.has("Content-Type")) {
      headers["Content-Type"] = "application/json";
    }
    if (token) {
      headers.Authorization = `Bearer ${token}`;
    }

    const response = await fetchImpl(resolveUrl(baseUrl, path), {
      ...init,
      headers
    });
    const body = await readJson(response);

    if (!response.ok) {
      const detail =
        typeof body === "object" &&
        body !== null &&
        "detail" in body &&
        typeof body.detail === "string"
          ? body.detail
          : response.statusText || "Request failed";
      throw new ApiError(response.status, detail);
    }

    return body as T;
  }

  return {
    listTaskPlans: () => request<TaskPlanListResponse>("/task-plans"),
    getTaskPlan: (planId) => request<TaskPlanResponse>(`/task-plans/${planId}`),
    createTaskPlan: (payload) =>
      request<TaskPlanResponse>("/task-plans", {
        method: "POST",
        body: JSON.stringify(payload)
      }),
    updateTaskPlan: (planId, payload) =>
      request<TaskPlanResponse>(`/task-plans/${planId}`, {
        method: "PUT",
        body: JSON.stringify(payload)
      }),
    confirmTaskPlan: (planId) =>
      request<TaskPlanResponse>(`/task-plans/${planId}/confirm`, {
        method: "POST"
      })
  };
}

export const ApiClientContext = createContext<ApiClient>(createApiClient());

export function useApiClient() {
  return useContext(ApiClientContext);
}
