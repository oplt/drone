import { useMutation, useQueryClient } from "@tanstack/react-query";
import { saveVisionAnnotations, setVisionImageSelected } from "../visionApi";
import type { AnnotationInput, VisionImage, VisionImagePage } from "../visionTypes";
import { visionKeys } from "./visionQueryKeys";

type SaveVariables = {
  datasetId: string;
  pageOffset: number;
  imageId: string;
  annotations: AnnotationInput[];
  reviewed: boolean;
  expectedRevision: number;
};

function replaceCachedImage(
  page: VisionImagePage | undefined,
  imageId: string,
  update: (image: VisionImage) => VisionImage,
) {
  if (!page) return page;
  return { ...page, items: page.items.map((image) => image.id === imageId ? update(image) : image) };
}

export function useSaveVisionAnnotations() {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ imageId, annotations, reviewed, expectedRevision }: SaveVariables) =>
      saveVisionAnnotations(imageId, annotations, reviewed, expectedRevision),
    onMutate: async (variables) => {
      const key = visionKeys.imagePage(variables.datasetId, variables.pageOffset);
      await client.cancelQueries({ queryKey: key });
      const previous = client.getQueryData<VisionImagePage>(key);
      client.setQueryData<VisionImagePage>(key, (page) =>
        replaceCachedImage(page, variables.imageId, (image) => ({
          ...image,
          annotation_status: variables.reviewed ? "reviewed" : variables.annotations.length ? "labeled" : "unlabeled",
          annotations: variables.annotations.map((annotation, index) => ({
            id: annotation.id ?? `optimistic-${index}`,
            annotation_type: "bbox",
            source: annotation.source ?? "manual",
            confidence: annotation.confidence ?? null,
            created_at: new Date().toISOString(),
            updated_at: new Date().toISOString(),
            ...annotation,
          })),
        })),
      );
      return { key, previous };
    },
    onError: (_error, _variables, context) => {
      if (context?.previous) client.setQueryData(context.key, context.previous);
    },
    onSuccess: (image, variables) => client.setQueryData<VisionImagePage>(
      visionKeys.imagePage(variables.datasetId, variables.pageOffset),
      (page) => replaceCachedImage(page, image.id, () => image),
    ),
    onSettled: (_data, _error, variables) => Promise.all([
      client.invalidateQueries({ queryKey: visionKeys.dataset(variables.datasetId) }),
      client.invalidateQueries({ queryKey: visionKeys.datasetLists() }),
    ]),
  });
}

export function useSetVisionImageSelected(datasetId: string, pageOffset = 0) {
  const client = useQueryClient();
  return useMutation({
    mutationFn: ({ imageId, selected }: { imageId: string; selected: boolean }) =>
      setVisionImageSelected(imageId, selected),
    onSuccess: (image) => {
      client.setQueryData<VisionImagePage>(
        visionKeys.imagePage(datasetId, pageOffset),
        (page) => replaceCachedImage(page, image.id, () => image),
      );
      void client.invalidateQueries({ queryKey: visionKeys.dataset(datasetId) });
      void client.invalidateQueries({ queryKey: visionKeys.datasetLists() });
    },
  });
}
