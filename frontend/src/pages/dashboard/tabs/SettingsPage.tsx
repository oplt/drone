import React from "react";
import {
  Box,
  Card,
  CardContent,
  Typography,
  TextField,
  Button,
  Stack,
  Divider,
  Switch,
  FormControlLabel,
  Alert,
  Grid,
  Chip,
} from "@mui/material";
import { getToken } from "../../../auth";

type FieldType = "string" | "number" | "boolean" | "password";

type FieldSpec = {
  key: string;
  label: string;
  type: FieldType;
  helperText?: string;
};

const FIELD_SPECS: { title: string; fields: FieldSpec[] }[] = [
  {
    title: "General",
    fields: [
      { key: "google_maps_api_key", label: "Google Maps API Key", type: "password" },
      { key: "llm_provider", label: "LLM Provider", type: "string" },
      { key: "llm_api_base", label: "LLM API Base", type: "string" },
      { key: "llm_api_key", label: "LLM API Key", type: "password" },
      { key: "llm_model", label: "LLM Model", type: "string" },
    ],
  },
  {
    title: "MQTT",
    fields: [
      { key: "mqtt_broker", label: "MQTT Broker", type: "string" },
      { key: "mqtt_port", label: "MQTT Port", type: "number" },
      { key: "mqtt_user", label: "MQTT User", type: "string" },
      { key: "mqtt_pass", label: "MQTT Password", type: "password" },
      { key: "telemetry_topic", label: "Telemetry Topic", type: "string" },
    ],
  },
  {
    title: "Operations Security",
    fields: [
      { key: "mqtt_use_tls", label: "MQTT TLS Enabled", type: "boolean" },
      { key: "mqtt_ca_certs", label: "MQTT CA Cert Path", type: "string" },
      { key: "opcua_security_policy", label: "OPC UA Policy", type: "string" },
      { key: "opcua_cert_path", label: "OPC UA Cert Path", type: "string" },
      { key: "opcua_key_path", label: "OPC UA Key Path", type: "string" },
    ],
  },
  {
    title: "Drone / Field Ops",
    fields: [
      { key: "opcua_endpoint", label: "OPC UA Endpoint", type: "string" },
      { key: "drone_conn", label: "Drone Connection", type: "string" },
      { key: "drone_conn_mavproxy", label: "Drone Conn (MAVProxy)", type: "string" },
      { key: "heartbeat_timeout", label: "Heartbeat Timeout (sec)", type: "number" },
      { key: "telem_log_interval_sec", label: "Telemetry Log Interval (sec)", type: "number" },
      { key: "enforce_preflight_range", label: "Enforce Preflight Range", type: "boolean" },
    ],
  },
  {
    title: "Auth / JWT",
    fields: [
      { key: "jwt_secret", label: "JWT Secret", type: "password" },
      { key: "jwt_algorithm", label: "JWT Algorithm", type: "string" },
      { key: "jwt_exp_minutes", label: "JWT Exp Minutes", type: "number" },
    ],
  },
  {
    title: "Edge / SSH",
    fields: [
      { key: "rasperry_ip", label: "Raspberry IP", type: "string" },
      { key: "rasperry_user", label: "Raspberry User", type: "string" },
      { key: "rasperry_host", label: "Raspberry Host", type: "string" },
      { key: "rasperry_password", label: "Raspberry Password", type: "password" },
      { key: "rasperry_streaming_script_path", label: "Streaming Script Path", type: "string" },
      { key: "ssh_key_path", label: "SSH Key Path", type: "string" },
    ],
  },
  {
    title: "Battery Model",
    fields: [
      { key: "battery_capacity_wh", label: "Battery Capacity (Wh)", type: "number" },
      { key: "cruise_power_w", label: "Cruise Power (W)", type: "number" },
      { key: "cruise_speed_mps", label: "Cruise Speed (m/s)", type: "number" },
      { key: "energy_reserve_frac", label: "Energy Reserve (0-1)", type: "number" },
    ],
  },
  {
    title: "Imagery Streaming",
    fields: [
      { key: "drone_video_enabled", label: "Video Enabled", type: "boolean" },
      { key: "drone_video_source", label: "Video Source", type: "string" },
      { key: "drone_video_width", label: "Video Width", type: "number" },
      { key: "drone_video_height", label: "Video Height", type: "number" },
      { key: "drone_video_fps", label: "Video FPS", type: "number" },
      { key: "drone_video_timeout", label: "Video Timeout (sec)", type: "number" },
      { key: "drone_video_fallback", label: "Video Fallback", type: "string" },
      { key: "drone_video_save_stream", label: "Save Stream", type: "boolean" },
      { key: "drone_video_save_path", label: "Save Path", type: "string" },
      { key: "drone_video_network_mode", label: "Network Mode", type: "string" },
      { key: "drone_video_network_ip", label: "Network IP", type: "string" },
      { key: "drone_video_network_port", label: "Network Port", type: "number" },
      { key: "drone_video_rtsp_port", label: "RTSP Port", type: "number" },
      { key: "drone_video_wifi_ssid", label: "WiFi SSID", type: "string" },
      { key: "drone_video_wifi_password", label: "WiFi Password", type: "password" },
    ],
  },
];

