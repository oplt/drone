import { http, HttpResponse } from "msw";

export const authHandlers = [
  http.get("*/auth/me", ({ request }) => {
    const cookie = request.headers.get("cookie") ?? "";
    if (cookie.includes("session_present=1")) {
      return HttpResponse.json({ id: "test-user", email: "ops@test.local" });
    }
    return new HttpResponse(null, { status: 401 });
  }),
  http.post("*/auth/refresh", () => new HttpResponse(null, { status: 401 })),
  http.post("*/auth/logout", () => new HttpResponse(null, { status: 204 })),
];
