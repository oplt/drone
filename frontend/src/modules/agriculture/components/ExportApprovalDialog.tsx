import {
  Alert,
  Button,
  Chip,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  MenuItem,
  Select,
  Stack,
  Typography,
} from "@mui/material";
import { useState } from "react";
import type { AgricultureExport } from "../types";

export function ExportApprovalDialog({
  exports,
  pending,
  error,
  onGenerate,
  onDownload,
}: {
  exports: AgricultureExport[];
  pending: boolean;
  error: boolean;
  onGenerate: (artifactKind: string, format: string) => void;
  onDownload: (id: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [artifactKind, setArtifactKind] = useState("report");
  const [format, setFormat] = useState("geojson");
  return (
    <Stack
      component="section"
      aria-labelledby="export-approval-heading"
      spacing={1}
    >
      <Stack direction="row" justifyContent="space-between">
        <div>
          <Typography id="export-approval-heading" variant="subtitle2">
            Approved exports
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Only confirmed or explicitly approved sources may leave the review
            workflow.
          </Typography>
        </div>
        <Button size="small" variant="contained" onClick={() => setOpen(true)}>
          Generate export
        </Button>
      </Stack>
      {error ? (
        <Alert severity="warning">
          Export blocked until the selected source is explicitly approved.
        </Alert>
      ) : null}
      {exports.map((item) => (
        <Stack
          key={item.id}
          direction={{ xs: "column", sm: "row" }}
          spacing={1}
          alignItems={{ sm: "center" }}
        >
          <Chip size="small" label={`${item.artifact_kind} · ${item.format}`} />
          <Chip
            size="small"
            color={item.status === "ready" ? "success" : "warning"}
            label={item.status}
          />
          <Typography variant="caption" sx={{ flex: 1 }}>
            Expires{" "}
            {item.expires_at ? new Date(item.expires_at).toLocaleString() : "—"}
          </Typography>
          {item.status === "ready" ? (
            <Button size="small" onClick={() => onDownload(item.id)}>
              Get signed link
            </Button>
          ) : null}
        </Stack>
      ))}
      <Dialog
        open={open}
        onClose={() => setOpen(false)}
        fullWidth
        maxWidth="xs"
        aria-labelledby="export-dialog-title"
      >
        <DialogTitle id="export-dialog-title">
          Approve export request
        </DialogTitle>
        <DialogContent>
          <Stack spacing={1.5} sx={{ pt: 1 }}>
            <Select
              value={artifactKind}
              onChange={(event) => {
                const next = event.target.value;
                setArtifactKind(next);
                if (next === "intervention_zones" && !["geojson", "shapefile"].includes(format)) {
                  setFormat("geojson");
                }
              }}
              inputProps={{ "aria-label": "Export artifact kind" }}
            >
              <MenuItem value="report">Report</MenuItem>
              <MenuItem value="observations">Confirmed observations</MenuItem>
              <MenuItem value="inspection_actions">
                Approved inspection actions
              </MenuItem>
              <MenuItem value="prescription">Approved prescription</MenuItem>
              <MenuItem value="intervention_zones">
                Approved intervention zones
              </MenuItem>
            </Select>
            <Select
              value={format}
              onChange={(event) => setFormat(event.target.value)}
              inputProps={{ "aria-label": "Export format" }}
            >
              <MenuItem value="geojson">GeoJSON</MenuItem>
              <MenuItem value="shapefile">Shapefile</MenuItem>
              {artifactKind !== "intervention_zones" ? <MenuItem value="csv">CSV</MenuItem> : null}
              {artifactKind !== "intervention_zones" ? <MenuItem value="pdf">PDF</MenuItem> : null}
            </Select>
            <Alert severity="info">
              Generation is audited and does not execute field treatment.
            </Alert>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancel</Button>
          <Button
            variant="contained"
            disabled={pending}
            onClick={() => {
              onGenerate(artifactKind, format);
              setOpen(false);
            }}
          >
            {pending ? "Generating…" : "Approve and generate"}
          </Button>
        </DialogActions>
      </Dialog>
    </Stack>
  );
}
