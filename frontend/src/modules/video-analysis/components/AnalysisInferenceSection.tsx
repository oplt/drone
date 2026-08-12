import {
  Alert,
  FormControlLabel,
  MenuItem,
  Slider,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import { ActionIconButton } from "../../../shared/ui/ActionIconButton";
import { useVisionModels } from "../../agriculture/hooks/useVisionModels";
import { MODEL_OPTIONS } from "../modelOptions";
import type { AnalysisControlsProps } from "./analysisControlsTypes";

export function AnalysisInferenceSection(props: AnalysisControlsProps) {
  const models = useVisionModels();
  const modelValue = props.payload.model_version_id
    ? `registered:${props.payload.model_version_id}`
    : `builtin:${props.payload.model_name}`;
  return (
    <Stack spacing={2}>
      <Typography variant="h6">Detection profile</Typography>
      <Alert severity="info">
        Advanced diagnostics for operators. Farmer agriculture workflows stay
        capability-based; SAHI/tracker promotion requires EXP-002 gates (ADR-004).
      </Alert>
      <TextField
        select
        size="small"
        label="Model"
        value={modelValue}
        onChange={(event) => {
          const [kind, value] = event.target.value.split(":", 2);
          props.onPayload({
            ...props.payload,
            model_name: kind === "builtin" ? value : (models.data?.find((model) => model.id === value)?.architecture ?? "yolo26s.pt"),
            model_version_id: kind === "registered" ? value : null,
          });
        }}
      >
        {MODEL_OPTIONS.map((option) => <MenuItem key={option.value} value={`builtin:${option.value}`}>{option.label}</MenuItem>)}
        {models.data?.filter((model) => model.status === "production").map((model) => (
          <MenuItem key={model.id} value={`registered:${model.id}`}>
            {model.name} · v{model.version} · {model.crop}
          </MenuItem>
        ))}
      </TextField>
      <Stack spacing={0.5}>
        <FormControlLabel
          control={<Switch
            checked={props.payload.tracking_enabled ?? false}
            onChange={(event) => props.onPayload({
              ...props.payload,
              tracking_enabled: event.target.checked,
              tracker_type: "bytetrack",
              frame_stride_seconds: event.target.checked ? Math.min(2, props.payload.frame_stride_seconds) : props.payload.frame_stride_seconds,
            })}
          />}
          label="Track objects"
        />
        <Typography variant="caption" color="text.secondary">Adds job-isolated tracking and estimated unique-object counts.</Typography>
      </Stack>
      <Stack spacing={0.5}>
        <FormControlLabel
          control={<Switch checked={props.payload.small_object_mode ?? false} onChange={(event) => props.onPayload({ ...props.payload, small_object_mode: event.target.checked })} />}
          label="Small-object mode"
        />
        <Typography variant="caption" color="text.secondary">Better for small fruit, weeds, and distant objects. Uses slower sliced inference.</Typography>
      </Stack>
      <Typography variant="body2">Sampling interval: {props.payload.frame_stride_seconds.toFixed(1)} s</Typography>
      <Slider
        aria-label="Sampling interval seconds"
        min={0.2}
        max={props.payload.tracking_enabled ? 2 : 5}
        step={0.1}
        value={props.payload.frame_stride_seconds}
        onChange={(_, value) => props.onPayload({ ...props.payload, frame_stride_seconds: value as number })}
      />
      {props.payload.tracking_enabled && props.payload.frame_stride_seconds > 1.5 ? (
        <Alert severity="warning">Dense sampling improves track continuity in moving drone footage.</Alert>
      ) : null}
      <Typography variant="body2">Minimum confidence: {(props.payload.confidence_threshold * 100).toFixed(0)}%</Typography>
      <Slider
        aria-label="Minimum confidence"
        min={0.05}
        max={0.95}
        step={0.05}
        value={props.payload.confidence_threshold}
        onChange={(_, value) => props.onPayload({ ...props.payload, confidence_threshold: value as number })}
      />
      <ActionIconButton
        variant="play"
        title={props.starting ? "Queuing…" : "Run analysis"}
        color="secondary"
        loading={props.starting}
        disabled={!props.video}
        onClick={props.onAnalyze}
      />
    </Stack>
  );
}
