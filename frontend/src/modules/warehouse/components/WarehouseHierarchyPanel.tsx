import {
  Button,
  List,
  ListItem,
  ListSubheader,
  Stack,
  Typography,
} from "@mui/material";
import type { LayoutDocument, LayoutKind } from "../api/warehouseLayoutApi";
import { LAYOUT_LABELS } from "../layoutEditorState";

const ORDER: LayoutKind[] = ["aisles", "racks", "shelves", "bins", "zones"];
const INDENT: Record<LayoutKind, number> = {
  aisles: 0,
  racks: 1,
  shelves: 2,
  bins: 3,
  zones: 0,
};

export function WarehouseHierarchyPanel({
  document,
  selectedId,
  onSelect,
}: {
  document: LayoutDocument;
  selectedId: string | null;
  onSelect: (id: string) => void;
}) {
  return (
    <Stack
      sx={{ maxHeight: 360, overflow: "auto" }}
      aria-label="Layout hierarchy"
    >
      <Typography variant="subtitle2" sx={{ px: 1, pt: 0.5 }}>
        Hierarchy
      </Typography>
      <List dense disablePadding>
        {ORDER.flatMap((kind) =>
          document[kind].map((entity) => {
            const id = `${kind}:${entity.id}`;
            const label =
              entity.code ??
              (entity.level != null
                ? `Level ${entity.level}`
                : `${LAYOUT_LABELS[kind]} ${entity.id}`);
            return (
              <ListItem key={id} disablePadding sx={{ pl: INDENT[kind] * 1.5 }}>
                <Button
                  fullWidth
                  size="small"
                  color={selectedId === id ? "primary" : "inherit"}
                  onClick={() => onSelect(id)}
                  sx={{ justifyContent: "flex-start", minHeight: 36 }}
                >
                  {label}
                </Button>
              </ListItem>
            );
          }),
        )}
        <ListSubheader disableSticky>Docks and inspection poses</ListSubheader>
        <ListItem>
          <Typography variant="caption" color="text.secondary">
            Edit these framed entities in Dock and Coordinates tabs. Both render
            in warehouse_map.
          </Typography>
        </ListItem>
      </List>
    </Stack>
  );
}
