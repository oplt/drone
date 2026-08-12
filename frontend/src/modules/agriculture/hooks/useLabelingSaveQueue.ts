import { useCallback, useRef } from "react";
import { ApiError } from "../../../shared/api/apiError";
import type { AnnotationDraft } from "../components/AnnotationCanvas";
import type { AnnotationInput, VisionImage } from "../visionTypes";
import { clearImageDrafts, imageDrafts, storeImageDraft } from "./labelingDraftStorage";
import type { useLabelingSession } from "./useLabelingSession";
import { useSaveVisionAnnotations } from "./useVisionModels";

type LabelingSession = ReturnType<typeof useLabelingSession>;

export function useLabelingSaveQueue({
  activeImage,
  datasetId,
  pageOffset,
  session,
}: {
  activeImage: VisionImage | null;
  datasetId: string;
  pageOffset: number;
  session: LabelingSession;
}) {
  const save = useSaveVisionAnnotations();
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const {
    setAnnotations, setReviewed, setSaveState, setSaveError, setConflict,
    saveFailedRef, sequenceRef, revisionRef, loadedRevisionRef, activeImageIdRef,
  } = session;

  const persist = useCallback(
    (next: AnnotationDraft[], nextReviewed: boolean) => {
      if (!activeImage) return Promise.resolve();
      const requestSequence = ++sequenceRef.current;
      const imageId = activeImage.id;
      setAnnotations(next);
      setReviewed(nextReviewed);
      setSaveState("saving");
      setSaveError(null);
      setConflict(null);
      saveFailedRef.current = false;
      storeImageDraft(datasetId, imageId, revisionRef.current, next, nextReviewed);
      const payload: AnnotationInput[] = next.map((annotation) => ({
        id: annotation.id.startsWith("annotation-") ? undefined : annotation.id,
        class_id: annotation.class_id,
        x1: annotation.x1,
        y1: annotation.y1,
        x2: annotation.x2,
        y2: annotation.y2,
        source: "manual",
      }));
      const operation = saveQueue.current.then(async () => {
        const expectedRevision = revisionRef.current;
        storeImageDraft(datasetId, imageId, expectedRevision, next, nextReviewed);
        const savedImage = await save.mutateAsync({
          datasetId, pageOffset, imageId, annotations: payload,
          reviewed: nextReviewed, expectedRevision,
        });
        revisionRef.current = savedImage.annotation_revision;
        loadedRevisionRef.current = savedImage.annotation_revision;
        clearImageDrafts(datasetId, imageId);
        return savedImage;
      });
      saveQueue.current = operation.then(
        (savedImage) => {
          if (requestSequence !== sequenceRef.current || activeImageIdRef.current !== imageId) return;
          setAnnotations(imageDrafts(savedImage));
          setReviewed(savedImage.annotation_status === "reviewed");
          saveFailedRef.current = false;
          setSaveState("saved");
        },
        (error: unknown) => {
          if (requestSequence !== sequenceRef.current || activeImageIdRef.current !== imageId) return;
          saveFailedRef.current = true;
          setSaveState("failed");
          if (
            error instanceof ApiError &&
            error.status === 409 &&
            error.code === "VISION_ANNOTATION_REVISION_CONFLICT"
          ) {
            const currentRevision = Number(error.details.current_revision);
            setConflict({
              expectedRevision: Number(error.details.expected_revision),
              currentRevision: Number.isFinite(currentRevision) ? currentRevision : revisionRef.current,
            });
            setSaveError("Someone saved a newer version of this image. Your local edits were not overwritten.");
            return;
          }
          setSaveError(error instanceof Error ? error.message : "Unable to save annotation.");
        },
      );
      return saveQueue.current;
    },
    [
      activeImage, activeImageIdRef, datasetId, loadedRevisionRef, pageOffset,
      revisionRef, save, saveFailedRef, sequenceRef, setAnnotations, setConflict,
      setReviewed, setSaveError, setSaveState,
    ],
  );

  const awaitSaves = useCallback(async () => {
    await saveQueue.current;
    return !saveFailedRef.current;
  }, [saveFailedRef]);

  return { persist, awaitSaves };
}
