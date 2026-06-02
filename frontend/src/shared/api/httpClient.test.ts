import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { ApiError } from "./apiError";
import { httpRequest, resolveApiUrl, shouldAttachBearerToken } from "./httpClient";
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

  it("does not treat session_present marker as Bearer auth", () => {
    expect(shouldAttachBearerToken("1")).toBe(false);
    expect(shouldAttachBearerToken("eyJhbGci.test.sig")).toBe(true);
    expect(shouldAttachBearerToken("sk-deadbeef_secret")).toBe(true);
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

  it("retries transient GET network failures", async () => {
    vi.useFakeTimers();
    let calls = 0;
    const originalFetch = window.fetch;
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        calls += 1;
        if (calls === 1) {
          throw new TypeError("ECONNREFUSED 127.0.0.1:8000");
        }
        return new Response(JSON.stringify({ id: "user-1" }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        });
      }),
    );

    try {
      const request = httpRequest<{ id: string }>("/auth/me", {
        skipUnauthorizedRedirect: true,
      });
      await vi.advanceTimersByTimeAsync(250);

      await expect(request).resolves.toEqual({ id: "user-1" });
      expect(calls).toBe(2);
    } finally {
      vi.stubGlobal("fetch", originalFetch);
      vi.useRealTimers();
    }
  });
});
