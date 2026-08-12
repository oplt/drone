import { defineConfig, devices } from "@playwright/test";

const baseURL = process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:5173";
const mockAuth = process.env.E2E_MOCK_AUTH !== "0";
const useWebServer = process.env.PLAYWRIGHT_SKIP_WEBSERVER !== "1" && !process.env.PLAYWRIGHT_BASE_URL;
const chromiumExecutable = process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH;
const chromiumArgs = process.env.PLAYWRIGHT_CHROMIUM_ARGS?.split(" ").filter(Boolean);

export default defineConfig({
  testDir: "./e2e",
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 1 : 0,
  workers: process.env.CI ? 1 : undefined,
  reporter: process.env.CI ? "github" : "list",
  use: {
    baseURL,
    trace: "on-first-retry",
    launchOptions: chromiumExecutable
      ? { executablePath: chromiumExecutable, args: chromiumArgs }
      : undefined,
  },
  webServer: useWebServer ? {
    command: "npm run dev -- --host 127.0.0.1 --port 5173",
    url: baseURL,
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
    env: {
      ...process.env,
      E2E_MOCK_AUTH: mockAuth ? "1" : "0",
    },
  } : undefined,
  projects: [
    { name: "chromium", use: { ...devices["Desktop Chrome"] } },
    { name: "tablet", use: { ...devices["iPad (gen 9)"] } },
    { name: "mobile", use: { ...devices["Pixel 7"] } },
  ],
});
