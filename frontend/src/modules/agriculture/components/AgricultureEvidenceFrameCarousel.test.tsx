import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AgricultureEvidenceFrameCarousel } from "./AgricultureEvidenceFrameCarousel";

const useEvidence = vi.hoisted(() => vi.fn());
const captureVideo = vi.hoisted(() => vi.fn());

vi.mock("../hooks", () => ({
  useAgricultureObservationEvidence: useEvidence,
}));
vi.mock("./AgricultureEvidenceVideoPlayer", () => ({
  AgricultureEvidenceVideoPlayer: (props: unknown) => {
    captureVideo(props);
    return <div>source video player</div>;
  },
}));
vi.mock("../../video-analysis/evidenceSelection", () => ({
  selectDetectionEvidence: vi.fn(),
}));

describe("AgricultureEvidenceFrameCarousel", () => {
  it("selects URL-linked evidence and exposes canonical video lineage", () => {
    useEvidence.mockReturnValue({
      isLoading: false,
      isError: false,
      data: {
        assets: [
          { evidence_id: "ev-1", media_id: "media-1", source_kind: "rgb_stills", content_type: "image/jpeg", checksum: "one", signed_url: "/one.jpg", frame_index: 1, timestamp_seconds: null, timestamp_source: null, source_video_id: null },
          { evidence_id: "ev-2", media_id: "media-2", source_kind: "rgb_video", content_type: "video/mp4", checksum: "two", signed_url: "/two.mp4", frame_index: 42, timestamp_seconds: 8.25, timestamp_source: "canonical_video_detection", source_video_id: "video-2" },
        ],
      },
    });
    render(
      <MemoryRouter initialEntries={["/?type=detection&evidence=ev-2"]}>
        <AgricultureEvidenceFrameCarousel observationId="obs-1" />
      </MemoryRouter>,
    );

    expect(screen.getByText("source video player")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /8.250s frame 42/i })).toHaveAttribute("aria-pressed", "true");
    expect(screen.getByText(/canonical_video_detection/i)).toBeInTheDocument();
    expect(captureVideo).toHaveBeenCalledWith({ videoId: "video-2", timestampSeconds: 8.25 });
  });

  it("keeps image-only evidence usable", () => {
    useEvidence.mockReturnValue({
      isLoading: false,
      isError: false,
      data: { assets: [{ evidence_id: "image-1", media_id: "media-1", source_kind: "rgb_stills", content_type: "image/jpeg", checksum: "one", signed_url: "/one.jpg", frame_index: null, timestamp_seconds: null, timestamp_source: null, source_video_id: null }] },
    });
    render(<MemoryRouter><AgricultureEvidenceFrameCarousel observationId="obs-1" /></MemoryRouter>);
    expect(screen.getByRole("link", { name: /open source evidence image-1/i })).toBeInTheDocument();
    expect(screen.getByText(/image-only evidence/i)).toBeInTheDocument();
  });
});
