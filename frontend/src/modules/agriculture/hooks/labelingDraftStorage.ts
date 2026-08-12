import type { AnnotationDraft } from "../components/AnnotationCanvas";
import type { VisionImage } from "../visionTypes";

const MAX_LOCAL_DRAFT_BYTES = 512 * 1024;

export function imageDrafts(image: VisionImage): AnnotationDraft[] {
  return image.annotations.map(({ id, class_id, x1, y1, x2, y2 }) => ({
    id,
    class_id,
    x1,
    y1,
    x2,
    y2,
  }));
}

function draftKey(datasetId: string, imageId: string, revision: number) {
  return `vision-annotation-draft:${datasetId}:${imageId}:${revision}`;
}

export function clearImageDrafts(datasetId: string, imageId: string) {
  if (typeof window === "undefined") return;
  const prefix = `vision-annotation-draft:${datasetId}:${imageId}:`;
  Object.keys(window.localStorage)
    .filter((key) => key.startsWith(prefix))
    .forEach((key) => window.localStorage.removeItem(key));
}

export function readImageDraft(
  datasetId: string,
  imageId: string,
  revision: number,
) {
  if (typeof window === "undefined") return null;
  const key = draftKey(datasetId, imageId, revision);
  const rawDraft = window.localStorage.getItem(key);
  if (!rawDraft) return null;
  try {
    const recovered = JSON.parse(rawDraft) as {
      annotations?: AnnotationDraft[];
      reviewed?: boolean;
    };
    if (!Array.isArray(recovered.annotations)) return null;
    return {
      annotations: recovered.annotations,
      reviewed: Boolean(recovered.reviewed),
    };
  } catch {
    window.localStorage.removeItem(key);
    return null;
  }
}

export function storeImageDraft(
  datasetId: string,
  imageId: string,
  revision: number,
  annotations: AnnotationDraft[],
  reviewed: boolean,
) {
  if (typeof window === "undefined") return;
  const serialized = JSON.stringify({
    annotations,
    reviewed,
    savedAt: new Date().toISOString(),
  });
  if (serialized.length > MAX_LOCAL_DRAFT_BYTES) return;
  try {
    window.localStorage.setItem(draftKey(datasetId, imageId, revision), serialized);
  } catch {
    // The server revision remains authoritative when browser storage is full.
  }
}
