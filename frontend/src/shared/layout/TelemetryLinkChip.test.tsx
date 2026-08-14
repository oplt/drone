import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import TelemetryLinkChip from "./TelemetryLinkChip";
import type { TelemetryLinkStatus } from "../../modules/mission-runtime/hooks/useTelemetryLinkStatus";

const linkStatus = vi.hoisted(() => ({
  current: {
    phase: "offline",
    label: "Telemetry offline",
    color: "error",
    ageSec: null,
    isConnected: false,
    reconnectAttempt: 0,
  } as TelemetryLinkStatus,
}));

vi.mock("../../modules/mission-runtime/hooks/useTelemetryLinkStatus", () => ({
  useTelemetryLinkStatus: () => linkStatus.current,
}));

function renderChip(compact = false) {
  return render(
    <ThemeProvider theme={createTheme()}>
      <TelemetryLinkChip compact={compact} />
    </ThemeProvider>,
  );
}

describe("TelemetryLinkChip", () => {
  beforeEach(() => {
    linkStatus.current = {
      phase: "offline",
      label: "Telemetry offline",
      color: "error",
      ageSec: null,
      isConnected: false,
      reconnectAttempt: 0,
    };
  });

  afterEach(() => {
    vi.clearAllMocks();
  });

  it("does not show success live when disconnected", () => {
    renderChip();
    expect(screen.getByLabelText("Telemetry offline")).toBeInTheDocument();
    expect(screen.queryByLabelText("Telemetry live")).not.toBeInTheDocument();
  });

  it("shows live only for live phase", () => {
    linkStatus.current = {
      phase: "live",
      label: "Telemetry live",
      color: "success",
      ageSec: 1,
      isConnected: true,
      reconnectAttempt: 0,
    };
    renderChip();
    expect(screen.getByLabelText("Telemetry live")).toBeInTheDocument();
  });

  it("shows stale distinctly from live", () => {
    linkStatus.current = {
      phase: "stale",
      label: "Telemetry stale (12s)",
      color: "warning",
      ageSec: 12,
      isConnected: true,
      reconnectAttempt: 0,
    };
    act(() => {
      renderChip(true);
    });
    expect(screen.getByLabelText("Telemetry stale (12s)")).toBeInTheDocument();
    expect(screen.getByText("Stale")).toBeInTheDocument();
  });
});
