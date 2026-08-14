import { QueryClient } from "@tanstack/react-query";
import { describe, expect, it, vi } from "vitest";
import { agricultureKeys } from "./queryKeys";
import {
  agricultureRunPollInterval,
  createAgricultureRunRefetchInterval,
  isAgricultureQualityTerminal,
  isAgricultureRunActive,
  isAgricultureRunTerminal,
  readAgricultureRunStatus,
} from "./analysisLifecycle";

describe("agriculture analysis lifecycle helpers", () => {
  it("treats active run statuses as pollable", () => {
    expect(isAgricultureRunActive("queued")).toBe(true);
    expect(isAgricultureRunActive("running")).toBe(true);
    expect(isAgricultureRunActive("waiting_inference")).toBe(true);
  });

  it("treats terminal run statuses as non-pollable", () => {
    for (const status of [
      "completed",
      "failed",
      "cancelled",
      "blocked",
      "blocked_quality",
      "review",
    ]) {
      expect(isAgricultureRunTerminal(status)).toBe(true);
      expect(isAgricultureRunActive(status)).toBe(false);
    }
  });

  it("polls when run status is unknown in cache", () => {
    expect(isAgricultureRunActive(undefined)).toBe(true);
    expect(isAgricultureRunActive(null)).toBe(true);
  });

  it("stops quality polling on terminal quality states", () => {
    expect(isAgricultureQualityTerminal("pass")).toBe(true);
    expect(isAgricultureQualityTerminal("blocked_quality")).toBe(true);
    expect(isAgricultureQualityTerminal("running")).toBe(false);
  });

  it("respects document visibility for active runs", () => {
    const visibility = vi
      .spyOn(document, "visibilityState", "get")
      .mockReturnValue("hidden");
    expect(agricultureRunPollInterval("running", 5000)).toBe(false);
    visibility.mockRestore();
    expect(agricultureRunPollInterval("running", 5000)).toBe(5000);
  });

  it("reads cached run status for scoped polling", () => {
    const client = new QueryClient();
    client.setQueryData(agricultureKeys.analysisRun("run-1"), {
      id: "run-1",
      status: "completed",
    });

    expect(readAgricultureRunStatus(client, "run-1")).toBe("completed");

    const poll = createAgricultureRunRefetchInterval(client, "run-1", 5000);
    expect(poll()).toBe(false);

    client.setQueryData(agricultureKeys.analysisRun("run-1"), {
      id: "run-1",
      status: "running",
    });
    expect(poll()).toBe(5000);
  });
});
