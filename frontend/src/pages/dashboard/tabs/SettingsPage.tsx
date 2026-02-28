import React, { useEffect, useMemo, useState } from "react";
import Header from "../../../components/dashboard/Header";

import {
  Alert,
  Box,
  Button,
  Container,
  Divider,
  FormControlLabel,
  Paper,
  Stack,
  Switch,
  Tab,
  Tabs,
  TextField,
  Typography,
} from "@mui/material";
import Grid from "@mui/material/Grid";


type TelemetrySettings = {
  mqtt_broker: string;
  mqtt_port: number;
  mqtt_user: string;
  mqtt_pass?: string;
  mqtt_use_tls: boolean;
  mqtt_ca_certs: string;
  opcua_endpoint: string;
  opcua_security_policy: string;
  opcua_cert_path: string;
  opcua_key_path: string;
  telem_log_interval_sec: number;
  telemetry_topic: string;
};

type AISettings = {
    llm_provider: string;
    llm_api_base: string;
    llm_model: string;
    llm_api_key?: string;
};

type CredentialsSettings = {
    google_maps_api_key: string;
    drone_conn: string;
    admin_emails: string;
    admin_domains: string;
};

type HardwareSettings = {
      battery_capacity_wh: number;
      energy_reserve_frac: number;
      cruise_speed_mps: number;
      cruise_power_w: number;
      heartbeat_timeout: number;
      enforce_preflight_range: boolean;
};

type PreflightSettings = {
  HDOP_MAX: number;
  SAT_MIN: number;
  HOME_MAX_DIST: number;
  GPS_FIX_TYPE_MIN: number;
  EKF_THRESHOLD: number;
  COMPASS_HEALTH_REQUIRED: boolean;
  BATTERY_MIN_V: number;
  BATTERY_MIN_PERCENT: number;
  HEARTBEAT_MAX_AGE: number;
  MSG_RATE_MIN_HZ: number;
  RTL_MIN_ALT: number;
  MIN_CLEARANCE: number;
  AGL_MIN: number;
  AGL_MAX: number;
  MAX_RANGE_M: number;
  MAX_WAYPOINTS: number;
  NFZ_BUFFER_M: number;
  A_LAT_MAX: number;
  BANK_MAX_DEG: number;
  TURN_PENALTY_S: number;
  WP_RADIUS_M: number;
};

type RaspberrySettings = {
    raspberry_ip: string;
    raspberry_user: string;
    raspberry_host: string;
    raspberry_password?: string;
    ssh_key_path: string;
};

type CameraSettings=  {
  drone_video_source: string;
  drone_video_width: number;
  drone_video_height: number;
  drone_video_fps: number;
  drone_video_timeout: number;
  drone_video_save_path: string;
  drone_video_fallback: string;
  drone_video_enabled: boolean;
  drone_video_save_stream: boolean;
};

type SettingsDoc = {
  telemetry: TelemetrySettings;
  ai: AISettings;
  credentials: CredentialsSettings;
  hardware: HardwareSettings;
  preflight: PreflightSettings;
  raspberry: RaspberrySettings;
  camera: CameraSettings;
  updated_at?: string;
};

const MASK = "********";

const DEFAULTS: SettingsDoc = {
    telemetry: {},
    ai: {},
    credentials: { },
    hardware: { },
    preflight: {},
    raspberry: {},
    camera: {},
    updated_at: new Date().toISOString(),
};

