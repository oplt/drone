import { existsSync } from "node:fs";
import { chromium, expect, test } from "@playwright/test";
import { mockAuthenticatedSession } from "../fixtures/auth";

const chromiumExecutable =
  process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH ?? chromium.executablePath();

test.skip(
  !existsSync(chromiumExecutable),
  "Chromium is not installed in this environment",
);

test("field list exposes the setup wizard", async ({ page }) => {
  await mockAuthenticatedSession(page);
  await page.route("**/agriculture/fields/overview", (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: "[]" }),
  );

  await page.goto("/dashboard/agriculture/fields");

  await expect(
    page.getByRole("heading", { name: "Agriculture fields" }),
  ).toBeVisible();
  await expect(page.getByRole("region", { name: "Set up a field" })).toBeVisible();
});
