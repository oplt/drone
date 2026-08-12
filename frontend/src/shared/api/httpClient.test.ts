import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "./apiError";
import { httpRequest, resolveApiUrl, shouldAttachBearerToken } from "./httpClient";
import { server } from "../../test/msw/server";
import { clearAppLogsForTests, getAppLogs } from "../logging";

describe("httpClient", () => {
  afterEach(() => {
    clearAppLogsForTests();
  });

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
    ).rejects.toMatchObject({
      message: "Video upload failed",
      code: "UPLOAD_FAILED",
    });
  });

  it("prefers the versioned error envelope over legacy detail", async () => {
    server.use(
      http.get("*/vision/models/missing", () =>
        HttpResponse.json(
          {
            detail: "Legacy message",
            error: {
              code: "VISION_NOT_FOUND",
              message: "Model version not found",
              fields: { version_id: "missing" },
              retryable: false,
              trace_id: "trace-1",
            },
          },
          { status: 404 },
        ),
      ),
    );

    await expect(
      httpRequest("/vision/models/missing", {
        skipUnauthorizedRedirect: true,
      }),
    ).rejects.toMatchObject({
      message: "Model version not found",
      detail: "Model version not found",
      code: "VISION_NOT_FOUND",
      details: { version_id: "missing" },
      requestId: "trace-1",
    });
  });

  it("preserves agriculture error codes and details from the stable envelope", async () => {
    server.use(
      http.post("*/agriculture/flights/start", () =>
        HttpResponse.json(
          {
            error: {
              code: "AGRICULTURE_CONTEXT_REQUIRED",
              message: "field_id and agriculture profile are required",
              details: { field_id: "required" },
              request_id: "req-agri-1",
            },
          },
          {
            status: 422,
            headers: { "X-Agriculture-Schema-Version": "agriculture.v1" },
          },
        ),
      ),
    );

    const error = await httpRequest("/agriculture/flights/start", {
      method: "POST",
      skipUnauthorizedRedirect: true,
    }).catch((caught: unknown) => caught);

    expect(error).toMatchObject({
      code: "AGRICULTURE_CONTEXT_REQUIRED",
      details: { field_id: "required" },
      schemaVersion: "agriculture.v1",
    });
  });

  it("attaches request ids and records failed API calls", async () => {
    let requestId: string | null = null;
    let correlationId: string | null = null;
    server.use(
      http.get("*/telemetry/status", ({ request }) => {
        requestId = request.headers.get("X-Request-ID");
        correlationId = request.headers.get("X-Correlation-ID");
        return HttpResponse.json(
          {
            error: {
              code: "INTERNAL_ERROR",
              message: "Telemetry status failed",
              request_id: requestId,
            },
          },
          {
            status: 500,
            headers: requestId ? { "X-Request-ID": requestId } : undefined,
          },
        );
      }),
    );

    const error = await httpRequest("/telemetry/status", {
      skipUnauthorizedRedirect: true,
    }).catch((caught: unknown) => caught);

    expect(requestId).toBeTruthy();
    expect(correlationId).toBeTruthy();
    expect(error).toMatchObject({ requestId });
    expect(getAppLogs()[0]).toMatchObject({
      level: "error",
      source: "api",
      requestId,
      message: "Telemetry status failed",
    });
  });

  it("refreshes the session and retries a non-auth 401 once", async () => {
    let overviewCalls = 0;
    let refreshCalls = 0;
    server.use(
      http.get("*/analytics/overview", () => {
        overviewCalls += 1;
        if (overviewCalls === 1) {
          return new HttpResponse(null, { status: 401 });
        }
        return HttpResponse.json({ summary: { active_flights: 3 } });
      }),
      http.post("*/auth/refresh", () => {
        refreshCalls += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await expect(
      httpRequest<{ summary: { active_flights: number } }>(
        "/analytics/overview",
        { skipUnauthorizedRedirect: true },
      ),
    ).resolves.toEqual({ summary: { active_flights: 3 } });

    expect(refreshCalls).toBe(1);
    expect(overviewCalls).toBe(2);
    expect(getAppLogs()).toHaveLength(0);
  });

  it("shares one refresh request across concurrent non-auth 401s", async () => {
    let refreshCalls = 0;
    const seenPaths: string[] = [];
    server.use(
      http.get("*/telemetry/status", ({ request }) => {
        seenPaths.push(new URL(request.url).pathname);
        if (seenPaths.filter((path) => path === "/telemetry/status").length === 1) {
          return new HttpResponse(null, { status: 401 });
        }
        return HttpResponse.json({ ok: true });
      }),
      http.get("*/warehouse/preflight", ({ request }) => {
        seenPaths.push(new URL(request.url).pathname);
        if (seenPaths.filter((path) => path === "/warehouse/preflight").length === 1) {
          return new HttpResponse(null, { status: 401 });
        }
        return HttpResponse.json({ ready_to_fly: true });
      }),
      http.post("*/auth/refresh", async () => {
        refreshCalls += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await expect(
      Promise.all([
        httpRequest("/telemetry/status", { skipUnauthorizedRedirect: true }),
        httpRequest("/warehouse/preflight", { skipUnauthorizedRedirect: true }),
      ]),
    ).resolves.toEqual([{ ok: true }, { ready_to_fly: true }]);

    expect(refreshCalls).toBe(1);
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