export default function SettingsPage() {
  const [tab, setTab] = useState(0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [doc, setDoc] = useState<SettingsDoc>(DEFAULTS);
  const [lastLoaded, setLastLoaded] = useState<SettingsDoc>(DEFAULTS);

  const dirty = useMemo(() => JSON.stringify(doc) !== JSON.stringify(lastLoaded), [doc, lastLoaded]);

  const validateSettings = (): string | null => {
    if (doc.preflight.BATTERY_MIN_PERCENT < 10 || doc.preflight.BATTERY_MIN_PERCENT > 50) return "Battery Min (%) must be 10-50%.";
    if (doc.preflight.BANK_MAX_DEG > 45) return "Bank angle exceeds 45° safe limit.";
    return null;
  };

  async function fetchSettings() {
    setLoading(true); setErr(null);
    try {
      const res = await fetch("/api/settings");
      if (!res.ok) throw new Error("Failed to fetch");
      const data = await res.json();
      setDoc(data); setLastLoaded(data);
    } catch (e: any) { setErr(e.message); } finally { setLoading(false); }
  }

  async function saveSettings() {
    const vErr = validateSettings();
    if (vErr) { setErr(vErr); return; }
    setSaving(true);
    try {
      await fetch("/api/settings", { method: "PUT", body: JSON.stringify(doc), headers: { "Content-Type": "application/json" } });
      await fetchSettings();
    } catch (e: any) { setErr(e.message); } finally { setSaving(false); }
  }

  useEffect(() => { void fetchSettings(); }, []);

  const update = (section: keyof SettingsDoc, field: string, value: any) => {
    setDoc(prev => ({ ...prev, [section]: { ...prev[section], [field]: value } }));
    if (err) setErr(null);
  };

  const handleFileUpload = (section: keyof SettingsDoc, field: string) => (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (file) {
      const reader = new FileReader();
      reader.onload = (e) => {
        const content = e.target?.result as string;
        update(section, field, content);
      };
      reader.readAsText(file);
    }
  };

  // Helper function to split array into chunks for column layout
  const chunkArray = (array: any[], chunkSize: number) => {
    const chunks = [];
    for (let i = 0; i < array.length; i += chunkSize) {
      chunks.push(array.slice(i, i + chunkSize));
    }
    return chunks;
  };

  return (
    <>
      <Header />
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper variant="outlined" sx={{ p: 0 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto">
            <Tab label="Telemetry" />
            <Tab label="AI" />
            <Tab label="Credentials" />
            <Tab label="Hardware" />
            <Tab label="Preflight Check Params" />
            <Tab label="Raspberry" />
            <Tab label="Camera" />
          </Tabs>
          <Divider />

          <Box sx={{ p: 3 }}>
            {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}

            {/* TELEMETRY TAB */}
            {tab === 0 && (
              <Grid container spacing={3}>
                <Grid item size={{ xs: 12, md: 4 }} >
                  <Typography variant="h6" gutterBottom>MQTT Broker</Typography>
                  <Stack spacing={3}>
                    <TextField fullWidth label="Broker" value={doc.telemetry?.mqtt_broker} onChange={e => update("telemetry", "mqtt_broker", e.target.value)} />
                    <TextField fullWidth label="Port" type="number" value={doc.telemetry?.mqtt_port} onChange={e => update("telemetry", "mqtt_port", Number(e.target.value))} />
                    <TextField fullWidth label="User" value={doc.telemetry?.mqtt_user} onChange={e => update("telemetry", "mqtt_user", e.target.value)} />
                    <TextField fullWidth label="Password" type="password" placeholder={MASK} value={doc.telemetry?.mqtt_pass} onChange={e => update("telemetry", "mqtt_pass", e.target.value)} />
                    <FormControlLabel control={<Switch checked={doc.telemetry?.mqtt_use_tls} onChange={e => update("telemetry", "mqtt_use_tls", e.target.checked)} />} label="Use TLS" />

                      <Button variant="outlined" component="label" fullWidth>
                        Upload CA Certificate
                        <input type="file" hidden accept=".pem,.crt,.ca" onChange={handleFileUpload("telemetry", "mqtt_ca_certs")} />
                      </Button>
                      {doc.telemetry?.mqtt_ca_certs && <Typography variant="caption" display="block" sx={{ mt: 1 }}>✓ CA certificate uploaded</Typography>}
                    </Stack>
                </Grid>
                <Grid item size={{ xs: 12, md: 4 }}>
                  <Typography variant="h6" gutterBottom>OPC UA</Typography>
                  <Stack spacing={3}>
                    <TextField fullWidth label="Endpoint" value={doc.telemetry?.opcua_endpoint} onChange={e => update("telemetry", "opcua_endpoint", e.target.value)} />
                    <TextField fullWidth label="Security Policy" value={doc.telemetry?.opcua_security_policy} onChange={e => update("telemetry", "opcua_security_policy", e.target.value)} />

                      <Button variant="outlined" component="label" fullWidth>
                        Upload OPC UA Certificate
                        <input type="file" hidden accept=".pem,.crt,.cert" onChange={handleFileUpload("telemetry", "opcua_cert_path")} />
                      </Button>
                      {doc.telemetry?.opcua_cert_path && <Typography variant="caption" display="block" sx={{ mt: 1 }}>✓ Certificate uploaded</Typography>}

                      <Button variant="outlined" component="label" fullWidth>
                        Upload OPC UA Key
                        <input type="file" hidden accept=".pem,.key" onChange={handleFileUpload("telemetry", "opcua_key_path")} />
                      </Button>
                      {doc.telemetry?.opcua_key_path && <Typography variant="caption" display="block" sx={{ mt: 1 }}>✓ Key uploaded</Typography>}
                  </Stack>
                </Grid>
                <Grid item size={{ xs: 12, md: 4 }}>
                  <Typography variant="h6" gutterBottom>Logging & Topics</Typography>
                  <Stack spacing={3}>
                    <TextField fullWidth label="Log Interval (sec)" type="number" value={doc.telemetry?.telem_log_interval_sec} onChange={e => update("telemetry", "telem_log_interval_sec", Number(e.target.value))} />
                    <TextField fullWidth label="Telemetry Topic" value={doc.telemetry?.telemetry_topic} onChange={e => update("telemetry", "telemetry_topic", e.target.value)} />
                  </Stack>
              </Grid>
              </Grid>
            )}

            {/* AI TAB */}
            {tab === 1 && (
              <Grid container spacing={4}>
                <Grid item size={{ xs: 12, md: 6 }} >
                  <Typography variant="h6" gutterBottom>LLM Provider</Typography>
                   <Stack spacing={3}>
                    <TextField fullWidth label="Provider" value={doc.ai?.llm_provider} onChange={e => update("ai", "llm_provider", e.target.value)} />
                    <TextField fullWidth label="Model" value={doc.ai?.llm_model} onChange={e => update("ai", "llm_model", e.target.value)} />
                    <TextField fullWidth label="API Base" value={doc.ai?.llm_api_base} onChange={e => update("ai", "llm_api_base", e.target.value)} />
                    <TextField fullWidth label="API Key" type="password" placeholder={MASK} value={doc.ai?.llm_api_key} onChange={e => update("ai", "llm_api_key", e.target.value)} />
                  </Stack>
                </Grid>

              </Grid>
            )}

            {/* CREDENTIALS TAB */}
            {tab === 2 && (
              <Grid container spacing={3}>
                <Grid item size={{ xs: 12, md: 6 }} >
                  <Typography variant="h6" gutterBottom>External APIs</Typography>
                   <Stack spacing={3}>
                    <TextField fullWidth label="Google Maps API Key" type="password" value={doc.credentials?.google_maps_api_key} onChange={e => update("credentials", "google_maps_api_key", e.target.value)} />
                    <TextField fullWidth label="Drone Connection String" value={doc.credentials?.drone_conn} onChange={e => update("credentials", "drone_conn", e.target.value)} />
                  </Stack>
                </Grid>
                <Grid item size={{ xs: 12, md: 6 }} >
                  <Typography variant="h6" gutterBottom>Administration</Typography>
                   <Stack spacing={3}>
                    <TextField fullWidth label="Admin Emails" value={doc.credentials?.admin_emails} onChange={e => update("credentials", "admin_emails", e.target.value)} />
                    <TextField fullWidth label="Admin Domains" value={doc.credentials?.admin_domains} onChange={e => update("credentials", "admin_domains", e.target.value)} />
                  </Stack>
                </Grid>
              </Grid>
            )}

            {/* HARDWARE TAB */}
            {tab === 3 && (
              <Grid container spacing={3}>
                <Grid item size={{ xs: 12, md: 6 }} >
                  <Typography variant="h6" gutterBottom>Drone</Typography>
                   <Stack spacing={3}>
                    <TextField fullWidth label="Battery Capacity (Wh)" type="number" value={doc.hardware?.battery_capacity_wh} onChange={e => update("hardware", "battery_capacity_wh", Number(e.target.value))} />
                    <TextField fullWidth label="Energy Reserve Fraction" type="number" inputProps={{ step: 0.1, min: 0, max: 1 }} value={doc.hardware?.energy_reserve_frac} onChange={e => update("hardware", "energy_reserve_frac", Number(e.target.value))} />
                    <TextField fullWidth label="Cruise Power (W)" type="number" value={doc.hardware?.cruise_power_w} onChange={e => update("hardware", "cruise_power_w", Number(e.target.value))} />
                    <TextField fullWidth label="Cruise Speed (mps)" type="number" value={doc.hardware?.cruise_speed_mps} onChange={e => update("hardware", "cruise_speed_mps", Number(e.target.value))} />
                    <TextField fullWidth label="Heartbeat Timeout" type="number" value={doc.hardware?.heartbeat_timeout} onChange={e => update("hardware", "heartbeat_timeout", Number(e.target.value))} />
                    <FormControlLabel control={<Switch checked={doc.hardware?.enforce_preflight_range} onChange={e => update("hardware", "enforce_preflight_range", e.target.checked)} />} label="Enforce Preflight Range" />
                  </Stack>
                </Grid>

              </Grid>
            )}

            {/* PREFLIGHT CHECK TAB */}
            {tab === 4 && (
              <Grid container spacing={4}>
                <Grid item size={{ xs: 12, md: 3 }} >
                  <Typography variant="h6" gutterBottom>GPS & Navigation</Typography>
                   <Stack spacing={3}>
                    <TextField fullWidth label="HDOP Max" type="number" value={doc.preflight?.HDOP_MAX} onChange={e => update("preflight", "HDOP_MAX", Number(e.target.value))} />
                    <TextField fullWidth label="Satellites Min" type="number" value={doc.preflight?.SAT_MIN} onChange={e => update("preflight", "SAT_MIN", Number(e.target.value))} />
                    <TextField fullWidth label="Home Max Dist (m)" type="number" value={doc.preflight?.HOME_MAX_DIST} onChange={e => update("preflight", "HOME_MAX_DIST", Number(e.target.value))} />
                    <TextField fullWidth label="GPS Fix Type Min" type="number" value={doc.preflight?.GPS_FIX_TYPE_MIN} onChange={e => update("preflight", "GPS_FIX_TYPE_MIN", Number(e.target.value))} />
                    <TextField fullWidth label="EKF Threshold" type="number" value={doc.preflight?.EKF_THRESHOLD} onChange={e => update("preflight", "EKF_THRESHOLD", Number(e.target.value))} />
                    <FormControlLabel control={<Switch checked={doc.preflight?.COMPASS_HEALTH_REQUIRED} onChange={e => update("preflight", "COMPASS_HEALTH_REQUIRED", e.target.checked)} />} label="Compass Health Required" />
                  </Stack>
                </Grid>
                <Grid item size={{ xs: 12, md: 3 }} >
                  <Typography variant="h6" gutterBottom>Battery & Heartbeat</Typography>
                   <Stack spacing={3}>
                    <TextField fullWidth label="Battery Min (V)" type="number" value={doc.preflight?.BATTERY_MIN_V} onChange={e => update("preflight", "BATTERY_MIN_V", Number(e.target.value))} />
                    <TextField fullWidth label="Battery Min %" type="number" value={doc.preflight?.BATTERY_MIN_PERCENT} onChange={e => update("preflight", "BATTERY_MIN_PERCENT", Number(e.target.value))} />
                    <TextField fullWidth label="Heartbeat Max Age" type="number" value={doc.preflight?.HEARTBEAT_MAX_AGE} onChange={e => update("preflight", "HEARTBEAT_MAX_AGE", Number(e.target.value))} />
                    <TextField fullWidth label="Msg Rate Min (Hz)" type="number" value={doc.preflight?.MSG_RATE_MIN_HZ} onChange={e => update("preflight", "MSG_RATE_MIN_HZ", Number(e.target.value))} />
                    <TextField fullWidth label="RTL Min Alt (m)" type="number" value={doc.preflight?.RTL_MIN_ALT} onChange={e => update("preflight", "RTL_MIN_ALT", Number(e.target.value))} />
                    <TextField fullWidth label="Min Clearance (m)" type="number" value={doc.preflight?.MIN_CLEARANCE} onChange={e => update("preflight", "MIN_CLEARANCE", Number(e.target.value))} />
                  </Stack>
                </Grid>

                <Grid item size={{ xs: 12, md: 3 }} >
                  <Typography variant="h6" gutterBottom>Altitude & Range</Typography>
                   <Stack spacing={3}>
                    <TextField fullWidth label="AGL Min (m)" type="number" value={doc.preflight?.AGL_MIN} onChange={e => update("preflight", "AGL_MIN", Number(e.target.value))} />
                    <TextField fullWidth label="AGL Max (m)" type="number" value={doc.preflight?.AGL_MAX} onChange={e => update("preflight", "AGL_MAX", Number(e.target.value))} />
                    <TextField fullWidth label="Max Range (m)" type="number" value={doc.preflight?.MAX_RANGE_M} onChange={e => update("preflight", "MAX_RANGE_M", Number(e.target.value))} />
                    <TextField fullWidth label="Max Waypoints" type="number" value={doc.preflight?.MAX_WAYPOINTS} onChange={e => update("preflight", "MAX_WAYPOINTS", Number(e.target.value))} />
                    <TextField fullWidth label="NFZ Buffer (m)" type="number" value={doc.preflight?.NFZ_BUFFER_M} onChange={e => update("preflight", "NFZ_BUFFER_M", Number(e.target.value))} />
                  </Stack>
                </Grid>
                <Grid item size={{ xs: 12, md: 3 }} >
                  <Typography variant="h6" gutterBottom>Performance</Typography>
                  <Stack spacing={3}>
                    <TextField fullWidth label="A Lat Max" type="number" value={doc.preflight?.A_LAT_MAX} onChange={e => update("preflight", "A_LAT_MAX", Number(e.target.value))} />
                    <TextField fullWidth label="Bank Max (deg)" type="number" value={doc.preflight?.BANK_MAX_DEG} onChange={e => update("preflight", "BANK_MAX_DEG", Number(e.target.value))} />
                    <TextField fullWidth label="Turn Penalty (s)" type="number" value={doc.preflight?.TURN_PENALTY_S} onChange={e => update("preflight", "TURN_PENALTY_S", Number(e.target.value))} />
                    <TextField fullWidth label="WP Radius (m)" type="number" value={doc.preflight?.WP_RADIUS_M} onChange={e => update("preflight", "WP_RADIUS_M", Number(e.target.value))} />
                  </Stack>
                </Grid>
              </Grid>
            )}

            {/* RASPBERRY TAB */}
            {tab === 5 && (
                <Grid container spacing={3}>
                <Grid item size={{ xs: 12, md: 6 }} >
                  <Typography variant="h6" gutterBottom>Raspberry Pi Connection</Typography>
                   <Stack spacing={3}>
                    <TextField fullWidth label="IP Address" value={doc.raspberry?.raspberry_ip} onChange={e => update("raspberry", "raspberry_ip", e.target.value)} />
                    <TextField fullWidth label="Hostname" value={doc.raspberry?.raspberry_host} onChange={e => update("raspberry", "raspberry_host", e.target.value)} />
                    <TextField fullWidth label="Username" value={doc.raspberry?.raspberry_user} onChange={e => update("raspberry", "raspberry_user", e.target.value)} />
                    <TextField fullWidth label="Password" type="password" placeholder={MASK} value={doc.raspberry?.raspberry_password} onChange={e => update("raspberry", "raspberry_password", e.target.value)} />
                    <TextField fullWidth label="Streaming Script Path" value={doc.raspberry?.raspberry_streaming_script_path} onChange={e => update("raspberry", "raspberry_streaming_script_path", e.target.value)} />

                      <Button variant="outlined" component="label" fullWidth>
                        Upload SSH Key
                        <input type="file" hidden accept=".pem,.key,.pub" onChange={handleFileUpload("raspberry", "ssh_key_path")} />
                      </Button>
                      {doc.raspberry?.ssh_key_path && <Typography variant="caption" display="block" sx={{ mt: 1 }}>✓ SSH key uploaded</Typography>}

                  </Stack>
                </Grid>
                </Grid>
            )}


            {/* CAMERA TAB */}
            {tab === 6 && (
              <Grid container spacing={3}>
                <Grid item size={{ xs: 12, md: 6 }}>
                  <Typography variant="h6" gutterBottom>Drone Camera Parameters</Typography>
                  <Stack spacing={3}>
                    <TextField fullWidth label="Camera Source" value={doc.camera?.drone_video_source} onChange={e => update("camera", "drone_video_source", e.target.value)} />
                    <TextField fullWidth label="Width" value={doc.camera?.drone_video_width} onChange={e => update("camera", "drone_video_width", e.target.value)} />
                    <TextField fullWidth label="Height" value={doc.camera?.drone_video_height} onChange={e => update("camera", "drone_video_height", e.target.value)} />
                    <TextField fullWidth label="FPS" value={doc.camera?.drone_video_fps} onChange={e => update("camera", "drone_video_fps", e.target.value)} />
                    <TextField fullWidth label="Timeout" value={doc.camera?.drone_video_timeout} onChange={e => update("camera", "drone_video_timeout", e.target.value)} />
                    <TextField fullWidth label="Fallback" value={doc.camera?.drone_video_fallback} onChange={e => update("camera", "drone_video_fallback", e.target.value)} />

                    <Stack direction="row" spacing={25}>
                      <FormControlLabel
                        control={<Switch checked={doc.camera?.drone_video_enabled} onChange={e => update("camera", "drone_video_enabled", e.target.checked)} />}
                        label="Enable Stream"
                      />
                      <FormControlLabel
                        control={<Switch checked={doc.camera?.drone_video_save_stream} onChange={e => update("camera", "drone_video_save_stream", e.target.checked)} />}
                        label="Save Stream"
                      />
                    </Stack>
                  </Stack>
                </Grid>
              </Grid>
            )}



            <Box sx={{ mt: 4, display: "flex", justifyContent: "flex-end", gap: 2 }}>
              <Button onClick={fetchSettings} variant="outlined">Reset</Button>
              <Button disabled={!dirty || saving} onClick={saveSettings} variant="contained">
                {saving ? "Saving..." : "Save All Changes"}
              </Button>
            </Box>
          </Box>
        </Paper>
      </Container>
    </>
  );
}