import { expect, test } from "@playwright/test";
import { mockAuthenticatedSession } from "../fixtures/auth";

async function stubOpsApis(page: import("@playwright/test").Page) {
  await page.route("**/auth/me", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        id: "e2e-user",
        email: "e2e@test.local",
        role: "operator",
      }),
    });
  });
  await page.route("**/alerts**", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify([
        {
          id: 1,
          title: "Link degraded",
          message: "Packet age high",
          severity: "critical",
          status: "open",
          last_triggered_at: "2026-08-01T12:00:00Z",
        },
      ]),
    });
  });
  await page.route("**/api/**", async (route) => {
    const url = route.request().url();
    if (
      url.includes("/flights") ||
      url.includes("/missions") ||
      url.includes("/telemetry") ||
      url.includes("/system") ||
      url.includes("/overview") ||
      url.includes("/fleet")
    ) {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify(url.includes("/overview") ? {} : []),
      });
      return;
    }
    await route.continue();
  });
}

test.describe("ops primary journey smoke", () => {
  test.beforeEach(async ({ page }) => {
    await mockAuthenticatedSession(page);
    await stubOpsApis(page);
  });

  test("dashboard alerts → task map → fleet telemetry", async ({ page }) => {
    await page.goto("/dashboard");
    await expect(page.getByText(/Live command overview|Needs attention/i)).toBeVisible({
      timeout: 60_000,
    });
    await expect(page.getByText(/Alerts|Link degraded|No open alerts/i).first()).toBeVisible();

    await page.goto("/dashboard/controlled");
    await expect(page).toHaveURL(/\/dashboard\/controlled/);
    await expect(
      page.getByText(/Controlled Flight|Map layers|Missing Google Maps API Key/i).first(),
    ).toBeVisible({ timeout: 60_000 });

    await page.goto("/dashboard/fleet");
    await expect(page.getByText(/Fleet connectivity|Telemetry stream|Battery/i).first()).toBeVisible({
      timeout: 60_000,
    });
  });

  test("mobile navbar opens alert drawer", async ({ page }, testInfo) => {
    test.skip(testInfo.project.name !== "mobile", "mobile viewport only");
    await page.goto("/dashboard");
    await expect(page.getByLabel("Open notifications")).toBeVisible({ timeout: 60_000 });
    await page.getByLabel("Open notifications").click();
    await expect(page.getByText(/Link degraded|No open alerts|Alerts/i).first()).toBeVisible();
  });
});
