import { expect, test } from "@playwright/test";
import { mockAuthenticatedSession } from "../fixtures/auth";

test.describe("agriculture responsive and degraded-network states", () => {
  test("renders an empty-field state on mobile-sized viewport", async ({ page }) => {
    await page.setViewportSize({ width: 390, height: 844 });
    await mockAuthenticatedSession(page);
    await page.route("**/agriculture/fields/overview", async (route) => route.fulfill({ json: [] }));
    await page.goto("/dashboard/agriculture/fields");
    await expect(page.getByRole("heading", { name: "Agriculture fields" })).toBeVisible();
    await expect(page.getByText(/No agriculture fields/i)).toBeVisible();
  });

  test("surfaces retryable failure after slow/offline reconnect", async ({ page, context }) => {
    await mockAuthenticatedSession(page);
    await page.route("**/agriculture/fields/overview", async (route) => {
      await new Promise((resolve) => setTimeout(resolve, 1200));
      await route.fulfill({ status: 503, json: { detail: "temporary outage" } });
    });
    await page.goto("/dashboard/agriculture/fields");
    await expect(page.getByText(/unavailable|retry|failed/i)).toBeVisible({ timeout: 10_000 });
    await context.setOffline(true);
    await page.reload();
    await expect(page.getByText(/unavailable|retry|failed|loading/i)).toBeVisible();
    await context.setOffline(false);
  });
});
