import { useCallback, useEffect, useRef, useState } from "react";
import type { AnnotationDraft } from "../components/AnnotationCanvas";
import type { VisionImage } from "../visionTypes";
import {
  clearImageDrafts,
  imageDrafts,
  readImageDraft,
} from "./labelingDraftStorage";
import type {
  AnnotationConflict,
  LabelingSaveState,
} from "./labelingPersistenceTypes";

export function useLabelingSession(
  activeImage: VisionImage | null,
  datasetId: string,
) {
  const [annotations, setAnnotations] = useState<AnnotationDraft[]>(() =>
    activeImage ? imageDrafts(activeImage) : [],
  );
  const [reviewed, setReviewed] = useState(activeImage?.annotation_status === "reviewed");
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [saveState, setSaveState] = useState<LabelingSaveState>("saved");
  const [saveError, setSaveError] = useState<string | null>(null);
  const [conflict, setConflict] = useState<AnnotationConflict | null>(null);
  const saveFailedRef = useRef(false);
  const sequenceRef = useRef(0);
  const revisionRef = useRef(activeImage?.annotation_revision ?? 0);
  const loadedImageId = useRef(activeImage?.id ?? null);
  const loadedRevisionRef = useRef(activeImage?.annotation_revision ?? 0);
  const activeImageIdRef = useRef(activeImage?.id ?? null);
  const hydratedImage = useRef(false);

  useEffect(() => {
    activeImageIdRef.current = activeImage?.id ?? null;
    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      if (!activeImage) {
        hydratedImage.current = false;
        loadedImageId.current = null;
        loadedRevisionRef.current = 0;
        revisionRef.current = 0;
        setAnnotations([]);
        setReviewed(false);
        return;
      }
      if (
        hydratedImage.current &&
        activeImage.id === loadedImageId.current &&
        activeImage.annotation_revision === loadedRevisionRef.current
      ) return;
      hydratedImage.current = true;
      loadedImageId.current = activeImage.id;
      loadedRevisionRef.current = activeImage.annotation_revision;
      revisionRef.current = activeImage.annotation_revision;
      setAnnotations(imageDrafts(activeImage));
      setReviewed(activeImage.annotation_status === "reviewed");
      setSelectedId(null);
      setSaveState("saved");
      setSaveError(null);
      setConflict(null);
      saveFailedRef.current = false;
      const recovered = readImageDraft(
        datasetId,
        activeImage.id,
        activeImage.annotation_revision,
      );
      if (recovered) {
        setAnnotations(recovered.annotations);
        setReviewed(recovered.reviewed);
        setSaveState("failed");
        setSaveError("Recovered an unsaved local draft from this browser.");
        saveFailedRef.current = true;
      }
    });
    return () => {
      cancelled = true;
    };
  }, [activeImage, datasetId]);

  const loadServerVersion = useCallback((image: VisionImage) => {
    clearImageDrafts(datasetId, image.id);
    sequenceRef.current += 1;
    loadedImageId.current = image.id;
    hydratedImage.current = true;
    loadedRevisionRef.current = image.annotation_revision;
    revisionRef.current = image.annotation_revision;
    setAnnotations(imageDrafts(image));
    setReviewed(image.annotation_status === "reviewed");
    setSelectedId(null);
    setSaveState("saved");
    setSaveError(null);
    setConflict(null);
    saveFailedRef.current = false;
  }, [datasetId]);

  return {
    annotations, setAnnotations, reviewed, setReviewed, selectedId, setSelectedId,
    saveState, setSaveState, saveError, setSaveError, conflict, setConflict,
    saveFailedRef, sequenceRef, revisionRef, loadedRevisionRef, activeImageIdRef,
    loadServerVersion,
  };
}
