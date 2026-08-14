import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { ThemeProvider, createTheme } from "@mui/material/styles";
import { describe, expect, it, vi } from "vitest";
import { CaptureMetadataEditor } from "./CaptureMetadataEditor";
import type { VideoAsset } from "../types";

const mutateAsync = vi.fn();

vi.mock("../hooks", () => ({
  usePatchCaptureMetadata: () => ({
    mutateAsync,
    isPending: false,
    error: null,
  }),
}));

const video: VideoAsset = {
  id: "vid-1",
  original_filename: "flight.mp4",
  status: "ready",
  created_at: "2026-08-01T00:00:00Z",
  captured_at: null,
  capture_timezone: null,
  sync_offset_seconds: 0,
};

describe("CaptureMetadataEditor", () => {
  it("validates sync offset and saves operator capture metadata", async () => {
    const user = userEvent.setup();
    mutateAsync.mockResolvedValue({ ...video, capture_timezone: "UTC" });
    const onUpdated = vi.fn();

    render(
      <ThemeProvider theme={createTheme()}>
        <CaptureMetadataEditor video={video} onUpdated={onUpdated} />
      </ThemeProvider>,
    );

    const offset = screen.getByLabelText(/Sync offset/i);
    await user.clear(offset);
    await user.type(offset, "not-a-number");
    await user.click(screen.getByRole("button", { name: /Save capture metadata/i }));
    expect(mutateAsync).not.toHaveBeenCalled();

    await user.clear(offset);
    await user.type(offset, "1.5");
    await user.type(screen.getByLabelText(/Timezone/i), "UTC");
    await user.click(screen.getByRole("button", { name: /Save capture metadata/i }));

    expect(mutateAsync).toHaveBeenCalledWith({
      videoId: "vid-1",
      patch: { sync_offset_seconds: 1.5, capture_timezone: "UTC" },
    });
    expect(onUpdated).toHaveBeenCalled();
  });
});
