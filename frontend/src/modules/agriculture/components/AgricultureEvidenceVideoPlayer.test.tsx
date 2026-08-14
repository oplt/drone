import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AgricultureEvidenceVideoPlayer } from "./AgricultureEvidenceVideoPlayer";

vi.mock("../../video-analysis/api", () => ({
  buildMissionVideoStreamUrl: (id: string) => `/stream/${id}`,
}));

describe("AgricultureEvidenceVideoPlayer", () => {
  const pause = vi.fn();
  const play = vi.fn(() => Promise.resolve());

  beforeEach(() => {
    pause.mockClear();
    play.mockClear();
    Object.defineProperty(HTMLMediaElement.prototype, "pause", { configurable: true, value: pause });
    Object.defineProperty(HTMLMediaElement.prototype, "play", { configurable: true, value: play });
  });

  it("seeks to canonical time and can play a bounded evidence window", async () => {
    const user = userEvent.setup();
    render(<AgricultureEvidenceVideoPlayer videoId="video-1" timestampSeconds={12.5} />);
    const video = screen.getByLabelText(/source video at event/i) as HTMLVideoElement;
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(12.5);

    await user.click(screen.getByRole("button", { name: /play ±2 seconds/i }));
    expect(video.currentTime).toBe(10.5);
    expect(play).toHaveBeenCalled();

    video.currentTime = 14.6;
    fireEvent.timeUpdate(video);
    expect(pause).toHaveBeenCalled();
  });
});
