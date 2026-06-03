import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "./App";
import { ApiClientContext, createApiClient } from "./api/client";

function renderApp(fetchImpl = vi.fn().mockResolvedValue(
  new Response(JSON.stringify({ task_plans: [], total: 0 }), {
    status: 200,
    headers: { "Content-Type": "application/json" }
  })
)) {
  const apiClient = createApiClient({ fetchImpl });

  return render(
    <ApiClientContext.Provider value={apiClient}>
      <QueryClientProvider client={new QueryClient()}>
        <App />
      </QueryClientProvider>
    </ApiClientContext.Provider>
  );
}

describe("App", () => {
  afterEach(() => {
    cleanup();
    window.sessionStorage.clear();
  });

  it("renders task plan summaries from the API", async () => {
    renderApp(
      vi.fn().mockResolvedValue(
        new Response(
          JSON.stringify({
            task_plans: [
              {
                plan_id: "plan-ui",
                source_task_id: "task-root",
                status: "draft",
                items_count: 3,
                updated_at: "2026-06-03T10:00:00Z"
              }
            ],
            total: 1
          }),
          { status: 200, headers: { "Content-Type": "application/json" } }
        )
      )
    );

    await waitFor(() => expect(screen.getByText("plan-ui")).toBeInTheDocument());
    expect(screen.getByText("来源：task-root")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "确认计划" })).toBeDisabled();
  });

  it("switches the workbench theme from the toolbar", async () => {
    const user = userEvent.setup();
    renderApp();

    const shell = screen.getByRole("main");
    expect(shell).toHaveAttribute("data-theme", "light");

    await user.click(screen.getByRole("button", { name: "切换为暗色主题" }));

    expect(shell).toHaveAttribute("data-theme", "dark");
    expect(screen.getByRole("button", { name: "切换为浅色主题" })).toBeInTheDocument();
  });
});
