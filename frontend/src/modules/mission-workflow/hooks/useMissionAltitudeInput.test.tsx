import { act, renderHook } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { useMissionAltitudeInput } from "./useMissionAltitudeInput";

describe("useMissionAltitudeInput", () => {
  it("accepts digits, ignores other input, and commits valid altitude", () => {
    const addError = vi.fn();
    const { result } = renderHook(() => useMissionAltitudeInput({ addError }));

    act(() => result.current.handleAltitudeInputChange("42"));
    act(() => result.current.handleAltitudeInputChange("42m"));
    expect(result.current.altInput).toBe("42");

    act(() => result.current.normalizeAltitude());
    expect(result.current.alt).toBe(42);
    expect(addError).not.toHaveBeenCalled();
  });

  it("restores empty input and preserves a domain-specific range error", () => {
    const addError = vi.fn();
    const { result } = renderHook(() =>
      useMissionAltitudeInput({
        initialAltitude: 25,
        minAltitude: 20,
        maxAltitude: 30,
        validationMessage: "Photogrammetry altitude must be between 20 and 30 meters",
        addError,
      })
    );

    act(() => result.current.handleAltitudeInputChange(""));
    act(() => result.current.normalizeAltitude());
    expect(result.current.altInput).toBe("25");

    act(() => result.current.handleAltitudeInputChange("31"));
    act(() => result.current.normalizeAltitude());
    expect(result.current.alt).toBe(25);
    expect(addError).toHaveBeenCalledWith(
      "Photogrammetry altitude must be between 20 and 30 meters"
    );
  });
});