export default function SettingsPage() {
  const API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";
  const token = getToken();

  const [data, setData] = React.useState<Record<string, any>>({});
  const [loading, setLoading] = React.useState(true);
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [ok, setOk] = React.useState<string | null>(null);

  React.useEffect(() => {
    if (!token) return;
    setLoading(true);
    setError(null);

    fetch(`${API_BASE}/settings`, {
      headers: { Authorization: `Bearer ${token}` },
    })
      .then(async (r) => {
        if (!r.ok) throw new Error(await r.text());
        return r.json();
      })
      .then((json) => setData(json ?? {}))
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));
  }, [API_BASE, token]);

  const setValue = (key: string, value: any) => {
    setOk(null);
    setData((prev) => ({ ...prev, [key]: value }));
  };

  const onSave = async () => {
    setSaving(true);
    setError(null);
    setOk(null);

    try {
      const r = await fetch(`${API_BASE}/settings`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          Authorization: `Bearer ${token}`,
        },
        body: JSON.stringify({ data }),
      });

      if (!r.ok) throw new Error(await r.text());
      const json = await r.json();
      setData(json ?? {});
      setOk("Settings saved.");
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  if (!token) return <Alert severity="error">Not authenticated.</Alert>;
  if (loading) return <>Loading...</>;

  return (
    <Box sx={{ width: "100%", maxWidth: 1400, p: 2 }}>
      <Stack spacing={3}>
        <Stack spacing={1}>
          <Typography variant="h4">Settings</Typography>
          <Typography variant="body2" sx={{ color: "text.secondary" }}>
            Administrative configuration for agronomy systems. Changes apply immediately.
          </Typography>
        </Stack>

        <Alert severity="warning">
          Settings are restricted to administrative users. Coordinate changes with farm operations.
        </Alert>

        {error && <Alert severity="error">{error}</Alert>}
        {ok && <Alert severity="success">{ok}</Alert>}

        <Grid container spacing={3}>
          {FIELD_SPECS.map((section) => (
            <Grid key={section.title} size={{ xs: 12, md: 6, lg: 4 }}>
              <Card sx={{ height: "100%" }}>
                <CardContent>
                  <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
                    <Typography variant="h6">{section.title}</Typography>
                    {section.title === "Operations Security" && (
                      <Chip size="small" color="warning" label="Critical" />
                    )}
                  </Stack>
                  <Divider sx={{ mb: 2 }} />
                  <Stack spacing={2}>
                    {section.fields.map((f) => {
                      const value = data[f.key];

                      if (f.type === "boolean") {
                        return (
                          <FormControlLabel
                            key={f.key}
                            control={
                              <Switch
                                checked={Boolean(value)}
                                onChange={(e) => setValue(f.key, e.target.checked)}
                              />
                            }
                            label={f.label}
                          />
                        );
                      }

                      const isNumber = f.type === "number";
                      const inputType =
                        f.type === "password" ? "password" : isNumber ? "number" : "text";

                      return (
                        <TextField
                          key={f.key}
                          label={f.label}
                          type={inputType}
                          value={value ?? ""}
                          helperText={f.helperText}
                          onChange={(e) => {
                            const raw = e.target.value;
                            setValue(f.key, isNumber ? (raw === "" ? "" : Number(raw)) : raw);
                          }}
                          fullWidth
                        />
                      );
                    })}
                  </Stack>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>

        <Stack direction="row" justifyContent="center">
          <Button variant="contained" onClick={onSave} disabled={saving} sx={{ width: "200px" }}>
            {saving ? "Saving..." : "Save"}
          </Button>
        </Stack>
      </Stack>
    </Box>
  );
}
