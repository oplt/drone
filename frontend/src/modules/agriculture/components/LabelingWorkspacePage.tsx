import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, CircularProgress, Divider, Paper, Stack, useMediaQuery, useTheme } from "@mui/material";
import { useNavigate, useParams } from "react-router-dom";
import {
  AnnotationCanvas,
  type AnnotationCanvasHandle,
  type AnnotationTool,
} from "./AnnotationCanvas";
import {
  LabelingFooter,
  LabelingHeader,
  LabelingShortcutMenu,
  LabelingToolbar,
} from "./LabelingControls";
import { LabelingClassPanel, LabelingImageStrip } from "./LabelingPanels";
import { useLabelingPersistence } from "../hooks/useLabelingPersistence";
import { useLabelingShortcuts } from "../hooks/useLabelingShortcuts";
import {
  useVisionDataset,
  useVisionImages,
  useVisionProjects,
} from "../hooks/useVisionModels";
import { resolveVisionMediaUrl } from "../visionApi";

const PAGE_SIZE = 200;

export function LabelingWorkspacePage() {
  const { datasetId = "" } = useParams();
  const navigate = useNavigate();
  const theme = useTheme();
  const compactWarning = useMediaQuery(theme.breakpoints.down("sm"));
  const [pageOffset, setPageOffset] = useState(0);
  const [activeIndex, setActiveIndex] = useState(0);
  const [preferredClassId, setPreferredClassId] = useState<string | null>(null);
  const [tool, setTool] = useState<AnnotationTool>("draw");
  const [spacePan, setSpacePan] = useState(false);
  const [zoom, setZoom] = useState(1);
  const [expanded, setExpanded] = useState(false);
  const [helpAnchor, setHelpAnchor] = useState<HTMLElement | null>(null);
  const canvasRef = useRef<AnnotationCanvasHandle | null>(null);
  const dataset = useVisionDataset(datasetId);
  const images = useVisionImages(datasetId, pageOffset);
  const projects = useVisionProjects();
  const project = projects.data?.find((item) => item.id === dataset.data?.project_id);
  const activeClassId =
    project?.classes.some((item) => item.id === preferredClassId)
      ? preferredClassId
      : project?.classes[0]?.id ?? null;
  const activeImage = images.data?.items[activeIndex] ?? null;
  const labeling = useLabelingPersistence({ activeImage, datasetId, pageOffset });

  useEffect(() => {
    if (!images.data) return;
    [activeIndex - 1, activeIndex + 1, activeIndex + 2]
      .map((index) => images.data.items[index])
      .filter(Boolean)
      .forEach((item) => {
        const preload = new window.Image();
        preload.src = resolveVisionMediaUrl(item.content_url);
      });
  }, [activeIndex, images.data]);

  const navigateImage = useCallback(
    async (direction: -1 | 1) => {
      if (!(await labeling.awaitSaves()) || !images.data) return;
      const next = activeIndex + direction;
      if (next >= 0 && next < images.data.items.length) {
        setActiveIndex(next);
        return;
      }
      const nextOffset = pageOffset + direction * PAGE_SIZE;
      if (nextOffset < 0 || nextOffset >= images.data.total) return;
      setPageOffset(nextOffset);
      setActiveIndex(direction === 1 ? 0 : PAGE_SIZE - 1);
    },
    [activeIndex, images.data, labeling, pageOffset],
  );
  useLabelingShortcuts({
    annotations: labeling.annotations,
    reviewed: labeling.reviewed,
    classes: project?.classes ?? [],
    canvas: canvasRef,
    persist: labeling.persist,
    navigate: navigateImage,
    deleteSelected: labeling.deleteSelected,
    setTool,
    setSpacePan,
    setSelectedId: labeling.setSelectedId,
    setActiveClassId: setPreferredClassId,
  });

  if (compactWarning)
    return <Alert severity="info">Image annotation needs a tablet or laptop-sized display.</Alert>;
  if (dataset.isLoading || images.isLoading || projects.isLoading)
    return <CircularProgress aria-label="Loading labeling workspace" />;
  if (!activeImage || !project || !dataset.data || !images.data)
    return <Alert severity="warning">This dataset has no images available for labeling.</Alert>;

  const selected = labeling.annotations.find((item) => item.id === labeling.selectedId);
  const position = pageOffset + activeIndex;
  const workspacePosition = expanded
    ? { position: "fixed" as const, inset: 0, zIndex: theme.zIndex.modal + 1, p: 1 }
    : { height: "calc(100vh - 112px)" };
  return (
    <Paper sx={{ ...workspacePosition, bgcolor: "background.default", overflow: "hidden" }}>
      <Stack height="100%">
        <LabelingHeader
          title={`${project.name} · Dataset v${dataset.data.version}`}
          reviewed={dataset.data.reviewed_count}
          total={dataset.data.image_count}
          saveState={labeling.saveState}
          expanded={expanded}
          toggleExpanded={() => setExpanded((value) => !value)}
          showHelp={setHelpAnchor}
          close={() => void labeling.awaitSaves().then((saved) => saved && navigate("/dashboard/agriculture/vision-models"))}
        />
        {labeling.saveError ? (
          <Alert severity="error" onClose={() => labeling.setSaveError(null)}>{labeling.saveError}</Alert>
        ) : null}
        <Divider />
        <Stack direction="row" flex={1} minHeight={0}>
          <LabelingImageStrip
            images={images.data.items}
            activeIndex={activeIndex}
            pageOffset={pageOffset}
            selectImage={(index) => void labeling.awaitSaves().then((saved) => saved && setActiveIndex(index))}
          />
          <Stack flex={1} minWidth={0}>
            <LabelingToolbar tool={tool} zoom={zoom} canvas={canvasRef} setTool={setTool} />
            <Box flex={1} minHeight={0}>
              <AnnotationCanvas
                ref={canvasRef}
                imageUrl={resolveVisionMediaUrl(activeImage.content_url)}
                imageWidth={activeImage.width}
                imageHeight={activeImage.height}
                classes={project.classes}
                annotations={labeling.annotations}
                activeClassId={activeClassId}
                selectedId={labeling.selectedId}
                tool={spacePan ? "pan" : tool}
                onSelect={labeling.setSelectedId}
                onChange={(next) => void labeling.persist(next, false)}
                onZoomChange={setZoom}
              />
            </Box>
            <LabelingFooter
              position={position}
              total={images.data.total}
              reviewed={labeling.reviewed}
              navigate={(direction) => void navigateImage(direction)}
              toggleReviewed={() => void labeling.persist(labeling.annotations, !labeling.reviewed)}
            />
          </Stack>
          <LabelingClassPanel
            classes={project.classes}
            annotations={labeling.annotations}
            activeClassId={activeClassId}
            selectedId={labeling.selectedId}
            chooseClass={(id) => {
              setPreferredClassId(id);
              if (selected) void labeling.persist(labeling.annotations.map((item) => item.id === selected.id ? { ...item, class_id: id } : item), false);
            }}
            selectAnnotation={labeling.setSelectedId}
            deleteSelected={labeling.deleteSelected}
          />
        </Stack>
      </Stack>
      <LabelingShortcutMenu anchor={helpAnchor} close={() => setHelpAnchor(null)} />
    </Paper>
  );
}
