import {
  Alert,
  Box,
  Divider,
  IconButton,
  Stack,
  TextField,
  Tooltip,
  Typography,
} from "@mui/material";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import type { PatrolSensorIntegration } from "../api/eventTriggerConfigApi";

type EventTriggerConnectionPanelProps = {
  integration: PatrolSensorIntegration | null;
  selectedFieldId: number | null;
  hasGeofence: boolean;
  saving?: boolean;
  saveError?: string | null;
};

function CopyField({
  label,
  value,
  ariaLabel,
}: {
  label: string;
  value: string;
  ariaLabel: string;
}) {
  return (
    <TextField
      variant="filled"
      label={label}
      size="small"
      fullWidth
      value={value}
      InputProps={{
        readOnly: true,
        endAdornment: (
          <Tooltip title={`Copy ${label.toLowerCase()}`}>
            <IconButton
              size="small"
              edge="end"
              aria-label={ariaLabel}
              onClick={() => void navigator.clipboard.writeText(value)}
            >
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </Tooltip>
        ),
      }}
    />
  );
}

export function EventTriggerConnectionPanel({
  integration,
  selectedFieldId,
  hasGeofence,
  saving = false,
  saveError = null,
}: EventTriggerConnectionPanelProps) {
  if (selectedFieldId == null) {
    return (
      <Alert severity="info" sx={{ py: 0.5, flexBasis: "100%" }}>
        Select or save a property geofence above. Event-trigger flight parameters auto-save for that
        property.
      </Alert>
    );
  }

  if (!hasGeofence) {
    return (
      <Alert severity="warning" sx={{ py: 0.5, flexBasis: "100%" }}>
        Draw and save a property geofence polygon before connecting webhook or MQTT triggers.
      </Alert>
    );
  }

  const mqtt = integration?.mqtt ?? null;

  return (
    <Box sx={{ flexBasis: "100%", width: "100%" }}>
      <Stack spacing={1.5}>
        <Typography variant="caption" sx={{ color: "text.secondary" }}>
          Sensor connections
        </Typography>
        {saveError && (
          <Alert severity="error" sx={{ py: 0.5 }}>
            {saveError}
          </Alert>
        )}
        {saving && (
          <Typography variant="caption" color="text.secondary">
            Saving event-trigger setup…
          </Typography>
        )}
        {!integration ? (
          <Alert severity="info" sx={{ py: 0.5 }}>
            Adjust parameters below to save the active event-trigger setup for this property.
          </Alert>
        ) : (
          <>
            <Typography variant="body2" fontWeight={600}>
              Webhook
            </Typography>
            <CopyField
              label="Webhook URL"
              value={integration.webhook_url}
              ariaLabel="Copy webhook URL"
            />
            <Alert severity="info" sx={{ py: 0.5 }}>
              POST JSON with a unique <code>trigger_id</code>, optional <code>sensor_id</code>, and
              optional <code>coordinates</code> <code>[lon, lat]</code>. Auth: {integration.auth_hint}
            </Alert>

            <Divider flexItem />

            <Typography variant="body2" fontWeight={600}>
              MQTT
            </Typography>
            {mqtt ? (
              <>
                <Stack direction={{ xs: "column", sm: "row" }} spacing={1}>
                  <CopyField
                    label="Broker"
                    value={`${mqtt.broker}:${mqtt.port}${mqtt.use_tls ? " (TLS)" : ""}`}
                    ariaLabel="Copy MQTT broker"
                  />
                  <CopyField label="Publish topic" value={mqtt.topic} ariaLabel="Copy MQTT topic" />
                </Stack>
                <Alert severity="info" sx={{ py: 0.5 }}>
                  Publish the same JSON payload to <code>{mqtt.topic}</code> at QoS {mqtt.qos}.{" "}
                  {mqtt.auth_hint}
                </Alert>
                <Typography variant="caption" sx={{ color: "text.secondary", display: "block" }}>
                  Example payload: {JSON.stringify(integration.example_body)}
                </Typography>
              </>
            ) : (
              <Alert severity="warning" sx={{ py: 0.5 }}>
                MQTT broker details are unavailable. Configure Settings → Telemetry → MQTT Broker and
                restart the backend.
              </Alert>
            )}

            <Typography variant="caption" sx={{ color: "text.secondary", display: "block" }}>
              No per-sensor registration is required—connect devices via webhook or MQTT using the
              saved Property Patrol setup above.
            </Typography>
          </>
        )}
      </Stack>
    </Box>
  );
}
