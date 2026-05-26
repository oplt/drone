import { expect, test } from "@playwright/test";
import { mockAuthenticatedSession } from "../fixtures/auth";

test.describe("controlled flight mission path", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedSession(page);
    await page.route("**/auth/me", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ id: "e2e-user", email: "e2e@test.local", role: "operator" }),
      });
    });
    await page.route("**/api/**", async (route) => {
      const url = route.request().url();
      if (url.includes("/flights") || url.includes("/missions") || url.includes("/telemetry")) {
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify([]),
        });
        return;
      }
      await route.continue();
    });
  });

  test("loads controlled flight workflow shell when authenticated", async ({ page }) => {
    await page.route("**/alerts/**", async (route) => {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify([]),
      });
    });

    await page.goto("/dashboard/controlled");
    await expect(page).toHaveURL(/\/dashboard\/controlled/);
    await expect(
      page.getByText(/Controlled Flight|Missing Google Maps API Key/i),
    ).toBeVisible({ timeout: 60_000 });
  });
});
