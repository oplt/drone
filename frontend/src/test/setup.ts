import "@testing-library/jest-dom/vitest";
import { toHaveNoViolations } from "jest-axe";
import { afterAll, afterEach, beforeAll, expect } from "vitest";
import { server } from "./msw/server";

expect.extend(toHaveNoViolations);

if (!URL.createObjectURL) {
  URL.createObjectURL = () => "blob:test-object";
}
if (!URL.revokeObjectURL) {
  URL.revokeObjectURL = () => undefined;
}

beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());
