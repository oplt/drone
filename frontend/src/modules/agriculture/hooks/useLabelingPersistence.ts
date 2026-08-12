import { useCallback } from "react";
import type { VisionImage } from "../visionTypes";
import { useLabelingSaveQueue } from "./useLabelingSaveQueue";
import { useLabelingSession } from "./useLabelingSession";
import { useUnsavedLabelingGuard } from "./useUnsavedLabelingGuard";

export type {
  AnnotationConflict,
  LabelingSaveState,
} from "./labelingPersistenceTypes";

export function useLabelingPersistence({
  activeImage,
  datasetId,
  pageOffset,
}: {
  activeImage: VisionImage | null;
  datasetId: string;
  pageOffset: number;
}) {
  const session = useLabelingSession(activeImage, datasetId);
  const { persist, awaitSaves } = useLabelingSaveQueue({
    activeImage,
    datasetId,
    pageOffset,
    session,
  });
  const {
    annotations,
    reviewed,
    selectedId,
    saveState,
    saveError,
    conflict,
    revisionRef,
    setSelectedId,
    setSaveError,
    loadServerVersion,
  } = session;

  const retry = useCallback(
    () => persist(annotations, reviewed),
    [annotations, persist, reviewed],
  );
  const overwriteConflict = useCallback(() => {
    if (!conflict) return Promise.resolve();
    revisionRef.current = conflict.currentRevision;
    return persist(annotations, reviewed);
  }, [annotations, conflict, persist, reviewed, revisionRef]);
  const downloadLocalCopy = useCallback(() => {
    if (!activeImage || typeof window === "undefined") return;
    const blob = new Blob([
      JSON.stringify({
        image_id: activeImage.id,
        based_on_revision: revisionRef.current,
        reviewed,
        annotations,
      }, null, 2),
    ], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = `annotations-${activeImage.id}-local.json`;
    anchor.click();
    URL.revokeObjectURL(url);
  }, [activeImage, annotations, reviewed, revisionRef]);
  const deleteSelected = useCallback(() => {
    if (!selectedId) return;
    void persist(annotations.filter((annotation) => annotation.id !== selectedId), false);
    setSelectedId(null);
  }, [annotations, persist, selectedId, setSelectedId]);

  useUnsavedLabelingGuard(saveState, setSaveError);

  return {
    annotations,
    reviewed,
    selectedId,
    saveState,
    saveError,
    conflict,
    setSelectedId,
    setSaveError,
    persist,
    retry,
    overwriteConflict,
    loadServerVersion,
    downloadLocalCopy,
    awaitSaves,
    deleteSelected,
  };
}
