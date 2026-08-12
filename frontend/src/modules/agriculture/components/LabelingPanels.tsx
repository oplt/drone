import { DeleteOutline } from "@mui/icons-material";
import {
  Box,
  Chip,
  Divider,
  IconButton,
  List,
  ListItemButton,
  ListItemText,
  Stack,
  Tooltip,
  Typography,
} from "@mui/material";
import type { AnnotationDraft } from "./AnnotationCanvas";
import type { VisionClass, VisionImage } from "../visionTypes";
import { resolveVisionMediaUrl } from "../visionApi";
import { classColor } from "../visionColors";

function statusColor(status: VisionImage["annotation_status"]): string {
  if (status === "reviewed") return "success.main";
  if (status === "labeled") return "info.main";
  return "text.disabled";
}

export function LabelingImageStrip({
  images,
  activeIndex,
  pageOffset,
  selectImage,
}: {
  images: VisionImage[];
  activeIndex: number;
  pageOffset: number;
  selectImage: (index: number) => void;
}) {
  return (
    <Box width={190} overflow="auto" borderRight={1} borderColor="divider" p={1}>
      <Typography variant="overline">Images</Typography>
      <List dense disablePadding>
        {images.map((item, index) => (
          <ListItemButton
            key={item.id}
            selected={index === activeIndex}
            onClick={() => selectImage(index)}
            sx={{ px: 0.75, gap: 1 }}
          >
            <Box
              component="img"
              src={resolveVisionMediaUrl(item.thumbnail_url)}
              alt=""
              loading="lazy"
              width={58}
              height={42}
              sx={{ objectFit: "cover", borderRadius: 0.5 }}
            />
            <ListItemText primary={`Image ${pageOffset + index + 1}`} secondary={`${item.annotations.length} boxes`} />
            <Box width={8} height={8} borderRadius="50%" bgcolor={statusColor(item.annotation_status)} title={item.annotation_status} />
          </ListItemButton>
        ))}
      </List>
    </Box>
  );
}

export function LabelingClassPanel({
  classes,
  annotations,
  activeClassId,
  selectedId,
  chooseClass,
  selectAnnotation,
  deleteSelected,
}: {
  classes: VisionClass[];
  annotations: AnnotationDraft[];
  activeClassId: string | null;
  selectedId: string | null;
  chooseClass: (id: string) => void;
  selectAnnotation: (id: string) => void;
  deleteSelected: () => void;
}) {
  const counts = new Map<string, number>();
  annotations.forEach((item) => counts.set(item.class_id, (counts.get(item.class_id) ?? 0) + 1));
  return (
    <Box width={260} overflow="auto" borderLeft={1} borderColor="divider" p={1.5}>
      <Typography variant="overline">Classes</Typography>
      <List dense>
        {classes.map((visionClass, index) => (
          <ListItemButton key={visionClass.id} selected={visionClass.id === activeClassId} onClick={() => chooseClass(visionClass.id)}>
            <Box width={11} height={11} borderRadius="50%" bgcolor={classColor(visionClass.id)} mr={1} />
            <ListItemText primary={`${index < 9 ? `[${index + 1}] ` : ""}${visionClass.name.replaceAll("_", " ")}`} />
            <Chip size="small" label={counts.get(visionClass.id) ?? 0} />
          </ListItemButton>
        ))}
      </List>
      <Divider sx={{ my: 1 }} />
      <Stack direction="row" justifyContent="space-between" alignItems="center">
        <Typography variant="overline">Annotations</Typography>
        <Tooltip title="Delete selected (Delete)">
          <span>
            <IconButton size="small" disabled={!selectedId} onClick={deleteSelected}><DeleteOutline /></IconButton>
          </span>
        </Tooltip>
      </Stack>
      <List dense>
        {annotations.map((annotation, index) => {
          const visionClass = classes.find((item) => item.id === annotation.class_id);
          return (
            <ListItemButton key={annotation.id} selected={annotation.id === selectedId} onClick={() => selectAnnotation(annotation.id)}>
              <ListItemText primary={`#${index + 1} ${visionClass?.name.replaceAll("_", " ") ?? "Unknown"}`} />
            </ListItemButton>
          );
        })}
      </List>
    </Box>
  );
}
