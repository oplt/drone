import { useCallback, useEffect, useRef, useState } from "react";
import type { AnnotationDraft } from "../components/AnnotationCanvas";
import type { AnnotationInput, VisionImage } from "../visionTypes";
import { useSaveVisionAnnotations } from "./useVisionModels";

export type LabelingSaveState = "saved" | "saving" | "failed";

function imageDrafts(image: VisionImage): AnnotationDraft[] {
  return image.annotations.map(({ id, class_id, x1, y1, x2, y2 }) => ({
    id,
    class_id,
    x1,
    y1,
    x2,
    y2,
  }));
}

export function useLabelingPersistence({
  activeImage,
  datasetId,
  pageOffset,
}: {
  activeImage: VisionImage | null;
  datasetId: string;
  pageOffset: number;
}) {
  const save = useSaveVisionAnnotations();
  const [loadedImageId, setLoadedImageId] = useState(activeImage?.id ?? null);
  const [annotations, setAnnotations] = useState<AnnotationDraft[]>(() =>
    activeImage ? imageDrafts(activeImage) : [],
  );
  const [reviewed, setReviewed] = useState(
    activeImage?.annotation_status === "reviewed",
  );
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<LabelingSaveState>("saved");
  const [saveError, setSaveError] = useState<string | null>(null);
  const saveQueue = useRef<Promise<void>>(Promise.resolve());
  const saveFailed = useRef(false);
  const sequence = useRef(0);

  if (activeImage?.id !== loadedImageId) {
    setLoadedImageId(activeImage?.id ?? null);
    setAnnotations(activeImage ? imageDrafts(activeImage) : []);
    setReviewed(activeImage?.annotation_status === "reviewed");
    setSelectedId(null);
    setSaveState("saved");
    setSaveError(null);
  }

  const persist = useCallback(
    (next: AnnotationDraft[], nextReviewed: boolean) => {
      if (!activeImage) return Promise.resolve();
      const requestSequence = ++sequence.current;
      const imageId = activeImage.id;
      setAnnotations(next);
      setReviewed(nextReviewed);
      setSaveState("saving");
      setSaveError(null);
      saveFailed.current = false;
      const payload: AnnotationInput[] = next.map((annotation) => ({
        id: annotation.id.startsWith("annotation-") ? undefined : annotation.id,
        class_id: annotation.class_id,
        x1: annotation.x1,
        y1: annotation.y1,
        x2: annotation.x2,
        y2: annotation.y2,
        source: "manual",
      }));
      const operation = saveQueue.current.then(() =>
        save.mutateAsync({
          datasetId,
          pageOffset,
          imageId,
          annotations: payload,
          reviewed: nextReviewed,
        }),
      );
      saveQueue.current = operation.then(
        (savedImage) => {
          if (requestSequence !== sequence.current) return;
          if (savedImage.id === activeImage.id)
            setAnnotations(imageDrafts(savedImage));
          saveFailed.current = false;
          setSaveState("saved");
        },
        (error: unknown) => {
          if (requestSequence !== sequence.current) return;
          saveFailed.current = true;
          setSaveState("failed");
          setSaveError(
            error instanceof Error ? error.message : "Unable to save annotation.",
          );
        },
      );
      return saveQueue.current;
    },
    [activeImage, datasetId, pageOffset, save],
  );

  const awaitSaves = useCallback(async () => {
    await saveQueue.current;
    return !saveFailed.current;
  }, []);
  const deleteSelected = useCallback(() => {
    if (!selectedId) return;
    void persist(
      annotations.filter((annotation) => annotation.id !== selectedId),
      false,
    );
    setSelectedId(null);
  }, [annotations, persist, selectedId]);

  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (saveState === "saving") event.preventDefault();
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [saveState]);

  return {
    annotations,
    reviewed,
    selectedId,
    saveState,
    saveError,
    setSelectedId,
    setSaveError,
    persist,
    awaitSaves,
    deleteSelected,
  };
}
