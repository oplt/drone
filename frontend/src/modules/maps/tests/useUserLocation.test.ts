import { act, renderHook, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { useUserLocation } from "../hooks/useUserLocation";

type SuccessCallback = PositionCallback;
type ErrorCallback = PositionErrorCallback;

function installGeolocation() {
  let success: SuccessCallback | undefined;
  let failure: ErrorCallback | undefined;
  const getCurrentPosition = vi.fn(
    (nextSuccess: SuccessCallback, nextFailure?: ErrorCallback) => {
      success = nextSuccess;
      failure = nextFailure;
    },
  );
  Object.defineProperty(navigator, "geolocation", {
    configurable: true,
    value: { getCurrentPosition },
  });
  return {
    getCurrentPosition,
    succeed: (latitude = 50.85, longitude = 4.35) =>
      success?.({ coords: { latitude, longitude } } as GeolocationPosition),
    fail: (code: number, message: string) =>
      failure?.({ code, message, PERMISSION_DENIED: 1, POSITION_UNAVAILABLE: 2, TIMEOUT: 3 } as GeolocationPositionError),
  };
}

afterEach(() => {
  vi.restoreAllMocks();
  Object.defineProperty(navigator, "geolocation", { configurable: true, value: undefined });
});

describe("useUserLocation", () => {
  it("returns coordinates and uses normalized browser options", async () => {
    const geo = installGeolocation();
    const { result } = renderHook(() => useUserLocation());

    expect(geo.getCurrentPosition).toHaveBeenCalledWith(
      expect.any(Function),
      expect.any(Function),
      { enableHighAccuracy: true, timeout: 5000, maximumAge: 0 },
    );
    act(() => geo.succeed(51, 5));

    await waitFor(() => expect(result.current.userCenter).toEqual({ lat: 51, lng: 5 }));
    expect(result.current.loadingLocation).toBe(false);
    expect(result.current.locationError).toBeNull();
  });

  it.each([
    [1, "Location access denied"],
    [3, "Location request timed out"],
  ])("exposes geolocation error code %s", async (code, message) => {
    const geo = installGeolocation();
    const policy = vi.fn(() => message);
    const { result } = renderHook(() => useUserLocation({ onLocationError: policy }));

    act(() => geo.fail(code, "browser error"));

    await waitFor(() => expect(result.current.locationError).toBe(message));
    expect(result.current.loadingLocation).toBe(false);
    expect(policy).toHaveBeenCalledWith(expect.objectContaining({ code }));
  });

  it("finishes with an unsupported-browser error", async () => {
    const warn = vi.spyOn(console, "warn").mockImplementation(() => undefined);
    const { result } = renderHook(() => useUserLocation());

    await waitFor(() => expect(result.current.loadingLocation).toBe(false));
    expect(result.current.locationError).toBe("Geolocation is not supported by this browser.");
    expect(warn).toHaveBeenCalledOnce();
  });

  it("requests only once across rerenders and manual calls", () => {
    const geo = installGeolocation();
    const { result, rerender } = renderHook(() => useUserLocation());

    rerender();
    act(() => result.current.requestLocation());
    expect(geo.getCurrentPosition).toHaveBeenCalledOnce();
  });

  it("ignores callbacks after unmount", () => {
    const geo = installGeolocation();
    const consoleError = vi.spyOn(console, "error").mockImplementation(() => undefined);
    const { unmount } = renderHook(() => useUserLocation());

    unmount();
    act(() => geo.succeed());
    act(() => geo.fail(3, "late timeout"));
    expect(consoleError).not.toHaveBeenCalled();
  });
});
