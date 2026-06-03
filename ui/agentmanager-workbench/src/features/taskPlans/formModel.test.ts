import { describe, expect, it } from "vitest";
import {
  buildCreatePlanPayload,
  createBlankItem,
  parseCsv,
  updateItemField
} from "./formModel";

describe("task plan form model", () => {
  it("creates stable blank items for editable task-plan rows", () => {
    const item = createBlankItem(3);

    expect(item.id).toBe("item-3");
    expect(item.title).toBe("");
    expect(item.verification).toBe("");
    expect(item.dependenciesText).toBe("");
  });

  it("parses comma-separated fields without empty values", () => {
    expect(parseCsv("build, test,, review ")).toEqual(["build", "test", "review"]);
  });

  it("builds a create payload from editable rows", () => {
    const item = updateItemField(createBlankItem(1), "title", "Implement API client");
    const payload = buildCreatePlanPayload({
      planId: "plan-ui",
      sourceTaskId: "task-root",
      items: [
        {
          ...item,
          verification: "npm run test",
          dependenciesText: "item-0",
          requiredSkillsText: "typescript,react"
        }
      ]
    });

    expect(payload).toEqual({
      plan_id: "plan-ui",
      source_task_id: "task-root",
      items: [
        {
          id: "item-1",
          title: "Implement API client",
          description: "",
          priority: 0,
          dependencies: ["item-0"],
          assignee: "",
          required_skills: ["typescript", "react"],
          workdir: "",
          verification: "npm run test",
          metadata: {}
        }
      ]
    });
  });
});
