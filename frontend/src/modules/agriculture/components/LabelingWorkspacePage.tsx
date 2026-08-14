import { useCallback, useEffect, useRef, useState } from "react";
import { Alert, Box, Button, CircularProgress, Divider, Paper, Stack, Typography, useMediaQuery, useTheme } from "@mui/material";
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
import { LabelingConflictDialog } from "./LabelingConflictDialog";
import { LabelingClassPanel, LabelingImageStrip } from "./LabelingPanels";
import { useLabelingPersistence } from "../hooks/useLabelingPersistence";
import { useLabelingShortcuts } from "../hooks/useLabelingShortcuts";
import {
  useVisionDataset,
  useVisionImages,
  useVisionProjects,
} from "../hooks/useVisionModels";
import { resolveVisionMediaUrl } from "../visionApi";
import { AgricultureAccessibilityBoundary } from "./AgricultureAccessibilityBoundary";

const PAGE_SIZE = 200;

/** Focused labeling IDE. Ops shell WorkflowHeader stays mounted above for alert/log access. */
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
  const reloadServerAnnotations = useCallback(async () => {
    const result = await images.refetch();
    const serverImage = result.data?.items.find((item) => item.id === activeImage?.id);
    if (serverImage) labeling.loadServerVersion(serverImage);
  }, [activeImage?.id, images, labeling]);

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

  if (compactWarning) {
    const items = images.data?.items ?? [];
    const reviewImage = items[activeIndex] ?? null;
    const markReviewed = async () => {
      if (!reviewImage) return;
      await labeling.persist(labeling.annotations, !labeling.reviewed);
      await images.refetch();
    };
    return (
      <AgricultureAccessibilityBoundary component="div">
      <Stack spacing={2} sx={{ p: 2, pb: "calc(16px + env(safe-area-inset-bottom, 0px))" }}>
        <Alert severity="info">
          Drawing annotations needs a tablet or laptop. On phone you can review
          frames and mark them reviewed, then continue labeling on a larger display.
        </Alert>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          <Button
            variant="outlined"
            onClick={() => navigate("/dashboard/agriculture/vision-models")}
          >
            Back to vision projects
          </Button>
          <Button
            variant="text"
            href={`/dashboard/agriculture/vision-models/datasets/${datasetId}/label`}
            target="_blank"
            rel="noreferrer"
          >
            Open labeling on desktop
          </Button>
        </Stack>
        {dataset.isLoading || images.isLoading ? (
          <CircularProgress aria-label="Loading review queue" />
        ) : items.length === 0 ? (
          <Alert severity="warning">No images in this dataset yet.</Alert>
        ) : (
          <Stack spacing={2}>
            {reviewImage ? (
              <Paper variant="outlined" sx={{ p: 1.5 }}>
                <Stack spacing={1.5}>
                  <Box
                    component="img"
                    src={resolveVisionMediaUrl(reviewImage.content_url)}
                    alt={`Frame ${pageOffset + activeIndex + 1}`}
                    sx={{
                      width: "100%",
                      maxHeight: 280,
                      objectFit: "contain",
                      borderRadius: 1,
                      bgcolor: "action.hover",
                    }}
                  />
                  <Typography variant="subtitle2">
                    Frame {pageOffset + activeIndex + 1} of {images.data?.total ?? items.length}
                    {labeling.reviewed ? " · reviewed" : " · pending review"}
                  </Typography>
                  <Stack direction="row" spacing={1}>
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={activeIndex <= 0}
                      onClick={() => setActiveIndex((value) => Math.max(0, value - 1))}
                    >
                      Previous
                    </Button>
                    <Button
                      size="small"
                      variant="outlined"
                      disabled={activeIndex >= items.length - 1}
                      onClick={() =>
                        setActiveIndex((value) => Math.min(items.length - 1, value + 1))
                      }
                    >
                      Next
                    </Button>
                    <Button
                      size="small"
                      variant={labeling.reviewed ? "outlined" : "contained"}
                      color={labeling.reviewed ? "success" : "primary"}
                      disabled={labeling.saveState === "saving"}
                      onClick={() => void markReviewed()}
                      sx={{ ml: "auto", minHeight: 44 }}
                    >
                      {labeling.reviewed ? "Reviewed" : "Mark reviewed"}
                    </Button>
                  </Stack>
                  {labeling.saveError ? (
                    <Alert severity="error">{labeling.saveError}</Alert>
                  ) : null}
                </Stack>
              </Paper>
            ) : null}
            <Typography variant="caption" color="text.secondary">
              Review queue (tap to select)
            </Typography>
            <Stack
              direction="row"
              spacing={1}
              sx={{ overflowX: "auto", pb: 0.5 }}
              component="ul"
              aria-label="Dataset review queue"
            >
              {items.slice(0, 40).map((item, index) => (
                <Box
                  key={item.id}
                  component="li"
                  sx={{ listStyle: "none", m: 0, p: 0 }}
                >
                  <Button
                    onClick={() => setActiveIndex(index)}
                    aria-pressed={index === activeIndex}
                    aria-label={`Select frame ${pageOffset + index + 1}`}
                    sx={{
                      p: 0.5,
                      minWidth: 72,
                      border: "2px solid",
                      borderColor: index === activeIndex ? "primary.main" : "divider",
                      borderRadius: 1,
                    }}
                  >
                    <Box
                      component="img"
                      src={resolveVisionMediaUrl(item.content_url)}
                      alt=""
                      sx={{ width: 64, height: 64, objectFit: "cover", borderRadius: 0.75 }}
                    />
                  </Button>
                </Box>
              ))}
            </Stack>
          </Stack>
        )}
      </Stack>
      </AgricultureAccessibilityBoundary>
    );
  }
  if (dataset.isLoading || images.isLoading || projects.isLoading)
    return (
      <AgricultureAccessibilityBoundary component="div">
        <CircularProgress aria-label="Loading labeling workspace" />
      </AgricultureAccessibilityBoundary>
    );
  if (!activeImage || !project || !dataset.data || !images.data)
    return (
      <AgricultureAccessibilityBoundary component="div">
        <Alert severity="warning">This dataset has no images available for labeling.</Alert>
      </AgricultureAccessibilityBoundary>
    );

  const selected = labeling.annotations.find((item) => item.id === labeling.selectedId);
  const position = pageOffset + activeIndex;
  const workspacePosition = expanded
    ? { position: "fixed" as const, inset: 0, zIndex: theme.zIndex.modal + 1, p: 1 }
    : { height: "calc(100vh - 112px)" };
  return (
    <AgricultureAccessibilityBoundary component="div">
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
        <LabelingConflictDialog
          open={Boolean(labeling.conflict)}
          message={labeling.saveError}
          expectedRevision={labeling.conflict?.expectedRevision ?? 0}
          currentRevision={labeling.conflict?.currentRevision ?? 0}
          onReload={() => void reloadServerAnnotations()}
          onDownload={labeling.downloadLocalCopy}
          onOverwrite={() => void labeling.overwriteConflict()}
        />
        {!labeling.conflict && labeling.saveError ? (
          <Alert
            severity="error"
            action={<Button size="small" onClick={() => void labeling.retry()}>Retry save</Button>}
          >
            {labeling.saveError} Your edits remain local and navigation is blocked.
          </Alert>
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
    </AgricultureAccessibilityBoundary>
  );
}
