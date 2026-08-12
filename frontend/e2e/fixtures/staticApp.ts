import { readFile } from "node:fs/promises";
import { extname, join, normalize } from "node:path";
import type { Page } from "@playwright/test";

const contentTypes: Record<string, string> = {
  ".css": "text/css",
  ".html": "text/html",
  ".js": "text/javascript",
  ".json": "application/json",
  ".png": "image/png",
  ".svg": "image/svg+xml",
  ".woff2": "font/woff2",
};

export async function serveBuiltAppWhenRequested(page: Page) {
  if (process.env.E2E_STATIC_BUILD !== "1") return;
  const root = join(process.cwd(), "dist");
  await page.route("http://app.test/**", async (route) => {
    const pathname = decodeURIComponent(new URL(route.request().url()).pathname);
    const relative = pathname.startsWith("/assets/") ? pathname.slice(1) : "index.html";
    const target = normalize(join(root, relative));
    if (!target.startsWith(root)) return route.fulfill({ status: 404, body: "" });
    try {
      await route.fulfill({
        status: 200,
        contentType: contentTypes[extname(target)] ?? "application/octet-stream",
        body: await readFile(target),
      });
    } catch {
      await route.fulfill({ status: 404, body: "" });
    }
  });
}
