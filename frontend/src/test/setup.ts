import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { toHaveNoViolations } from "jest-axe";
import { afterAll, afterEach, beforeAll, expect } from "vitest";
import { server } from "./msw/server";

expect.extend(toHaveNoViolations);
if (!window.URL.createObjectURL) {
  window.URL.createObjectURL = () => "blob:test-worker";
}
if (!window.URL.revokeObjectURL) {
  window.URL.revokeObjectURL = () => undefined;
}
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => {
  server.resetHandlers();
  cleanup();
});
afterAll(() => server.close());
