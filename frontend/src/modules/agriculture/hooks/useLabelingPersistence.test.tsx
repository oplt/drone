import { act, renderHook, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../../shared/api/apiError";
import type { AnnotationDraft } from "../components/AnnotationCanvas";
import type { VisionImage } from "../visionTypes";
import { useLabelingPersistence } from "./useLabelingPersistence";

const { saveMock } = vi.hoisted(() => ({ saveMock: vi.fn() }));

vi.mock("./useVisionModels", () => ({
  useSaveVisionAnnotations: () => ({ mutateAsync: saveMock }),
}));

function image(id: string, revision = 0): VisionImage {
  return {
    id,
    dataset_id: "dataset-1",
    content_url: `/vision/images/${id}`,
    thumbnail_url: `/vision/images/${id}/thumbnail`,
    source_type: "upload",
    source_video_id: null,
    mission_id: null,
    field_id: null,
    frame_index: null,
    timestamp_seconds: null,
    width: 100,
    height: 100,
    quality_score: 1,
    selected: true,
    split: null,
    annotation_status: "unlabeled",
    annotation_revision: revision,
    annotations: [],
    lat: null,
    lon: null,
    altitude_m: null,
    heading_deg: null,
    metadata: {},
    created_at: "2026-08-12T00:00:00Z",
  };
}

const draft: AnnotationDraft[] = [
  { id: "annotation-local", class_id: "class-1", x1: 1, y1: 2, x2: 20, y2: 30 },
];

describe("useLabelingPersistence", () => {
  beforeEach(() => {
    saveMock.mockReset();
    window.localStorage.clear();
  });

  it("keeps a failed save dirty, recoverable, and protected from navigation", async () => {
    saveMock.mockRejectedValueOnce(new Error("network unavailable"));
    const { result } = renderHook(() =>
      useLabelingPersistence({
        activeImage: image("image-1", 3),
        datasetId: "dataset-1",
        pageOffset: 0,
      }),
    );

    await act(async () => {
      await result.current.persist(draft, false);
    });

    expect(result.current.saveState).toBe("failed");
    expect(result.current.annotations).toEqual(draft);
    expect(result.current.saveError).toContain("network unavailable");
    expect(
      window.localStorage.getItem(
        "vision-annotation-draft:dataset-1:image-1:3",
      ),
    ).toContain("annotation-local");

    const unload = new Event("beforeunload", { cancelable: true });
    window.dispatchEvent(unload);
    expect(unload.defaultPrevented).toBe(true);

    const anchor = document.createElement("a");
    anchor.href = "/dashboard";
    document.body.append(anchor);
    const click = new MouseEvent("click", { bubbles: true, cancelable: true });
    act(() => anchor.dispatchEvent(click));
    expect(click.defaultPrevented).toBe(true);
    anchor.remove();
  });

  it("recovers a revision-scoped local draft without replacing server data", async () => {
    window.localStorage.setItem(
      "vision-annotation-draft:dataset-1:image-2:5",
      JSON.stringify({ annotations: draft, reviewed: true }),
    );
    const { result } = renderHook(() =>
      useLabelingPersistence({
        activeImage: image("image-2", 5),
        datasetId: "dataset-1",
        pageOffset: 0,
      }),
    );

    await waitFor(() => expect(result.current.saveState).toBe("failed"));
    expect(result.current.annotations).toEqual(draft);
    expect(result.current.reviewed).toBe(true);
    expect(saveMock).not.toHaveBeenCalled();
  });

  it("serializes saves with the image identity captured by each operation", async () => {
    saveMock.mockImplementation(async ({ imageId, expectedRevision }) => ({
      ...image(imageId, expectedRevision + 1),
      annotations: [],
    }));
    const { result, rerender } = renderHook(
      ({ activeImage }) =>
        useLabelingPersistence({
          activeImage,
          datasetId: "dataset-1",
          pageOffset: 0,
        }),
      { initialProps: { activeImage: image("image-a") } },
    );

    await act(async () => {
      await result.current.persist(draft, false);
    });
    rerender({ activeImage: image("image-b") });
    await waitFor(() => expect(result.current.annotations).toEqual([]));
    await act(async () => {
      await result.current.persist(draft, false);
    });

    expect(saveMock.mock.calls.map(([request]) => request.imageId)).toEqual([
      "image-a",
      "image-b",
    ]);
  });

  it("requires an explicit resolution before overwriting a newer server revision", async () => {
    saveMock.mockRejectedValueOnce(
      new ApiError(
        409,
        "Annotations changed in another session",
        null,
        null,
        null,
        "VISION_ANNOTATION_REVISION_CONFLICT",
        { expected_revision: 2, current_revision: 4 },
      ),
    );
    saveMock.mockImplementationOnce(async ({ imageId }) => ({
      ...image(imageId, 5),
      annotations: [],
    }));
    const { result } = renderHook(() =>
      useLabelingPersistence({
        activeImage: image("image-conflict", 2),
        datasetId: "dataset-1",
        pageOffset: 0,
      }),
    );

    await act(async () => {
      await result.current.persist(draft, true);
    });
    expect(result.current.conflict).toEqual({
      expectedRevision: 2,
      currentRevision: 4,
    });

    await act(async () => {
      await result.current.overwriteConflict();
    });
    expect(saveMock.mock.calls[1][0].expectedRevision).toBe(4);
    expect(result.current.saveState).toBe("saved");
  });
});
