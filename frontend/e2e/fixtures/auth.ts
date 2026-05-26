import type { Page, Route } from "@playwright/test";

export async function mockAuthenticatedSession(page: Page) {
  await page.route("**/auth/me", async (route: Route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: "e2e-user", email: "e2e@test.local" }),
    });
  });
  await page.route("**/auth/refresh", async (route: Route) => {
    await route.fulfill({ status: 204, body: "" });
  });
}

export async function mockGuestSession(page: Page) {
  await page.route("**/auth/me", async (route: Route) => {
    await route.fulfill({ status: 401, body: "" });
  });
  await page.route("**/auth/refresh", async (route: Route) => {
    await route.fulfill({ status: 401, body: "" });
  });
}
