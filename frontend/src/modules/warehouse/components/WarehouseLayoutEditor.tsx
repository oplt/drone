import {
  Alert,
  Box,
  Button,
  IconButton,
  MenuItem,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import AddRoundedIcon from "@mui/icons-material/AddRounded";
import ContentCopyRoundedIcon from "@mui/icons-material/ContentCopyRounded";
import RedoRoundedIcon from "@mui/icons-material/RedoRounded";
import SaveRoundedIcon from "@mui/icons-material/SaveRounded";
import UndoRoundedIcon from "@mui/icons-material/UndoRounded";
import { useState } from "react";
import type { LayoutKind } from "../api/warehouseLayoutApi";
import { previewLayoutImport } from "../api/warehouseLayoutApi";
import { LAYOUT_LABELS, useWarehouseLayoutEditor } from "../layoutEditorState";
import { moveEntity } from "../utils/warehouseLayoutScene";
import { WarehouseLayoutCanvas } from "./WarehouseLayoutCanvas";
import { WarehouseLayoutIssuePanel } from "./WarehouseLayoutIssuePanel";
import { WarehouseHierarchyPanel } from "./WarehouseHierarchyPanel";
import { WarehouseDisplacementReview } from "./WarehouseDisplacementReview";

export function WarehouseLayoutEditor({
  warehouseMapId,
  token,
}: {
  warehouseMapId: number;
  token?: string | null;
}) {
  const editor = useWarehouseLayoutEditor(warehouseMapId, token);
  const { selected, selectedEntity } = editor;
  const [importPreviewIssues, setImportPreviewIssues] = useState<
    Array<{ code: string; message: string }>
  >([]);
  return (
    <Stack spacing={2} aria-label="Warehouse hierarchy editor">
      <Box
        sx={{ display: "flex", gap: 1, flexWrap: "wrap", alignItems: "center" }}
      >
        {(Object.keys(LAYOUT_LABELS) as LayoutKind[]).map((kind) => (
          <Button
            key={kind}
            size="small"
            startIcon={<AddRoundedIcon />}
            onClick={() => editor.add(kind)}
          >
            {LAYOUT_LABELS[kind]}
          </Button>
        ))}
        <Tooltip title="Undo">
          <span>
            <IconButton
              aria-label="Undo"
              disabled={!editor.canUndo}
              onClick={editor.undo}
            >
              <UndoRoundedIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Redo">
          <span>
            <IconButton
              aria-label="Redo"
              disabled={!editor.canRedo}
              onClick={editor.redo}
            >
              <RedoRoundedIcon />
            </IconButton>
          </span>
        </Tooltip>
        <Tooltip title="Duplicate selection">
          <span>
            <IconButton
              aria-label="Duplicate selection"
              disabled={!selectedEntity}
              onClick={editor.duplicate}
            >
              <ContentCopyRoundedIcon />
            </IconButton>
          </span>
        </Tooltip>
        <TextField
          size="small"
          type="number"
          label="Snap grid (m)"
          value={editor.grid}
          inputProps={{ min: 0, step: 0.05 }}
          onChange={(event) =>
            editor.setGrid(Math.max(0, Number(event.target.value)))
          }
          sx={{ width: 120 }}
        />
      </Box>
      {editor.error && (
        <Alert severity="error" onClose={() => editor.setError(null)}>
          {editor.error}
        </Alert>
      )}
      <Box
        sx={{
          display: "grid",
          gridTemplateColumns: {
            xs: "1fr",
            lg: "200px minmax(0, 2fr) minmax(220px, 1fr)",
          },
          gap: 2,
        }}
      >
        <WarehouseHierarchyPanel
          document={editor.present}
          selectedId={selected ? `${selected.kind}:${selected.id}` : null}
          onSelect={(id) => {
            const [kind, rawId] = id.split(":");
            editor.setSelected({ kind: kind as LayoutKind, id: Number(rawId) });
          }}
        />
        <WarehouseLayoutCanvas
          nodes={editor.nodes}
          selectedId={selected ? `${selected.kind}:${selected.id}` : null}
          mode={editor.mode}
          onModeChange={editor.setMode}
          onSelect={(id) => {
            const [kind, rawId] = id.split(":");
            editor.setSelected({ kind: kind as LayoutKind, id: Number(rawId) });
          }}
        />
        <Stack spacing={1.5}>
          <Typography variant="subtitle1">Selection</Typography>
          {selected && selectedEntity ? (
            <>
              <TextField
                size="small"
                label={selected.kind === "shelves" ? "Level" : "Code"}
                value={selectedEntity.level ?? selectedEntity.code ?? ""}
                onChange={(event) =>
                  editor.mutate(selected.kind, selected.id, (row) =>
                    selected.kind === "shelves"
                      ? { ...row, level: Number(event.target.value) }
                      : { ...row, code: event.target.value },
                  )
                }
              />
              {selected.kind === "zones" && (
                <TextField
                  select
                  size="small"
                  label="Zone type"
                  value={selectedEntity.kind ?? "keep_out"}
                  onChange={(event) =>
                    editor.mutate(selected.kind, selected.id, (row) => ({
                      ...row,
                      kind: event.target.value,
                    }))
                  }
                >
                  <MenuItem value="no_fly">No fly</MenuItem>
                  <MenuItem value="keep_out">Keep out</MenuItem>
                  <MenuItem value="slow">Slow</MenuItem>
                  <MenuItem value="landing">Landing</MenuItem>
                </TextField>
              )}
              {(["x_m", "y_m", "z_m"] as const).map((field) => (
                <TextField
                  key={field}
                  size="small"
                  type="number"
                  label={field.replace("_m", " (m)")}
                  value={Number(selectedEntity.geometry[field] ?? 0)}
                  onChange={(event) =>
                    editor.mutate(selected.kind, selected.id, (row) => ({
                      ...row,
                      geometry: {
                        ...row.geometry,
                        [field]: Number(event.target.value),
                      },
                    }))
                  }
                />
              ))}
              <Button
                onClick={() =>
                  editor.mutate(selected.kind, selected.id, (row) =>
                    moveEntity(row, 0, 0, editor.grid),
                  )
                }
              >
                Align to origin
              </Button>
            </>
          ) : (
            <Typography variant="body2" color="text.secondary">
              Select geometry to edit precise coordinates.
            </Typography>
          )}
        </Stack>
      </Box>
      <Stack direction="row" spacing={1}>
        <Button
          variant="contained"
          startIcon={<SaveRoundedIcon />}
          disabled={editor.busy}
          onClick={() => void editor.save()}
        >
          Save draft
        </Button>
        <Button
          variant="outlined"
          disabled={editor.busy || !editor.layout}
          onClick={() => void editor.runValidation()}
        >
          Validate on server
        </Button>
        <Button
          variant="outlined"
          disabled={editor.busy || !editor.layout}
          onClick={() => {
            if (!editor.layout) return;
            void previewLayoutImport(
              warehouseMapId,
              editor.layout,
              editor.present,
              token,
            ).then((report) => setImportPreviewIssues(report.issues));
          }}
        >
          Import dry-run
        </Button>
      </Stack>
      {importPreviewIssues.length > 0 ? (
        <Alert severity="info">
          Import dry-run reported {importPreviewIssues.length} issue(s).
        </Alert>
      ) : null}
      <Typography variant="caption" color="text.secondary">
        Use arrow keys to nudge the selected entity (Shift = larger step).
      </Typography>
      <WarehouseLayoutIssuePanel issues={editor.issues} />
      {editor.layout && (
        <WarehouseDisplacementReview
          warehouseMapId={warehouseMapId}
          version={editor.layout.version}
          token={token}
        />
      )}
    </Stack>
  );
}
