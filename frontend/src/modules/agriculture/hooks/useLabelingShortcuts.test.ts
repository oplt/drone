import { describe, expect, it } from "vitest";
import { isTypingTarget } from "./useLabelingShortcuts";

describe("labeling shortcut typing guards", () => {
  it("treats inputs, textareas, selects, and contentEditable as typing targets", () => {
    const input = document.createElement("input");
    const textarea = document.createElement("textarea");
    const select = document.createElement("select");
    const editable = document.createElement("div");
    editable.setAttribute("contenteditable", "true");
    const button = document.createElement("button");

    expect(isTypingTarget(input)).toBe(true);
    expect(isTypingTarget(textarea)).toBe(true);
    expect(isTypingTarget(select)).toBe(true);
    expect(isTypingTarget(editable)).toBe(true);
    expect(isTypingTarget(button)).toBe(false);
  });
});
