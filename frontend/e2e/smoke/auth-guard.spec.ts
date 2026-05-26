import { expect, test } from "@playwright/test";
import { mockGuestSession } from "../fixtures/auth";

test.describe("authentication guard", () => {
  test("redirects unauthenticated users from dashboard to sign-in", async ({ page }) => {
    await mockGuestSession(page);
    await page.goto("/dashboard");
    await expect(page).toHaveURL(/\/signin$/);
  });
});
