import { describe, expect, it } from "vitest";

import { parseFindings } from "./check_eslint_baseline.mjs";

describe("ESLint baseline parser", () => {
  it("counts findings by repository path and rule", () => {
    const output = JSON.stringify([
      {
        filePath: `${process.cwd()}/src/example.ts`,
        messages: [
          { ruleId: "no-empty" },
          { ruleId: "no-empty" },
          { ruleId: null },
        ],
      },
    ]);

    expect(parseFindings(output)).toEqual({
      "frontend/src/example.ts|no-empty": 2,
      "frontend/src/example.ts|unknown": 1,
    });
  });

  it("reports malformed formatter output", () => {
    expect(() => parseFindings("not-json")).toThrow("Could not parse ESLint JSON");
  });
});
