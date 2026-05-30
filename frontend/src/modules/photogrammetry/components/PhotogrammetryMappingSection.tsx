import {
  Alert,
  Box,
  Chip,
  LinearProgress,
  MenuItem,
  Paper,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import InfoLabel from "../../../shared/ui/InfoLabel";
import { ActionIconButton, ActionIconLabel } from "../../../shared/ui/ActionIconButton";
import { INFO_INPUT_LABEL_PROPS } from "../../mission-workflow";
import type { MappingJobRecord } from "../types";
import { IncompleteJobsTable } from "./IncompleteJobsTable";
import type { usePhotogrammetryMapping } from "../hooks/usePhotogrammetryMapping";

type MappingVm = ReturnType<typeof usePhotogrammetryMapping>;

export function PhotogrammetryMappingSection({
  mapping,
  selectedFieldId,
  onOpen3DPlanning,
}: {
  mapping: MappingVm;
  selectedFieldId: number | null;
  onOpen3DPlanning: () => void;
}) {
  const jobStatus = mapping.jobStatus;

  return (
    <>
      <Paper variant="outlined" sx={{ p: 1.5, borderRadius: 2 }}>
        <Typography variant="subtitle2">3D Field Map Workflow</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
          Upload geotagged images to auto-create a field, or select a saved field for
          manual/drone-sync processing. Once the map is ready, continue route planning in
          3D mode.
        </Typography>

        <Stack spacing={1.2} sx={{ mt: 1 }}>
          <TextField
            variant="filled"
            select
            size="small"
            label="Input source"
            value={mapping.mappingInputMode}
            onChange={(e) => {
              const mode = e.target.value as "upload" | "drone_sync";
              mapping.setMappingInputMode(mode);
              if (mode === "drone_sync") mapping.setMappingInputFiles([]);
            }}
          >
            <MenuItem value="upload">Upload Images</MenuItem>
            <MenuItem value="drone_sync">Direct Drone Sync</MenuItem>
          </TextField>

          {mapping.mappingInputMode === "upload" && (
            <Stack direction="row" spacing={0.25} alignItems="center" flexWrap="wrap">
              <ActionIconLabel variant="upload" title="Select Images">
                <input
                  hidden
                  multiple
                  type="file"
                  accept="image/*,.jpg,.jpeg,.png,.tif,.tiff"
                  onChange={(e) => {
                    const files = e.target.files ? Array.from(e.target.files) : [];
                    mapping.setMappingInputFiles(files);
                  }}
                />
              </ActionIconLabel>
              <Chip
                size="small"
                color={mapping.mappingInputFiles.length > 0 ? "success" : "default"}
                label={`${mapping.mappingInputFiles.length} file(s)`}
              />
            </Stack>
          )}

          {mapping.mappingInputMode === "drone_sync" && (
            <TextField
              variant="filled"
              size="small"
              label={
                <InfoLabel
                  label="Sync source folder (optional)"
                  info="If blank, backend tries auto-discovery in configured drone sync directory."
                />
              }
              InputLabelProps={INFO_INPUT_LABEL_PROPS}
              value={mapping.mappingSyncSourceDir}
              onChange={(e) => mapping.setMappingSyncSourceDir(e.target.value)}
              placeholder="field_12 or /mnt/gs-sync/field_12"
            />
          )}

          <Tooltip
            title={
              !mapping.mappingFieldReady
                ? "Select a saved field or draw a named field first"
                : mapping.mappingInputMode === "upload" &&
                    mapping.mappingInputFiles.length === 0
                  ? "Please select images to upload"
                  : ""
            }
          >
            <span>
              <ActionIconButton
                variant="add"
                title={
                  mapping.busy
                    ? "Preparing 3D Field Map…"
                    : mapping.mappingWillAutoSaveField
                      ? "Save Field & Create 3D Field Map"
                      : mapping.mappingWillInferFieldFromUpload
                        ? "Create Map From Images"
                        : "Create 3D Field Map"
                }
                color="primary"
                loading={mapping.busy}
                disabled={
                  mapping.busy ||
                  mapping.mappingJobRunning ||
                  !mapping.mappingFieldReady ||
                  (mapping.mappingInputMode === "upload" && mapping.mappingInputFiles.length === 0)
                }
                onClick={() => void mapping.create3DFieldMap()}
              />
            </span>
          </Tooltip>

          {mapping.mappingInputMode !== "upload" &&
            selectedFieldId == null &&
            !mapping.mappingWillAutoSaveField && (
              <Alert severity="info" sx={{ py: 0.5 }}>
                Select a saved field or draw a named field first. Mapping jobs are linked
                to saved field IDs.
              </Alert>
            )}

          {mapping.mappingWillInferFieldFromUpload && (
            <Alert severity="info" sx={{ py: 0.5 }}>
              No saved field is selected. Upload mode will create one from the images&apos;
              GPS coordinates, then place the processed map on the field automatically.
            </Alert>
          )}

          {mapping.mappingWillAutoSaveField && (
            <Alert severity="info" sx={{ py: 0.5 }}>
              This field is not saved yet. Starting 3D mapping will save it first.
            </Alert>
          )}

          {mapping.error && (
            <Alert severity="error" sx={{ py: 0.5 }}>
              {mapping.error}
            </Alert>
          )}

          {jobStatus && <MappingJobProgress jobStatus={jobStatus} mappingJobRunning={mapping.mappingJobRunning} onOpen3DPlanning={onOpen3DPlanning} />}
        </Stack>
      </Paper>

      <IncompleteJobsTable
        jobs={mapping.jobs}
        onDelete={(id) => void mapping.handleDeleteJob(id)}
        onResume={(id) => void mapping.handleResumeJob(id)}
      />
    </>
  );
}

function MappingJobProgress({
  jobStatus,
  mappingJobRunning,
  onOpen3DPlanning,
}: {
  jobStatus: MappingJobRecord;
  mappingJobRunning: boolean;
  onOpen3DPlanning: () => void;
}) {
  return (
    <Box>
      <Stack direction="row" spacing={1} sx={{ flexWrap: "wrap", rowGap: 1, mb: 0.5 }}>
        <Chip size="small" variant="outlined" label={`Job #${jobStatus.job_id}`} />
        <Chip
          size="small"
          color={
            jobStatus.status === "ready"
              ? "success"
              : jobStatus.status === "failed"
                ? "error"
                : "warning"
          }
          label={jobStatus.status}
        />
        <Chip size="small" label={`${jobStatus.progress}%`} />
      </Stack>
      <LinearProgress
        variant="determinate"
        value={Math.max(0, Math.min(100, jobStatus.progress))}
      />
      {mappingJobRunning &&
        jobStatus.status !== "ready" &&
        jobStatus.status !== "failed" && (
          <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
            Processing is active. You can continue route planning once status is ready.
          </Typography>
        )}
      {jobStatus.status === "ready" && (
        <Alert severity="success" sx={{ mt: 1, py: 0.5 }}>
          3D field map is ready. Mesh + boundary are loaded for route planning.
          <ActionIconButton
            variant="open"
            title="Open 3D Planning"
            size="medium"
            onClick={onOpen3DPlanning}
            sx={{ ml: 0.5, verticalAlign: "middle" }}
          />
        </Alert>
      )}
    </Box>
  );
}
