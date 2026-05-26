import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { ApiError } from "./apiError";
import { httpRequest, resolveApiUrl } from "./httpClient";
import { server } from "../../test/msw/server";

describe("httpClient", () => {
  it("resolves relative API paths", () => {
    expect(resolveApiUrl("/analytics/overview")).toBe("/analytics/overview");
  });

  it("parses JSON success responses", async () => {
    server.use(
      http.get("*/analytics/overview", () =>
        HttpResponse.json({ summary: { active_flights: 2 } }),
      ),
    );

    const data = await httpRequest<{ summary: { active_flights: number } }>(
      "/analytics/overview",
      { skipUnauthorizedRedirect: true },
    );
    expect(data.summary.active_flights).toBe(2);
  });

  it("throws ApiError for failed responses", async () => {
    server.use(
      http.get("*/analytics/overview", () =>
        HttpResponse.json({ detail: "Forbidden" }, { status: 403 }),
      ),
    );

    await expect(
      httpRequest("/analytics/overview", { skipUnauthorizedRedirect: true }),
    ).rejects.toBeInstanceOf(ApiError);
  });

  it("surfaces structured backend error messages", async () => {
    server.use(
      http.post("*/video-analysis/videos", () =>
        HttpResponse.json(
          { error: { code: "UPLOAD_FAILED", message: "Video upload failed" } },
          { status: 500 },
        ),
      ),
    );

    await expect(
      httpRequest("/video-analysis/videos", {
        method: "POST",
        skipUnauthorizedRedirect: true,
      }),
    ).rejects.toMatchObject({ message: "Video upload failed" });
  });
});
