import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it } from "vitest";
import { logout, verifySession } from "../api/sessionApi";
import { server } from "../../../test/msw/server";

describe("verifySession", () => {
  afterEach(() => {
    document.cookie = "session_present=; Max-Age=0; path=/";
  });

  it("returns true when /auth/me succeeds", async () => {
    server.use(
      http.get("*/auth/me", () =>
        HttpResponse.json({ id: "user-1", email: "ops@test.local" }),
      ),
    );

    await expect(verifySession()).resolves.toBe(true);
  });

  it("returns true after refresh then successful /auth/me", async () => {
    let meCalls = 0;
    server.use(
      http.get("*/auth/me", () => {
        meCalls += 1;
        if (meCalls === 1) {
          return new HttpResponse(null, { status: 401 });
        }
        return HttpResponse.json({ id: "user-1" });
      }),
      http.post("*/auth/refresh", () => new HttpResponse(null, { status: 204 })),
    );

    await expect(verifySession()).resolves.toBe(true);
  });

  it("returns false and clears marker when refresh fails", async () => {
    document.cookie = "session_present=1; path=/";
    server.use(
      http.get("*/auth/me", () => new HttpResponse(null, { status: 401 })),
      http.post("*/auth/refresh", () => new HttpResponse(null, { status: 401 })),
    );

    await expect(verifySession()).resolves.toBe(false);
    expect(document.cookie.includes("session_present=1")).toBe(false);
  });
});

describe("logout", () => {
  it("calls logout endpoint and clears session marker", async () => {
    document.cookie = "session_present=1; path=/";
    let logoutCalled = false;
    server.use(
      http.post("*/auth/logout", () => {
        logoutCalled = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    await logout();
    expect(logoutCalled).toBe(true);
    expect(document.cookie.includes("session_present=1")).toBe(false);
  });
});
