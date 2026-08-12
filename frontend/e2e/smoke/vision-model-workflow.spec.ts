import { expect, test } from "@playwright/test";
import { mockAuthenticatedSession } from "../fixtures/auth";
import { serveBuiltAppWhenRequested } from "../fixtures/staticApp";
import {
  createVisionMockState,
  mockVisionWorkflow,
} from "../fixtures/vision";

test.describe("agriculture vision model workflow", () => {
  test("creates data, labels, trains, evaluates, deploys, and analyzes tracked small objects", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "chromium", "The complete workflow runs once on desktop Chromium.");
    await serveBuiltAppWhenRequested(page);
    await mockAuthenticatedSession(page);
    const state = createVisionMockState();
    await mockVisionWorkflow(page, state);
    await page.goto("/dashboard/agriculture/vision-models");

    await page.getByRole("button", { name: "New project" }).click();
    await page.getByLabel("Project name").fill("Tomato field detector");
    await page.getByLabel("Crop").fill("tomato");
    await page.getByLabel("Classes (comma separated)").fill("ripe tomato, damaged tomato");
    await page.getByRole("button", { name: "Create project" }).click();
    await expect(page.getByText("Tomato field detector").first()).toBeVisible();

    await page.getByRole("button", { name: "Create dataset" }).click();
    await expect(page.getByText("Upload images")).toBeVisible();
    await page.locator('input[accept*="image/jpeg"]').setInputFiles([
      { name: "tomato-1.jpg", mimeType: "image/jpeg", buffer: Buffer.from("one") },
      { name: "tomato-2.jpg", mimeType: "image/jpeg", buffer: Buffer.from("two") },
      { name: "tomato-3.jpg", mimeType: "image/jpeg", buffer: Buffer.from("three") },
    ]);
    await expect(page.getByText(/Added 3; skipped 0 duplicates/i)).toBeVisible();
    await page.getByRole("button", { name: "Open labeling workspace" }).click();

    const canvas = page.getByTestId("annotation-canvas");
    const bounds = await canvas.boundingBox();
    expect(bounds).not.toBeNull();
    await page.mouse.move(bounds!.x + bounds!.width * 0.3, bounds!.y + bounds!.height * 0.3);
    await page.mouse.down();
    await page.mouse.move(bounds!.x + bounds!.width * 0.5, bounds!.y + bounds!.height * 0.55, { steps: 5 });
    await page.mouse.up();
    await expect(page.getByText("#1 ripe tomato")).toBeVisible();
    await page.getByRole("button", { name: "Mark reviewed" }).click();
    await expect(page.getByText("Saved")).toBeVisible();
    await page.getByRole("button", { name: "Close" }).click();

    await page.getByRole("tab", { name: "Train" }).click();
    await expect(page.getByText(/Dataset is ready/i)).toBeVisible();
    await page.getByRole("button", { name: "Start training" }).click();
    await expect(page.getByText("Evaluation completed")).toBeVisible();
    await page.reload();
    await page.getByRole("tab", { name: "Evaluation" }).click();
    await page.getByRole("button", { name: "View evaluation" }).click();
    await expect(page.getByText("91.3%")).toBeVisible();
    await expect(page.getByText("ripe tomato")).toBeVisible();
    await page.getByRole("button", { name: "Deploy candidate" }).click();
    await page.getByRole("button", { name: "Confirm deployment" }).click();
    await expect.poll(() => state.models[0]?.status).toBe("production");

    await page.goto("/dashboard/video-analysis");
    await page.locator('input[accept="video/*"]').setInputFiles({
      name: "tomato-flight.mp4",
      mimeType: "video/mp4",
      buffer: Buffer.from("video"),
    });
    await page.getByRole("button", { name: "Upload video" }).click();
    await expect(page.getByText("Upload ready for analysis.")).toBeVisible();
    await page.getByRole("tab", { name: "Inference" }).click();
    await page.getByLabel("Model").click();
    await page.getByRole("option", { name: /Tomato field detector · v1 · tomato/i }).click();
    await page.getByRole("switch", { name: "Track objects" }).click();
    await page.getByRole("switch", { name: "Small-object mode" }).click();
    await page.getByRole("button", { name: "Run analysis" }).click();

    await expect(page.getByText("Unique tracked objects")).toBeVisible();
    await expect(page.getByText(/Tracking enabled · Small-object mode enabled/i)).toBeVisible();
    expect(state.lastVideoPayload).toMatchObject({
      model_version_id: "version-1",
      tracking_enabled: true,
      tracker_type: "bytetrack",
      small_object_mode: true,
    });
  });
});
