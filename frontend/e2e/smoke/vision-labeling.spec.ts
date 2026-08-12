import { expect, test } from "@playwright/test";
import { mockAuthenticatedSession } from "../fixtures/auth";
import { serveBuiltAppWhenRequested } from "../fixtures/staticApp";
import {
  createVisionMockState,
  mockVisionWorkflow,
} from "../fixtures/vision";

test.describe("agriculture image labeling", () => {
  test("draws, edits, reviews, navigates, and reloads pixel boxes", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "Precision canvas interactions run on desktop Chromium.");
    await serveBuiltAppWhenRequested(page);
    await mockAuthenticatedSession(page);
    const state = createVisionMockState(true);
    await mockVisionWorkflow(page, state);
    await page.goto(
      "/dashboard/agriculture/vision-models/datasets/dataset-1/label",
    );

    await expect(page.getByText("Image 1")).toBeVisible();
    await expect(page.getByText("[1] ripe tomato")).toBeVisible();
    const canvas = page.getByTestId("annotation-canvas");
    const bounds = await canvas.boundingBox();
    expect(bounds).not.toBeNull();
    const box = bounds!;
    const start = { x: box.x + box.width * 0.3, y: box.y + box.height * 0.3 };
    const end = { x: box.x + box.width * 0.5, y: box.y + box.height * 0.5 };

    await page.mouse.move(start.x, start.y);
    await page.mouse.down();
    await page.mouse.move(end.x, end.y, { steps: 5 });
    await page.mouse.up();
    await expect(page.getByText("#1 ripe tomato")).toBeVisible();

    await page.keyboard.press("v");
    await page.mouse.move((start.x + end.x) / 2, (start.y + end.y) / 2);
    await page.mouse.down();
    await page.mouse.move(
      (start.x + end.x) / 2 + box.width * 0.06,
      (start.y + end.y) / 2 + box.height * 0.04,
      { steps: 5 },
    );
    await page.mouse.up();

    const movedEnd = {
      x: end.x + box.width * 0.06,
      y: end.y + box.height * 0.04,
    };
    await page.mouse.move(movedEnd.x, movedEnd.y);
    await page.mouse.down();
    await page.mouse.move(
      movedEnd.x + box.width * 0.05,
      movedEnd.y + box.height * 0.04,
      { steps: 5 },
    );
    await page.mouse.up();

    await page.getByText("[2] damaged tomato").click();
    await expect(page.getByText("#1 damaged tomato")).toBeVisible();
    await page.keyboard.press("Delete");
    await expect(page.getByText(/^#1 /)).toHaveCount(0);

    await page.keyboard.press("b");
    await page.mouse.move(box.x + box.width * 0.55, box.y + box.height * 0.35);
    await page.mouse.down();
    await page.mouse.move(box.x + box.width * 0.7, box.y + box.height * 0.55, { steps: 5 });
    await page.mouse.up();
    await expect(page.getByText("#1 damaged tomato")).toBeVisible();
    await page.getByRole("button", { name: "Mark reviewed" }).click();
    await expect(page.getByText("Saved")).toBeVisible();

    await page.getByRole("button", { name: "Next" }).click();
    await expect(page.getByText("2 / 2")).toBeVisible();
    await page.getByRole("button", { name: "Previous" }).click();
    await expect(page.getByText("#1 damaged tomato")).toBeVisible();
    await page.reload();
    await expect(page.getByText("#1 damaged tomato")).toBeVisible();
    await expect(page.getByRole("button", { name: "Reviewed" })).toBeVisible();

    expect(state.annotationRequests.some((request) => request.annotations.length === 0)).toBe(true);
    expect(state.annotationRequests.some((request) =>
      request.annotations.some((annotation) => annotation.class_id === "class-damaged"),
    )).toBe(true);
    const persisted = state.images[0].annotations[0];
    expect(persisted.x1).toBeGreaterThanOrEqual(0);
    expect(persisted.x2).toBeLessThanOrEqual(1000);
    expect(persisted.y2).toBeLessThanOrEqual(600);
  });
});
