import { http, HttpResponse } from "msw";
import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { axe } from "jest-axe";
import { Route, Routes } from "react-router-dom";
import { ProtectedRoute } from "./ProtectedRoute";
import { server } from "../../test/msw/server";
import { renderWithProviders } from "../../test/renderWithProviders";

describe("ProtectedRoute", () => {
  it("redirects guests to sign-in", async () => {
    server.use(
      http.get("*/auth/me", () => new HttpResponse(null, { status: 401 })),
      http.post("*/auth/refresh", () => new HttpResponse(null, { status: 401 })),
    );

    renderWithProviders(
      <Routes>
        <Route
          path="/dashboard"
          element={
            <ProtectedRoute>
              <div>Secret mission console</div>
            </ProtectedRoute>
          }
        />
        <Route path="/signin" element={<div>Sign in page</div>} />
      </Routes>,
      { router: { initialEntries: ["/dashboard"] } },
    );

    expect(await screen.findByText("Sign in page")).toBeInTheDocument();
    expect(screen.queryByText("Secret mission console")).not.toBeInTheDocument();
  });

  it("renders children for authenticated sessions", async () => {
    server.use(
      http.get("*/auth/me", () => HttpResponse.json({ id: "user-1" })),
    );

    const { container } = renderWithProviders(
      <ProtectedRoute>
        <div>Secret mission console</div>
      </ProtectedRoute>,
      { router: { initialEntries: ["/dashboard"] } },
    );

    expect(await screen.findByText("Secret mission console")).toBeInTheDocument();
    const results = await axe(container);
    expect(results).toHaveNoViolations();
  });
});
