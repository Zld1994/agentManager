import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "./client";

describe("createApiClient", () => {
  it("sends bearer tokens and lists task plan summaries", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          task_plans: [
            {
              plan_id: "plan-1",
              source_task_id: "task-1",
              status: "draft",
              items_count: 2,
              updated_at: "2026-06-03T10:00:00Z"
            }
          ],
          total: 1
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const client = createApiClient({
      tokenProvider: () => "secret-token",
      fetchImpl
    });

    const result = await client.listTaskPlans();

    expect(result.total).toBe(1);
    expect(result.task_plans[0].plan_id).toBe("plan-1");
    expect(fetchImpl).toHaveBeenCalledWith(
      "/task-plans",
      expect.objectContaining({
        headers: expect.objectContaining({
          Authorization: "Bearer secret-token"
        })
      })
    );
  });

  it("turns non-ok JSON responses into ApiError", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(JSON.stringify({ detail: "Cannot update a confirmed task plan" }), {
        status: 409,
        headers: { "Content-Type": "application/json" }
      })
    );

    const client = createApiClient({ fetchImpl });

    await expect(
      client.updateTaskPlan("plan-1", {
        items: []
      })
    ).rejects.toMatchObject({
      status: 409,
      detail: "Cannot update a confirmed task plan"
    });
    expect(ApiError).toBeDefined();
  });

  it("posts confirm requests to the selected plan", async () => {
    const fetchImpl = vi.fn().mockResolvedValue(
      new Response(
        JSON.stringify({
          plan_id: "plan-1",
          source_task_id: "task-1",
          status: "confirmed",
          items: [],
          created_at: "2026-06-03T10:00:00Z",
          updated_at: "2026-06-03T10:01:00Z"
        }),
        { status: 200, headers: { "Content-Type": "application/json" } }
      )
    );

    const client = createApiClient({ fetchImpl });

    await client.confirmTaskPlan("plan-1");

    expect(fetchImpl).toHaveBeenCalledWith(
      "/task-plans/plan-1/confirm",
      expect.objectContaining({ method: "POST" })
    );
  });
});
