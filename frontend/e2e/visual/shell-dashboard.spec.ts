import { expect, test } from "@playwright/test";
import { mockAuthenticatedSession } from "../fixtures/auth";

/**
 * Optional visual baselines for shell + dashboard (light/dark).
 * Run locally after reviewing screenshots:
 *   E2E_VISUAL=1 npx playwright test e2e/visual/shell-dashboard.spec.ts --project=chromium
 * CI job: frontend-visual (workflow_dispatch only).
 */
test.describe("shell visual baselines", () => {
  test.skip(!process.env.E2E_VISUAL, "Set E2E_VISUAL=1 to capture/compare baselines");

  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedSession(page);
    await page.route("**/alerts**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
    await page.route("**/api/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });
  });

  test("operations shell dashboard light", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "light" });
    await page.goto("/dashboard");
    await expect(page.getByText(/Live command overview/i)).toBeVisible({ timeout: 60_000 });
    await expect(page).toHaveScreenshot("ops-shell-dashboard-light.png", {
      fullPage: true,
      maxDiffPixelRatio: 0.02,
    });
  });

  test("operations shell dashboard dark", async ({ page }) => {
    await page.emulateMedia({ colorScheme: "dark" });
    await page.goto("/dashboard");
    await expect(page.getByText(/Live command overview/i)).toBeVisible({ timeout: 60_000 });
    await expect(page).toHaveScreenshot("ops-shell-dashboard-dark.png", {
      fullPage: true,
      maxDiffPixelRatio: 0.02,
    });
  });
});
