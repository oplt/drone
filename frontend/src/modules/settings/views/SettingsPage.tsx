import React, { useEffect, useMemo, useState } from "react";
import Header from "../../../shared/layout/WorkflowHeader";
import { IconButton, InputAdornment } from "@mui/material";
import Visibility from "@mui/icons-material/Visibility";
import VisibilityOff from "@mui/icons-material/VisibilityOff";
import Avatar from "@mui/material/Avatar";
import Skeleton from "@mui/material/Skeleton";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { getToken } from "../../../modules/session";
import { fetchCurrentUser, updateCurrentUser } from "../../session/api/sessionApi";
import {
  fetchAppSettings,
  type LlmProfile,
  type LlmProviderId,
  type LlmProviderSettings,
  updateAppSettings,
  uploadAppSettingsFile,
} from "../api/settingsApi";
import {
  DEFAULT_AI_PROVIDERS,
  DEFAULT_LLM_PROFILES,
  DEFAULT_TASK_DEFAULTS,
  PROVIDER_IDS,
} from "../aiSettingsDefaults";
import { AiSettingsPanel } from "../components/AiSettingsPanel";
import type {
  AISettings,
  SettingsDoc,
  SettingsSection,
  UserResponse,
  UserUpdate,
} from "../settingsTypes";

