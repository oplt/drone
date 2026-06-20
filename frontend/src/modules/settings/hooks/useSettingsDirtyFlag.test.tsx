import { act, renderHook } from "@testing-library/react";
import { expect, it } from "vitest";

import { useSettingsDirtyFlag } from "./useSettingsDirtyFlag";

it("tracks edits and resets only when marked clean", () => {
  const { result } = renderHook(() => useSettingsDirtyFlag());

  expect(result.current.dirty).toBe(false);

  act(() => result.current.markDirty());
  expect(result.current.dirty).toBe(true);

  act(() => result.current.markDirty());
  expect(result.current.dirty).toBe(true);

  act(() => result.current.markClean());
  expect(result.current.dirty).toBe(false);
});