import { ActionIconButton, ActionIconLabel } from "../../../shared/ui/ActionIconButton";
import {
  Alert,
  Box,
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

const MASK = "********";

const DEFAULTS: SettingsDoc = {
  telemetry: {
    mqtt_broker: "localhost",
    mqtt_port: 1883,
    mqtt_user: "",
    mqtt_pass: "",
    mqtt_use_tls: false,
    mqtt_ca_certs: "",
    opcua_endpoint: "",
    opcua_security_policy: "",
    opcua_cert_path: "",
    opcua_key_path: "",
    telem_log_interval_sec: 2,
    telemetry_topic: "ardupilot/telemetry",
  },
  ai: {
    llm_provider: "ollama",
    llm_api_base: "",
    llm_model: "",
    llm_api_key: "",
    active_provider: "ollama",
    system_prompt: "You support drone operations. Be precise and operationally safe.",
    providers: DEFAULT_AI_PROVIDERS,
    task_defaults: DEFAULT_TASK_DEFAULTS,
    profiles: DEFAULT_LLM_PROFILES,
    default_profile_id: "ollama",
    task_overrides: {},
  },
  credentials: {
    google_maps_api_key: "",
    drone_conn: "",
    admin_emails: "",
    admin_domains: "",
  },
  hardware: {
    battery_capacity_wh: 77,
    energy_reserve_frac: 0.2,
    cruise_speed_mps: 8,
    cruise_power_w: 180,
    heartbeat_timeout: 5,
    enforce_preflight_range: false,
  },
  preflight: {
    HDOP_MAX: 2,
    SAT_MIN: 10,
    HOME_MAX_DIST: 30,
    GPS_FIX_TYPE_MIN: 3,
    EKF_THRESHOLD: 0.8,
    COMPASS_HEALTH_REQUIRED: true,
    BATTERY_MIN_V: 0,
    BATTERY_MIN_PERCENT: 20,
    HEARTBEAT_MAX_AGE: 3,
    MSG_RATE_MIN_HZ: 2,
    RTL_MIN_ALT: 15,
    MIN_CLEARANCE: 3,
    AGL_MIN: 5,
    AGL_MAX: 120,
    MAX_RANGE_M: 1500,
    MAX_WAYPOINTS: 60,
    NFZ_BUFFER_M: 15,
    A_LAT_MAX: 3,
    BANK_MAX_DEG: 30,
    TURN_PENALTY_S: 2,
    WP_RADIUS_M: 2,
  },
  raspberry: {
    raspberry_ip: "",
    raspberry_user: "",
    raspberry_host: "",
    raspberry_password: "",
    ssh_key_path: "",
    raspberry_streaming_script_path: "",
  },
  camera: {
    drone_video_source: "",
    drone_video_source_gazebo: "udp://127.0.0.1:5600",
    drone_video_use_gazebo: false,
    drone_video_width: 640,
    drone_video_height: 480,
    drone_video_fps: 30,
    drone_video_timeout: 10,
    drone_video_save_path: "./backend/video/recordings/",
    drone_video_fallback: "",
    drone_video_enabled: true,
    drone_video_save_stream: false,
  },
  photogrammetry: {
    PHOTOGRAMMETRY_DRONE_SYNC_DIR: "backend/storage/drone_sync",
    PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR: "backend/storage/staging",
    PHOTOGRAMMETRY_INPUTS_DIR: "backend/storage/mapping_jobs_inputs",
    PHOTOGRAMMETRY_STORAGE_DIR: "backend/storage/mapping",
    PHOTOGRAMMETRY_STORAGE_BASE_URL: "/mapping-assets",
    PHOTOGRAMMETRY_3DTILES_CMD: "",
    PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET: false,
    WEBODM_BASE_URL: "http://localhost:8001",
    WEBODM_API_TOKEN: "",
    WEBODM_PROJECT_ID: 1,
    WEBODM_MOCK_MODE: false,
    MAPPING_JOB_QUEUE_BACKEND: "celery",
    CELERY_PHOTOGRAMMETRY_QUEUE: "photogrammetry",
    PHOTOGRAMMETRY_ASSET_SIGNING_SECRET: "",
  },
  alerts: {
    enabled: true,
    check_interval_sec: 5,
    dedupe_window_sec: 300,
    operation_geofence_id: null,
    monitor_herd_ids: "",
    herd_isolation_threshold_m: 250,
    low_battery_percent: 25,
    weak_link_percent: 35,
    high_wind_mps: 12,
    route_in_app: true,
    route_email: false,
    route_sms: false,
    email_recipients: "",
    sms_recipients: "",
    smtp_host: "",
    smtp_port: 587,
    smtp_user: "",
    smtp_password: "",
    smtp_from: "",
    smtp_use_tls: true,
    twilio_account_sid: "",
    twilio_auth_token: "",
    twilio_from_number: "",
  },
  updated_at: undefined,
};

const normalizeDoc = (raw: Partial<SettingsDoc>): SettingsDoc => ({
  ...DEFAULTS,
  ...raw,
  telemetry: { ...DEFAULTS.telemetry, ...(raw.telemetry ?? {}) },
  ai: {
    ...DEFAULTS.ai,
    ...(raw.ai ?? {}),
    providers: {
      ...Object.fromEntries(
        PROVIDER_IDS.map((providerId) => [
          providerId,
          {
            ...DEFAULT_AI_PROVIDERS[providerId],
            ...((raw.ai as Partial<AISettings> | undefined)?.providers?.[providerId] ?? {}),
          },
        ]),
      ) as Record<LlmProviderId, LlmProviderSettings>,
    },
    task_defaults: {
      ...DEFAULT_TASK_DEFAULTS,
      ...((raw.ai as Partial<AISettings> | undefined)?.task_defaults ?? {}),
    },
    profiles: (raw.ai as Partial<AISettings> | undefined)?.profiles?.length
      ? ((raw.ai as Partial<AISettings>).profiles ?? [])
      : DEFAULT_LLM_PROFILES,
    default_profile_id:
      (raw.ai as Partial<AISettings> | undefined)?.default_profile_id || "ollama",
    task_overrides: (raw.ai as Partial<AISettings> | undefined)?.task_overrides ?? {},
  },
  credentials: { ...DEFAULTS.credentials, ...(raw.credentials ?? {}) },
  hardware: { ...DEFAULTS.hardware, ...(raw.hardware ?? {}) },
  preflight: { ...DEFAULTS.preflight, ...(raw.preflight ?? {}) },
  raspberry: { ...DEFAULTS.raspberry, ...(raw.raspberry ?? {}) },
  camera: { ...DEFAULTS.camera, ...(raw.camera ?? {}) },
  photogrammetry: { ...DEFAULTS.photogrammetry, ...(raw.photogrammetry ?? {}) },
  alerts: { ...DEFAULTS.alerts, ...(raw.alerts ?? {}) },
});

type SettingsTabKey =
  | "profile"
  | "telemetry"
  | "ai"
  | "credentials"
  | "hardware"
  | "preflight"
  | "alerts"
  | "raspberry"
  | "camera"
  | "photogrammetry";

const SETTINGS_TAB_INDEX: Record<SettingsTabKey, number> = {
  profile: 0,
  telemetry: 1,
  ai: 2,
  credentials: 3,
  hardware: 4,
  preflight: 5,
  alerts: 6,
  raspberry: 7,
  camera: 8,
  photogrammetry: 9,
};

export default function SettingsPage({ initialTab = "profile" }: { initialTab?: SettingsTabKey }) {
  const token = getToken();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState(SETTINGS_TAB_INDEX[initialTab] ?? 0);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [doc, setDoc] = useState<SettingsDoc>(DEFAULTS);
  const [lastLoaded, setLastLoaded] = useState<SettingsDoc>(DEFAULTS);
  const [fullName, setFullName] = useState("");
  const [saveProfileSuccess, setSaveProfileSuccess] = useState(false);
  const [saveProfileError, setSaveProfileError] = useState<string | null>(null);

  const { data: user, isLoading: userLoading, error: userError } = useQuery<UserResponse>({
    queryKey: ["me"],
    enabled: Boolean(token),
    queryFn: async (): Promise<UserResponse> => {
      const user = await fetchCurrentUser();
      const fullName = [user.first_name, user.last_name].filter(Boolean).join(" ").trim();
      return {
        id: String(user.id),
        email: user.email,
        full_name: fullName || user.email,
        created_at: undefined,
      };
    },
  });

  useEffect(() => {
    if (user) {
      setFullName(user.full_name ?? "");
    }
  }, [user]);

  const profileMutation = useMutation({
    mutationFn: (payload: UserUpdate) =>
      updateCurrentUser(payload, token),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["me"] });
      setSaveProfileSuccess(true);
      setSaveProfileError(null);
    },
    onError: (error: unknown) => {
      setSaveProfileError(error instanceof Error ? error.message : "Failed to save profile.");
      setSaveProfileSuccess(false);
    },
  });

  const dirty = useMemo(() => JSON.stringify(doc) !== JSON.stringify(lastLoaded), [doc, lastLoaded]);

  const validateSettings = (): string | null => {
    if (doc.preflight.BATTERY_MIN_PERCENT < 10 || doc.preflight.BATTERY_MIN_PERCENT > 50) return "Battery Min (%) must be 10-50%.";
    if (doc.preflight.BANK_MAX_DEG > 45) return "Bank angle exceeds 45° safe limit.";
    for (const providerId of PROVIDER_IDS) {
      const provider = doc.ai.providers[providerId];
      if (!provider?.enabled) continue;
      try {
        const parsed = new URL(provider.api_base);
        if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
      } catch {
        return `${providerId} API base must be a valid http(s) URL.`;
      }
    }
    for (const profile of doc.ai.profiles) {
      if (!profile.enabled) continue;
      try {
        const parsed = new URL(profile.api_base);
        if (!["http:", "https:"].includes(parsed.protocol)) throw new Error();
      } catch {
        return `${profile.name || profile.provider} API base must be a valid http(s) URL.`;
      }
    }
    return null;
  };

  async function fetchSettings() {
    setLoading(true); setErr(null);
    try {
      const data = normalizeDoc(await fetchAppSettings<SettingsDoc>());
      setDoc(data); setLastLoaded(data);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to fetch settings");
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings() {
    const vErr = validateSettings();
    if (vErr) { setErr(vErr); return; }
    setSaving(true); setErr(null);
    try {
      const saved = normalizeDoc(await updateAppSettings<SettingsDoc>(doc));
      setDoc(saved);
      setLastLoaded(saved);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => { void fetchSettings(); }, []);

  const handleSaveProfile = () => {
    setSaveProfileSuccess(false);
    setSaveProfileError(null);
    profileMutation.mutate({ full_name: fullName.trim() });
  };

  const update = (section: SettingsSection, field: string, value: unknown) => {
    setDoc(prev => ({ ...prev, [section]: { ...prev[section], [field]: value } }));
    if (err) setErr(null);
  };

  const persistAiProfiles = (profiles: LlmProfile[]) => {
    const applyProfiles = (prev: SettingsDoc): SettingsDoc => {
      const defaultProfile = profiles.find((profile) => profile.id === prev.ai.default_profile_id);
      return {
        ...prev,
        ai: {
          ...prev.ai,
          profiles,
          ...(defaultProfile
            ? {
                llm_provider: defaultProfile.provider,
                llm_api_base: defaultProfile.api_base,
                llm_model: defaultProfile.model,
                active_provider: defaultProfile.provider,
              }
            : {}),
        },
      };
    };
    setDoc(applyProfiles);
    setLastLoaded(applyProfiles);
  };

  const handleFileUpload = (section: SettingsSection, field: string) => async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file) return;

    try {
      setErr(null);
      const formData = new FormData();
      formData.append("section", section);
      formData.append("field", field);
      formData.append("file", file);

      const payload = (await uploadAppSettingsFile(formData)) as { path?: string };
      if (typeof payload?.path !== "string" || !payload.path) {
        throw new Error("Upload succeeded but no path was returned.");
      }
      update(section, field, payload.path);
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Failed to upload file.");
    } finally {
      event.target.value = "";
    }
  };

function SecretField(props: React.ComponentProps<typeof TextField>) {
  const [show, setShow] = useState(false);
  return (
    <TextField variant="filled"
      {...props}
      type={show ? "text" : "password"}
      InputProps={{
        endAdornment: (
          <InputAdornment position="end">
            <IconButton
              onClick={() => setShow(v => !v)}
              onMouseDown={e => e.preventDefault()}
              edge="end"
              size="small"
              aria-label={show ? "Hide value" : "Show value"}
            >
              {show ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
            </IconButton>
          </InputAdornment>
        ),
      }}
    />
  );
}

  return (
    <>
      <Header />
      <Container maxWidth="lg" sx={{ py: 4 }}>
        <Paper variant="outlined" sx={{ p: 0 }}>
          <Tabs value={tab} onChange={(_, v) => setTab(v)} variant="scrollable" scrollButtons="auto">
            <Tab label="Profile" />
            <Tab label="Telemetry" />
            <Tab label="AI" />
            <Tab label="Credentials" />
            <Tab label="Hardware" />
            <Tab label="Preflight Check Params" />
            <Tab label="Alerts" />
            <Tab label="Raspberry" />
            <Tab label="Camera" />
            <Tab label="Photogrammetry" />
          </Tabs>
          <Divider />

          <Box sx={{ p: 3 }}>
            {err && <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert>}
            {loading && <Alert severity="info" sx={{ mb: 2 }}>Loading settings...</Alert>}

            {/* PROFILE TAB */}
            {tab === 0 && (
              <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 4 }}>
                  <Stack alignItems="center" spacing={2}>
                    {userLoading ? (
                      <Skeleton variant="circular" width={80} height={80} />
                    ) : (
                      <Avatar sx={{ width: 80, height: 80, bgcolor: "primary.main", fontSize: 28, fontWeight: 700 }}>
                        {(user?.full_name ?? user?.email ?? "?")
                          .split(/\s+/)
                          .filter(Boolean)
                          .slice(0, 2)
                          .map((part) => part[0]?.toUpperCase() ?? "")
                          .join("")}
                      </Avatar>
                    )}
                    <Typography variant="body2" color="text.secondary">
                      {user?.created_at ? `Member since ${new Date(user.created_at).toLocaleDateString()}` : "Profile details"}
                    </Typography>
                  </Stack>
                </Grid>
                <Grid size={{ xs: 12, md: 8 }}>
                  <Stack spacing={2.5}>
                    {userError ? (
                      <Alert severity="error">Failed to load profile. Refresh page.</Alert>
                    ) : null}
                    {saveProfileSuccess ? (
                      <Alert severity="success" onClose={() => setSaveProfileSuccess(false)}>
                        Profile updated successfully.
                      </Alert>
                    ) : null}
                    {saveProfileError ? (
                      <Alert severity="error" onClose={() => setSaveProfileError(null)}>
                        {saveProfileError}
                      </Alert>
                    ) : null}
                    <TextField
                      variant="filled"
                      fullWidth
                      label="Full name"
                      value={fullName}
                      onChange={(event) => setFullName(event.target.value)}
                      disabled={userLoading || !user}
                    />
                    <TextField
                      variant="filled"
                      fullWidth
                      label="Email"
                      value={user?.email ?? ""}
                      disabled
                    />
                    <Box>
                      <ActionIconButton
                        variant="upgrade"
                        title={profileMutation.isPending ? "Saving…" : "Save profile"}
                        color="primary"
                        loading={profileMutation.isPending}
                        disabled={profileMutation.isPending || !fullName.trim() || !user}
                        onClick={handleSaveProfile}
                      />
                    </Box>
                  </Stack>
                </Grid>
              </Grid>
            )}

            {/* TELEMETRY TAB */}
            {tab === 1 && (
              <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 4 }} >
                  <Typography variant="h6" gutterBottom>MQTT Broker</Typography>
                  <Stack spacing={3}>
                    <TextField variant="filled" fullWidth label="Broker" value={doc.telemetry?.mqtt_broker} onChange={e => update("telemetry", "mqtt_broker", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Port" type="number" value={doc.telemetry?.mqtt_port} onChange={e => update("telemetry", "mqtt_port", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="User" value={doc.telemetry?.mqtt_user} onChange={e => update("telemetry", "mqtt_user", e.target.value)} />
                    <SecretField fullWidth label="Password" placeholder={MASK} value={doc.telemetry?.mqtt_pass} onChange={e => update("telemetry", "mqtt_pass", e.target.value)} />
                    <FormControlLabel control={<Switch checked={doc.telemetry?.mqtt_use_tls} onChange={e => update("telemetry", "mqtt_use_tls", e.target.checked)} />} label="Use TLS" />

                      <ActionIconLabel variant="upload" title="Upload CA Certificate">
                        <input type="file" hidden accept=".pem,.crt,.ca" onChange={handleFileUpload("telemetry", "mqtt_ca_certs")} />
                      </ActionIconLabel>
                      {doc.telemetry?.mqtt_ca_certs && <Typography variant="caption" display="block" sx={{ mt: 1 }}>✓ CA certificate uploaded</Typography>}
                    </Stack>
                </Grid>
                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="h6" gutterBottom>OPC UA</Typography>
                  <Stack spacing={3}>
                    <TextField variant="filled" fullWidth label="Endpoint" value={doc.telemetry?.opcua_endpoint} onChange={e => update("telemetry", "opcua_endpoint", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Security Policy" value={doc.telemetry?.opcua_security_policy} onChange={e => update("telemetry", "opcua_security_policy", e.target.value)} />

                      <ActionIconLabel variant="upload" title="Upload OPC UA Certificate">
                        <input type="file" hidden accept=".pem,.crt,.cert" onChange={handleFileUpload("telemetry", "opcua_cert_path")} />
                      </ActionIconLabel>
                      {doc.telemetry?.opcua_cert_path && <Typography variant="caption" display="block" sx={{ mt: 1 }}>✓ Certificate uploaded</Typography>}

                      <ActionIconLabel variant="upload" title="Upload OPC UA Key">
                        <input type="file" hidden accept=".pem,.key" onChange={handleFileUpload("telemetry", "opcua_key_path")} />
                      </ActionIconLabel>
                      {doc.telemetry?.opcua_key_path && <Typography variant="caption" display="block" sx={{ mt: 1 }}>✓ Key uploaded</Typography>}
                  </Stack>
                </Grid>
                <Grid size={{ xs: 12, md: 4 }}>
                  <Typography variant="h6" gutterBottom>Logging & Topics</Typography>
                  <Stack spacing={3}>
                    <TextField variant="filled" fullWidth label="Log Interval (sec)" type="number" value={doc.telemetry?.telem_log_interval_sec} onChange={e => update("telemetry", "telem_log_interval_sec", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Telemetry Topic" value={doc.telemetry?.telemetry_topic} onChange={e => update("telemetry", "telemetry_topic", e.target.value)} />
                  </Stack>
              </Grid>
              </Grid>
            )}

            {/* AI TAB */}
            {tab === 2 && (
              <AiSettingsPanel
                ai={doc.ai}
                onAiFieldChange={(field, value) => update("ai", field, value)}
                onProfilesPersisted={persistAiProfiles}
              />
            )}

            {/* CREDENTIALS TAB */}
            {tab === 3 && (
              <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 6 }} >
                  <Typography variant="h6" gutterBottom>External APIs</Typography>
                   <Stack spacing={3}>
                    <SecretField fullWidth label="Google Maps API Key" value={doc.credentials?.google_maps_api_key} onChange={e => update("credentials", "google_maps_api_key", e.target.value)} />
                    <SecretField fullWidth label="Drone Connection String" value={doc.credentials?.drone_conn} onChange={e => update("credentials", "drone_conn", e.target.value)} />
                  </Stack>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }} >
                  <Typography variant="h6" gutterBottom>Administration</Typography>
                   <Stack spacing={3}>
                    <TextField variant="filled" fullWidth label="Admin Emails" value={doc.credentials?.admin_emails} onChange={e => update("credentials", "admin_emails", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Admin Domains" value={doc.credentials?.admin_domains} onChange={e => update("credentials", "admin_domains", e.target.value)} />
                  </Stack>
                </Grid>
              </Grid>
            )}

            {/* HARDWARE TAB */}
            {tab === 4 && (
              <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 6 }} >
                  <Typography variant="h6" gutterBottom>Drone</Typography>
                   <Stack spacing={3}>
                    <TextField variant="filled" fullWidth label="Battery Capacity (Wh)" type="number" value={doc.hardware?.battery_capacity_wh} onChange={e => update("hardware", "battery_capacity_wh", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Energy Reserve Fraction" type="number" inputProps={{ step: 0.1, min: 0, max: 1 }} value={doc.hardware?.energy_reserve_frac} onChange={e => update("hardware", "energy_reserve_frac", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Cruise Power (W)" type="number" value={doc.hardware?.cruise_power_w} onChange={e => update("hardware", "cruise_power_w", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Cruise Speed (mps)" type="number" value={doc.hardware?.cruise_speed_mps} onChange={e => update("hardware", "cruise_speed_mps", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Heartbeat Timeout" type="number" value={doc.hardware?.heartbeat_timeout} onChange={e => update("hardware", "heartbeat_timeout", Number(e.target.value))} />
                    <FormControlLabel control={<Switch checked={doc.hardware?.enforce_preflight_range} onChange={e => update("hardware", "enforce_preflight_range", e.target.checked)} />} label="Enforce Preflight Range" />
                  </Stack>
                </Grid>

              </Grid>
            )}

            {/* PREFLIGHT CHECK TAB */}
            {tab === 5 && (
              <Grid container spacing={4}>
                <Grid size={{ xs: 12, md: 3 }} >
                  <Typography variant="h6" gutterBottom>GPS & Navigation</Typography>
                   <Stack spacing={3}>
                    <TextField variant="filled" fullWidth label="HDOP Max" type="number" value={doc.preflight?.HDOP_MAX} onChange={e => update("preflight", "HDOP_MAX", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Satellites Min" type="number" value={doc.preflight?.SAT_MIN} onChange={e => update("preflight", "SAT_MIN", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Home Max Dist (m)" type="number" value={doc.preflight?.HOME_MAX_DIST} onChange={e => update("preflight", "HOME_MAX_DIST", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="GPS Fix Type Min" type="number" value={doc.preflight?.GPS_FIX_TYPE_MIN} onChange={e => update("preflight", "GPS_FIX_TYPE_MIN", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="EKF Threshold" type="number" value={doc.preflight?.EKF_THRESHOLD} onChange={e => update("preflight", "EKF_THRESHOLD", Number(e.target.value))} />
                    <FormControlLabel control={<Switch checked={doc.preflight?.COMPASS_HEALTH_REQUIRED} onChange={e => update("preflight", "COMPASS_HEALTH_REQUIRED", e.target.checked)} />} label="Compass Health Required" />
                  </Stack>
                </Grid>
                <Grid size={{ xs: 12, md: 3 }} >
                  <Typography variant="h6" gutterBottom>Battery & Heartbeat</Typography>
                   <Stack spacing={3}>
                    <TextField variant="filled" fullWidth label="Battery Min (V)" type="number" value={doc.preflight?.BATTERY_MIN_V} onChange={e => update("preflight", "BATTERY_MIN_V", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Battery Min %" type="number" value={doc.preflight?.BATTERY_MIN_PERCENT} onChange={e => update("preflight", "BATTERY_MIN_PERCENT", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Heartbeat Max Age" type="number" value={doc.preflight?.HEARTBEAT_MAX_AGE} onChange={e => update("preflight", "HEARTBEAT_MAX_AGE", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Msg Rate Min (Hz)" type="number" value={doc.preflight?.MSG_RATE_MIN_HZ} onChange={e => update("preflight", "MSG_RATE_MIN_HZ", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="RTL Min Alt (m)" type="number" value={doc.preflight?.RTL_MIN_ALT} onChange={e => update("preflight", "RTL_MIN_ALT", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Min Clearance (m)" type="number" value={doc.preflight?.MIN_CLEARANCE} onChange={e => update("preflight", "MIN_CLEARANCE", Number(e.target.value))} />
                  </Stack>
                </Grid>

                <Grid size={{ xs: 12, md: 3 }} >
                  <Typography variant="h6" gutterBottom>Altitude & Range</Typography>
                   <Stack spacing={3}>
                    <TextField variant="filled" fullWidth label="AGL Min (m)" type="number" value={doc.preflight?.AGL_MIN} onChange={e => update("preflight", "AGL_MIN", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="AGL Max (m)" type="number" value={doc.preflight?.AGL_MAX} onChange={e => update("preflight", "AGL_MAX", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Max Range (m)" type="number" value={doc.preflight?.MAX_RANGE_M} onChange={e => update("preflight", "MAX_RANGE_M", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Max Waypoints" type="number" value={doc.preflight?.MAX_WAYPOINTS} onChange={e => update("preflight", "MAX_WAYPOINTS", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="NFZ Buffer (m)" type="number" value={doc.preflight?.NFZ_BUFFER_M} onChange={e => update("preflight", "NFZ_BUFFER_M", Number(e.target.value))} />
                  </Stack>
                </Grid>
                <Grid size={{ xs: 12, md: 3 }} >
                  <Typography variant="h6" gutterBottom>Performance</Typography>
                  <Stack spacing={3}>
                    <TextField variant="filled" fullWidth label="A Lat Max" type="number" value={doc.preflight?.A_LAT_MAX} onChange={e => update("preflight", "A_LAT_MAX", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Bank Max (deg)" type="number" value={doc.preflight?.BANK_MAX_DEG} onChange={e => update("preflight", "BANK_MAX_DEG", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Turn Penalty (s)" type="number" value={doc.preflight?.TURN_PENALTY_S} onChange={e => update("preflight", "TURN_PENALTY_S", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="WP Radius (m)" type="number" value={doc.preflight?.WP_RADIUS_M} onChange={e => update("preflight", "WP_RADIUS_M", Number(e.target.value))} />
                  </Stack>
                </Grid>
              </Grid>
            )}

            {/* ALERTS TAB */}
            {tab === 6 && (
              <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h6" gutterBottom>Rules</Typography>
                  <Stack spacing={3}>
                    <FormControlLabel
                      control={<Switch checked={doc.alerts?.enabled} onChange={e => update("alerts", "enabled", e.target.checked)} />}
                      label="Enable Alert Engine"
                    />
                    <TextField variant="filled" fullWidth label="Check Interval (sec)" type="number" value={doc.alerts?.check_interval_sec} onChange={e => update("alerts", "check_interval_sec", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Dedupe Window (sec)" type="number" value={doc.alerts?.dedupe_window_sec} onChange={e => update("alerts", "dedupe_window_sec", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Operation Geofence ID" type="number" value={doc.alerts?.operation_geofence_id ?? ""} onChange={e => update("alerts", "operation_geofence_id", e.target.value ? Number(e.target.value) : null)} />
                    <TextField variant="filled" fullWidth label="Monitor Herd IDs (comma-separated)" value={doc.alerts?.monitor_herd_ids} onChange={e => update("alerts", "monitor_herd_ids", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Herd Isolation Threshold (m)" type="number" value={doc.alerts?.herd_isolation_threshold_m} onChange={e => update("alerts", "herd_isolation_threshold_m", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Low Battery Threshold (%)" type="number" value={doc.alerts?.low_battery_percent} onChange={e => update("alerts", "low_battery_percent", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Weak Link Threshold (%)" type="number" value={doc.alerts?.weak_link_percent} onChange={e => update("alerts", "weak_link_percent", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="High Wind Threshold (m/s)" type="number" value={doc.alerts?.high_wind_mps} onChange={e => update("alerts", "high_wind_mps", Number(e.target.value))} />
                  </Stack>
                </Grid>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h6" gutterBottom>Routing & Channels</Typography>
                  <Stack spacing={3}>
                    <FormControlLabel
                      control={<Switch checked={doc.alerts?.route_in_app} onChange={e => update("alerts", "route_in_app", e.target.checked)} />}
                      label="Route In-App"
                    />
                    <FormControlLabel
                      control={<Switch checked={doc.alerts?.route_email} onChange={e => update("alerts", "route_email", e.target.checked)} />}
                      label="Route Email"
                    />
                    <TextField variant="filled" fullWidth label="Email Recipients" value={doc.alerts?.email_recipients} onChange={e => update("alerts", "email_recipients", e.target.value)} />
                    <TextField variant="filled" fullWidth label="SMTP Host" value={doc.alerts?.smtp_host} onChange={e => update("alerts", "smtp_host", e.target.value)} />
                    <TextField variant="filled" fullWidth label="SMTP Port" type="number" value={doc.alerts?.smtp_port} onChange={e => update("alerts", "smtp_port", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="SMTP User" value={doc.alerts?.smtp_user} onChange={e => update("alerts", "smtp_user", e.target.value)} />
                    <SecretField fullWidth label="SMTP Password" placeholder={MASK} value={doc.alerts?.smtp_password} onChange={e => update("alerts", "smtp_password", e.target.value)} />
                    <TextField variant="filled" fullWidth label="SMTP From Address" value={doc.alerts?.smtp_from} onChange={e => update("alerts", "smtp_from", e.target.value)} />
                    <FormControlLabel
                      control={<Switch checked={doc.alerts?.smtp_use_tls} onChange={e => update("alerts", "smtp_use_tls", e.target.checked)} />}
                      label="SMTP TLS"
                    />
                    <FormControlLabel
                      control={<Switch checked={doc.alerts?.route_sms} onChange={e => update("alerts", "route_sms", e.target.checked)} />}
                      label="Route SMS"
                    />
                    <TextField variant="filled" fullWidth label="SMS Recipients" value={doc.alerts?.sms_recipients} onChange={e => update("alerts", "sms_recipients", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Twilio Account SID" value={doc.alerts?.twilio_account_sid} onChange={e => update("alerts", "twilio_account_sid", e.target.value)} />
                    <SecretField fullWidth label="Twilio Auth Token" placeholder={MASK} value={doc.alerts?.twilio_auth_token} onChange={e => update("alerts", "twilio_auth_token", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Twilio From Number" value={doc.alerts?.twilio_from_number} onChange={e => update("alerts", "twilio_from_number", e.target.value)} />
                  </Stack>
                </Grid>
              </Grid>
            )}

            {/* RASPBERRY TAB */}
            {tab === 7 && (
                <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 6 }} >
                  <Typography variant="h6" gutterBottom>Raspberry Pi Connection</Typography>
                   <Stack spacing={3}>
                    <SecretField fullWidth label="IP Address" value={doc.raspberry?.raspberry_ip} onChange={e => update("raspberry", "raspberry_ip", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Hostname" value={doc.raspberry?.raspberry_host} onChange={e => update("raspberry", "raspberry_host", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Username" value={doc.raspberry?.raspberry_user} onChange={e => update("raspberry", "raspberry_user", e.target.value)} />
                    <SecretField fullWidth label="Password" placeholder={MASK} value={doc.raspberry?.raspberry_password} onChange={e => update("raspberry", "raspberry_password", e.target.value)} />
                    <SecretField fullWidth label="Streaming Script Path" value={doc.raspberry?.raspberry_streaming_script_path} onChange={e => update("raspberry", "raspberry_streaming_script_path", e.target.value)} />

                      <ActionIconLabel variant="upload" title="Upload SSH Key">
                        <input type="file" hidden accept=".pem,.key,.pub" onChange={handleFileUpload("raspberry", "ssh_key_path")} />
                      </ActionIconLabel>
                      {doc.raspberry?.ssh_key_path && <Typography variant="caption" display="block" sx={{ mt: 1 }}>✓ SSH key uploaded</Typography>}

                  </Stack>
                </Grid>
                </Grid>
            )}


            {/* CAMERA TAB */}
            {tab === 8 && (
              <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h6" gutterBottom>Drone Camera Parameters</Typography>
                  <Stack spacing={3}>
                    <SecretField fullWidth label="Camera Source" value={doc.camera?.drone_video_source} onChange={e => update("camera", "drone_video_source", e.target.value)} />
                    <SecretField fullWidth label="Sim UDP Camera Source" value={doc.camera?.drone_video_source_gazebo} onChange={e => update("camera", "drone_video_source_gazebo", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Width" type="number" value={doc.camera?.drone_video_width} onChange={e => update("camera", "drone_video_width", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Height" type="number" value={doc.camera?.drone_video_height} onChange={e => update("camera", "drone_video_height", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="FPS" type="number" value={doc.camera?.drone_video_fps} onChange={e => update("camera", "drone_video_fps", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Timeout" type="number" value={doc.camera?.drone_video_timeout} onChange={e => update("camera", "drone_video_timeout", Number(e.target.value))} />
                    <TextField variant="filled" fullWidth label="Recording Save Path" value={doc.camera?.drone_video_save_path} onChange={e => update("camera", "drone_video_save_path", e.target.value)} />
                    <TextField variant="filled" fullWidth label="Fallback" value={doc.camera?.drone_video_fallback} onChange={e => update("camera", "drone_video_fallback", e.target.value)} />

                    <Stack direction="row" spacing={25}>
                      <FormControlLabel
                        control={<Switch checked={doc.camera?.drone_video_enabled} onChange={e => update("camera", "drone_video_enabled", e.target.checked)} />}
                        label="Enable Stream"
                      />
                      <FormControlLabel
                        control={<Switch checked={doc.camera?.drone_video_save_stream} onChange={e => update("camera", "drone_video_save_stream", e.target.checked)} />}
                        label="Save Stream"
                      />
                      <FormControlLabel
                        control={<Switch checked={doc.camera?.drone_video_use_gazebo} onChange={e => update("camera", "drone_video_use_gazebo", e.target.checked)} />}
                        label="Use sim transport video"
                      />
                    </Stack>
                  </Stack>
                </Grid>
              </Grid>
            )}

            {/* PHOTOGRAMMETRY TAB */}
            {tab === 9 && (
              <Grid container spacing={3}>
                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h6" gutterBottom>Storage & Sync</Typography>
                  <Stack spacing={3}>
                    <TextField
                      variant="filled"
                      fullWidth
                      label="Drone Sync Dir"
                      placeholder={DEFAULTS.photogrammetry.PHOTOGRAMMETRY_DRONE_SYNC_DIR}
                      value={doc.photogrammetry?.PHOTOGRAMMETRY_DRONE_SYNC_DIR}
                      onChange={e => update("photogrammetry", "PHOTOGRAMMETRY_DRONE_SYNC_DIR", e.target.value)}
                    />
                    <TextField
                      variant="filled"
                      fullWidth
                      label="Capture Staging Dir"
                      placeholder={DEFAULTS.photogrammetry.PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR}
                      value={doc.photogrammetry?.PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR}
                      onChange={e => update("photogrammetry", "PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR", e.target.value)}
                    />
                    <TextField
                      variant="filled"
                      fullWidth
                      label="Inputs Dir"
                      placeholder={DEFAULTS.photogrammetry.PHOTOGRAMMETRY_INPUTS_DIR}
                      value={doc.photogrammetry?.PHOTOGRAMMETRY_INPUTS_DIR}
                      onChange={e => update("photogrammetry", "PHOTOGRAMMETRY_INPUTS_DIR", e.target.value)}
                    />
                    <TextField
                      variant="filled"
                      fullWidth
                      label="Storage Dir"
                      placeholder={DEFAULTS.photogrammetry.PHOTOGRAMMETRY_STORAGE_DIR}
                      value={doc.photogrammetry?.PHOTOGRAMMETRY_STORAGE_DIR}
                      onChange={e => update("photogrammetry", "PHOTOGRAMMETRY_STORAGE_DIR", e.target.value)}
                    />
                    <TextField
                      variant="filled"
                      fullWidth
                      label="Storage Base URL"
                      placeholder={DEFAULTS.photogrammetry.PHOTOGRAMMETRY_STORAGE_BASE_URL}
                      value={doc.photogrammetry?.PHOTOGRAMMETRY_STORAGE_BASE_URL}
                      onChange={e => update("photogrammetry", "PHOTOGRAMMETRY_STORAGE_BASE_URL", e.target.value)}
                    />
                    <TextField
                      variant="filled"
                      fullWidth
                      label="3D Tiles Command"
                      placeholder="(none)"
                      value={doc.photogrammetry?.PHOTOGRAMMETRY_3DTILES_CMD}
                      onChange={e => update("photogrammetry", "PHOTOGRAMMETRY_3DTILES_CMD", e.target.value)}
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={doc.photogrammetry?.PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET}
                          onChange={e => update("photogrammetry", "PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET", e.target.checked)}
                        />
                      }
                      label="Allow Minimal Tileset (Dev)"
                    />
                  </Stack>
                </Grid>

                <Grid size={{ xs: 12, md: 6 }}>
                  <Typography variant="h6" gutterBottom>WebODM & Queue</Typography>
                  <Stack spacing={3}>
                    <TextField
                      variant="filled"
                      fullWidth
                      label="WebODM Base URL"
                      placeholder={DEFAULTS.photogrammetry.WEBODM_BASE_URL}
                      value={doc.photogrammetry?.WEBODM_BASE_URL}
                      onChange={e => update("photogrammetry", "WEBODM_BASE_URL", e.target.value)}
                    />
                    <SecretField
                      fullWidth
                      label="WebODM API Token"
                      placeholder="(none)"
                      value={doc.photogrammetry?.WEBODM_API_TOKEN}
                      onChange={e => update("photogrammetry", "WEBODM_API_TOKEN", e.target.value)}
                    />
                    <TextField
                      variant="filled"
                      fullWidth
                      type="number"
                      label="WebODM Project ID"
                      placeholder={String(DEFAULTS.photogrammetry.WEBODM_PROJECT_ID)}
                      value={doc.photogrammetry?.WEBODM_PROJECT_ID}
                      onChange={e => update("photogrammetry", "WEBODM_PROJECT_ID", Number(e.target.value))}
                    />
                    <FormControlLabel
                      control={
                        <Switch
                          checked={doc.photogrammetry?.WEBODM_MOCK_MODE}
                          onChange={e => update("photogrammetry", "WEBODM_MOCK_MODE", e.target.checked)}
                        />
                      }
                      label="WebODM Mock Mode"
                    />
                    <TextField
                      variant="filled"
                      fullWidth
                      label="Mapping Job Queue Backend"
                      placeholder={DEFAULTS.photogrammetry.MAPPING_JOB_QUEUE_BACKEND}
                      value={doc.photogrammetry?.MAPPING_JOB_QUEUE_BACKEND}
                      onChange={e => update("photogrammetry", "MAPPING_JOB_QUEUE_BACKEND", e.target.value)}
                    />
                    <TextField
                      variant="filled"
                      fullWidth
                      label="Celery Photogrammetry Queue"
                      placeholder={DEFAULTS.photogrammetry.CELERY_PHOTOGRAMMETRY_QUEUE}
                      value={doc.photogrammetry?.CELERY_PHOTOGRAMMETRY_QUEUE}
                      onChange={e => update("photogrammetry", "CELERY_PHOTOGRAMMETRY_QUEUE", e.target.value)}
                    />
                    <SecretField
                      fullWidth
                      label="Asset Signing Secret"
                      placeholder="(uses jwt_secret)"
                      value={doc.photogrammetry?.PHOTOGRAMMETRY_ASSET_SIGNING_SECRET}
                      onChange={e => update("photogrammetry", "PHOTOGRAMMETRY_ASSET_SIGNING_SECRET", e.target.value)}
                    />
                  </Stack>
                </Grid>
              </Grid>
            )}



            <Box sx={{ mt: 4, display: "flex", justifyContent: "flex-end", gap: 0.5 }}>
              <ActionIconButton
                variant="undo"
                title="Reset"
                disabled={loading || saving}
                onClick={fetchSettings}
              />
              <ActionIconButton
                variant="upgrade"
                title={saving ? "Saving…" : "Save All Changes"}
                color="primary"
                loading={saving}
                disabled={!dirty || saving || loading}
                onClick={saveSettings}
              />
            </Box>
          </Box>
        </Paper>
      </Container>
    </>
  );
}
