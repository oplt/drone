import React, { useEffect, useMemo, useState } from "react";
import Header from "../../../components/dashboard/Header";

import {
  Alert,
  Box,
  Container,
  Divider,
  Grid,
  Paper,
  Tab,
  Tabs,
  TextField,
  Typography,
  FormControlLabel,
  Switch,
  Stack,
  CircularProgress,
} from "@mui/material";
import LoadingButton from "@mui/lab/LoadingButton";

type GeneralSettings = {
  llm_provider: string;
  llm_api_base: string;
  llm_model: string;

  mqtt_broker: string;
  mqtt_port: number;
  mqtt_user: string;

  telem_log_interval_sec: number;
  telemetry_topic: string;

  enforce_preflight_range: boolean;
  heartbeat_timeout: number;

  // secrets are masked server-side; send a new value only if user edits
  llm_api_key?: string; // secret
  mqtt_pass?: string; // secret
};

type PreflightSettings = {
  HDOP_MAX: number;
  SAT_MIN: number;
  HOME_MAX_DIST: number;

  HEARTBEAT_MAX_AGE: number;
  MSG_RATE_MIN_HZ: number;

  RTL_MIN_ALT: number;
  MIN_CLEARANCE: number;

  NFZ_BUFFER_M: number;
  COMPASS_HEALTH_REQUIRED: boolean;
};

type MissionSettings = {
  cruise_speed_mps: number;
  cruise_power_w: number;
  battery_capacity_wh: number;
  energy_reserve_frac: number;

  AGL_MIN: number;
  AGL_MAX: number;
  MAX_RANGE_M: number;
  MAX_WAYPOINTS: number;
};

type SettingsDoc = {
  general: GeneralSettings;
  preflight: PreflightSettings;
  mission: MissionSettings;
  updated_at?: string;
};

const MASK = "********";

const DEFAULTS: SettingsDoc = {
  general: {
    llm_provider: "ollama",
    llm_api_base: "",
    llm_model: "",
    mqtt_broker: "localhost",
    mqtt_port: 1883,
    mqtt_user: "",
    telem_log_interval_sec: 2.0,
    telemetry_topic: "ardupilot/telemetry",
    enforce_preflight_range: false,
    heartbeat_timeout: 5,
    llm_api_key: "",
    mqtt_pass: "",
  },
  preflight: {
    HDOP_MAX: 2.5,
    SAT_MIN: 6,
    HOME_MAX_DIST: 100,
    HEARTBEAT_MAX_AGE: 3.0,
    MSG_RATE_MIN_HZ: 5.0,
    RTL_MIN_ALT: 30,
    MIN_CLEARANCE: 5,
    NFZ_BUFFER_M: 50,
    COMPASS_HEALTH_REQUIRED: true,
  },
  mission: {
    cruise_speed_mps: 8,
    cruise_power_w: 180,
    battery_capacity_wh: 77,
    energy_reserve_frac: 0.2,
    AGL_MIN: 10,
    AGL_MAX: 120,
    MAX_RANGE_M: 5000,
    MAX_WAYPOINTS: 700,
  },
};

type TabKey = "general" | "preflight" | "mission";

function safeNum(v: unknown, fallback = 0): number {
  const n = typeof v === "number" ? v : Number(v);
  return Number.isFinite(n) ? n : fallback;
}

export default function SettingsPage() {
  const [tab, setTab] = useState<TabKey>("general");
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const [doc, setDoc] = useState<SettingsDoc>(DEFAULTS);
  const [lastLoaded, setLastLoaded] = useState<SettingsDoc>(DEFAULTS);

  const dirty = useMemo(
    () => JSON.stringify(doc) !== JSON.stringify(lastLoaded),
    [doc, lastLoaded]
  );

  async function fetchSettings() {
    setLoading(true);
    setErr(null);
    try {
      const res = await fetch("/api/settings", { credentials: "include" });
      if (!res.ok) throw new Error(`GET /api/settings failed: ${res.status}`);
      const data = (await res.json()) as Partial<SettingsDoc>;

      // merge for forward/backward compatibility
      const merged: SettingsDoc = {
        general: { ...DEFAULTS.general, ...(data.general || {}) },
        preflight: { ...DEFAULTS.preflight, ...(data.preflight || {}) },
        mission: { ...DEFAULTS.mission, ...(data.mission || {}) },
        updated_at: data.updated_at,
      };

      setDoc(merged);
      setLastLoaded(merged);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to load settings");
    } finally {
      setLoading(false);
    }
  }

  async function saveSettings() {
    setSaving(true);
    setErr(null);
    try {
      const res = await fetch("/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(doc),
      });

      if (!res.ok) {
        const t = await res.text().catch(() => "");
        throw new Error(`PUT /api/settings failed: ${res.status} ${t}`);
      }

      const saved = (await res.json()) as Partial<SettingsDoc>;
      const merged: SettingsDoc = {
        general: { ...DEFAULTS.general, ...(saved.general || {}) },
        preflight: { ...DEFAULTS.preflight, ...(saved.preflight || {}) },
        mission: { ...DEFAULTS.mission, ...(saved.mission || {}) },
        updated_at: saved.updated_at,
      };

      setDoc(merged);
      setLastLoaded(merged);
    } catch (e: any) {
      setErr(e?.message ?? "Failed to save settings");
    } finally {
      setSaving(false);
    }
  }

  useEffect(() => {
    void fetchSettings();
  }, []);

  function setGeneral<K extends keyof GeneralSettings>(k: K, v: GeneralSettings[K]) {
    setDoc((d) => ({ ...d, general: { ...d.general, [k]: v } }));
  }
  function setPreflight<K extends keyof PreflightSettings>(k: K, v: PreflightSettings[K]) {
    setDoc((d) => ({ ...d, preflight: { ...d.preflight, [k]: v } }));
  }
  function setMission<K extends keyof MissionSettings>(k: K, v: MissionSettings[K]) {
    setDoc((d) => ({ ...d, mission: { ...d.mission, [k]: v } }));
  }

  return (
    <>
      {/* Match HomePage: shared dashboard header */}
      <Header />

      <Container maxWidth="md" sx={{ py: 3 }}>
        <Stack spacing={2}>
          <Box>
            <Typography variant="h5" fontWeight={700}>
              Settings
            </Typography>
            <Typography variant="body2" color="text.secondary">
              Update system configuration and mission/preflight thresholds.
            </Typography>
          </Box>

          <Paper variant="outlined" sx={{ overflow: "hidden" }}>
            <Tabs
              value={tab}
              onChange={(_, v) => setTab(v)}
              variant="scrollable"
              scrollButtons="auto"
            >
              <Tab value="general" label="General" />
              <Tab value="preflight" label="Preflight Parameters" />
              <Tab value="mission" label="Mission Parameters" />
            </Tabs>

            <Divider />

            <Box sx={{ p: 2 }}>
              {err ? <Alert severity="error" sx={{ mb: 2 }}>{err}</Alert> : null}

              {loading ? (
                <Box sx={{ display: "flex", alignItems: "center", gap: 1, py: 2 }}>
                  <CircularProgress size={18} />
                  <Typography variant="body2" color="text.secondary">
                    Loading…
                  </Typography>
                </Box>
              ) : null}

              {!loading && tab === "general" ? (
                <Stack spacing={2}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    LLM
                  </Typography>

                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="LLM Provider"
                        value={doc.general.llm_provider ?? ""}
                        onChange={(e) => setGeneral("llm_provider", e.target.value)}
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="LLM Model"
                        value={doc.general.llm_model ?? ""}
                        onChange={(e) => setGeneral("llm_model", e.target.value)}
                      />
                    </Grid>

                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        label="LLM API Base"
                        value={doc.general.llm_api_base ?? ""}
                        onChange={(e) => setGeneral("llm_api_base", e.target.value)}
                        placeholder="http://localhost:11434"
                      />
                    </Grid>

                    <Grid item xs={12}>
                      <TextField
                        fullWidth
                        label="LLM API Key (secret)"
                        type="password"
                        helperText={`Stored encrypted. Leave as ${MASK} to keep current value.`}
                        value={doc.general.llm_api_key ?? ""}
                        onChange={(e) => setGeneral("llm_api_key", e.target.value)}
                        placeholder={MASK}
                        autoComplete="off"
                      />
                    </Grid>
                  </Grid>

                  <Divider />

                  <Typography variant="subtitle1" fontWeight={700}>
                    MQTT
                  </Typography>

                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="MQTT Broker"
                        value={doc.general.mqtt_broker ?? ""}
                        onChange={(e) => setGeneral("mqtt_broker", e.target.value)}
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="MQTT Port"
                        type="number"
                        inputProps={{ step: 1, min: 1 }}
                        value={safeNum(doc.general.mqtt_port, 1883)}
                        onChange={(e) => setGeneral("mqtt_port", safeNum(e.target.value, 1883))}
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="MQTT User"
                        value={doc.general.mqtt_user ?? ""}
                        onChange={(e) => setGeneral("mqtt_user", e.target.value)}
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="MQTT Password (secret)"
                        type="password"
                        helperText={`Stored encrypted. Leave as ${MASK} to keep current value.`}
                        value={doc.general.mqtt_pass ?? ""}
                        onChange={(e) => setGeneral("mqtt_pass", e.target.value)}
                        placeholder={MASK}
                        autoComplete="off"
                      />
                    </Grid>
                  </Grid>

                  <Divider />

                  <Typography variant="subtitle1" fontWeight={700}>
                    Telemetry & Safety
                  </Typography>

                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Telemetry Topic"
                        value={doc.general.telemetry_topic ?? ""}
                        onChange={(e) => setGeneral("telemetry_topic", e.target.value)}
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Telemetry Log Interval (sec)"
                        type="number"
                        inputProps={{ step: 0.1, min: 0 }}
                        value={safeNum(doc.general.telem_log_interval_sec, 2.0)}
                        onChange={(e) =>
                          setGeneral("telem_log_interval_sec", safeNum(e.target.value, 2.0))
                        }
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Heartbeat Timeout (sec)"
                        type="number"
                        inputProps={{ step: 0.5, min: 0 }}
                        value={safeNum(doc.general.heartbeat_timeout, 5)}
                        onChange={(e) =>
                          setGeneral("heartbeat_timeout", safeNum(e.target.value, 5))
                        }
                      />
                    </Grid>

                    <Grid item xs={12} md={6} sx={{ display: "flex", alignItems: "center" }}>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={!!doc.general.enforce_preflight_range}
                            onChange={(e) =>
                              setGeneral("enforce_preflight_range", e.target.checked)
                            }
                          />
                        }
                        label="Enforce Preflight Range"
                      />
                    </Grid>
                  </Grid>
                </Stack>
              ) : null}

              {!loading && tab === "preflight" ? (
                <Stack spacing={2}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    Preflight thresholds
                  </Typography>

                  <Grid container spacing={2}>
                    <Grid item xs={12} md={4}>
                      <TextField
                        fullWidth
                        label="HDOP_MAX"
                        type="number"
                        inputProps={{ step: 0.1, min: 0 }}
                        value={safeNum(doc.preflight.HDOP_MAX, 2.5)}
                        onChange={(e) => setPreflight("HDOP_MAX", safeNum(e.target.value, 2.5))}
                      />
                    </Grid>

                    <Grid item xs={12} md={4}>
                      <TextField
                        fullWidth
                        label="SAT_MIN"
                        type="number"
                        inputProps={{ step: 1, min: 0 }}
                        value={safeNum(doc.preflight.SAT_MIN, 6)}
                        onChange={(e) => setPreflight("SAT_MIN", safeNum(e.target.value, 6))}
                      />
                    </Grid>

                    <Grid item xs={12} md={4}>
                      <TextField
                        fullWidth
                        label="HOME_MAX_DIST (m)"
                        type="number"
                        inputProps={{ step: 1, min: 0 }}
                        value={safeNum(doc.preflight.HOME_MAX_DIST, 100)}
                        onChange={(e) =>
                          setPreflight("HOME_MAX_DIST", safeNum(e.target.value, 100))
                        }
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="HEARTBEAT_MAX_AGE (s)"
                        type="number"
                        inputProps={{ step: 0.1, min: 0 }}
                        value={safeNum(doc.preflight.HEARTBEAT_MAX_AGE, 3.0)}
                        onChange={(e) =>
                          setPreflight("HEARTBEAT_MAX_AGE", safeNum(e.target.value, 3.0))
                        }
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="MSG_RATE_MIN_HZ"
                        type="number"
                        inputProps={{ step: 0.1, min: 0 }}
                        value={safeNum(doc.preflight.MSG_RATE_MIN_HZ, 5.0)}
                        onChange={(e) =>
                          setPreflight("MSG_RATE_MIN_HZ", safeNum(e.target.value, 5.0))
                        }
                      />
                    </Grid>

                    <Grid item xs={12} md={4}>
                      <TextField
                        fullWidth
                        label="RTL_MIN_ALT (m)"
                        type="number"
                        inputProps={{ step: 1, min: 0 }}
                        value={safeNum(doc.preflight.RTL_MIN_ALT, 30)}
                        onChange={(e) => setPreflight("RTL_MIN_ALT", safeNum(e.target.value, 30))}
                      />
                    </Grid>

                    <Grid item xs={12} md={4}>
                      <TextField
                        fullWidth
                        label="MIN_CLEARANCE (m)"
                        type="number"
                        inputProps={{ step: 0.5, min: 0 }}
                        value={safeNum(doc.preflight.MIN_CLEARANCE, 5)}
                        onChange={(e) =>
                          setPreflight("MIN_CLEARANCE", safeNum(e.target.value, 5))
                        }
                      />
                    </Grid>

                    <Grid item xs={12} md={4}>
                      <TextField
                        fullWidth
                        label="NFZ_BUFFER_M (m)"
                        type="number"
                        inputProps={{ step: 1, min: 0 }}
                        value={safeNum(doc.preflight.NFZ_BUFFER_M, 50)}
                        onChange={(e) => setPreflight("NFZ_BUFFER_M", safeNum(e.target.value, 50))}
                      />
                    </Grid>

                    <Grid item xs={12}>
                      <FormControlLabel
                        control={
                          <Switch
                            checked={!!doc.preflight.COMPASS_HEALTH_REQUIRED}
                            onChange={(e) =>
                              setPreflight("COMPASS_HEALTH_REQUIRED", e.target.checked)
                            }
                          />
                        }
                        label="COMPASS_HEALTH_REQUIRED"
                      />
                    </Grid>
                  </Grid>
                </Stack>
              ) : null}

              {!loading && tab === "mission" ? (
                <Stack spacing={2}>
                  <Typography variant="subtitle1" fontWeight={700}>
                    Mission & energy model
                  </Typography>

                  <Grid container spacing={2}>
                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Cruise Speed (m/s)"
                        type="number"
                        inputProps={{ step: 0.1, min: 0 }}
                        value={safeNum(doc.mission.cruise_speed_mps, 8)}
                        onChange={(e) =>
                          setMission("cruise_speed_mps", safeNum(e.target.value, 8))
                        }
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Cruise Power (W)"
                        type="number"
                        inputProps={{ step: 1, min: 0 }}
                        value={safeNum(doc.mission.cruise_power_w, 180)}
                        onChange={(e) => setMission("cruise_power_w", safeNum(e.target.value, 180))}
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Battery Capacity (Wh)"
                        type="number"
                        inputProps={{ step: 1, min: 0 }}
                        value={safeNum(doc.mission.battery_capacity_wh, 77)}
                        onChange={(e) =>
                          setMission("battery_capacity_wh", safeNum(e.target.value, 77))
                        }
                      />
                    </Grid>

                    <Grid item xs={12} md={6}>
                      <TextField
                        fullWidth
                        label="Energy Reserve Fraction"
                        type="number"
                        inputProps={{ step: 0.01, min: 0, max: 1 }}
                        value={safeNum(doc.mission.energy_reserve_frac, 0.2)}
                        onChange={(e) =>
                          setMission("energy_reserve_frac", safeNum(e.target.value, 0.2))
                        }
                      />
                    </Grid>
                  </Grid>

                  <Divider />

                  <Typography variant="subtitle1" fontWeight={700}>
                    Mission limits
                  </Typography>

                  <Grid container spacing={2}>
                    <Grid item xs={12} md={3}>
                      <TextField
                        fullWidth
                        label="AGL_MIN (m)"
                        type="number"
                        inputProps={{ step: 1, min: 0 }}
                        value={safeNum(doc.mission.AGL_MIN, 10)}
                        onChange={(e) => setMission("AGL_MIN", safeNum(e.target.value, 10))}
                      />
                    </Grid>

                    <Grid item xs={12} md={3}>
                      <TextField
                        fullWidth
                        label="AGL_MAX (m)"
                        type="number"
                        inputProps={{ step: 1, min: 0 }}
                        value={safeNum(doc.mission.AGL_MAX, 120)}
                        onChange={(e) => setMission("AGL_MAX", safeNum(e.target.value, 120))}
                      />
                    </Grid>

                    <Grid item xs={12} md={3}>
                      <TextField
                        fullWidth
                        label="MAX_RANGE_M (m)"
                        type="number"
                        inputProps={{ step: 10, min: 0 }}
                        value={safeNum(doc.mission.MAX_RANGE_M, 5000)}
                        onChange={(e) => setMission("MAX_RANGE_M", safeNum(e.target.value, 5000))}
                      />
                    </Grid>

                    <Grid item xs={12} md={3}>
                      <TextField
                        fullWidth
                        label="MAX_WAYPOINTS"
                        type="number"
                        inputProps={{ step: 1, min: 0 }}
                        value={safeNum(doc.mission.MAX_WAYPOINTS, 700)}
                        onChange={(e) =>
                          setMission("MAX_WAYPOINTS", safeNum(e.target.value, 700))
                        }
                      />
                    </Grid>
                  </Grid>
                </Stack>
              ) : null}

              <Divider sx={{ my: 2 }} />

              <Box
                sx={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  gap: 2,
                  flexWrap: "wrap",
                }}
              >
                <Typography variant="body2" color="text.secondary">
                  {doc.updated_at ? `Last saved: ${doc.updated_at}` : "Not saved yet"}
                  {dirty ? (
                    <Typography component="span" sx={{ ml: 1, color: "warning.main" }}>
                      • Unsaved changes
                    </Typography>
                  ) : null}
                </Typography>

                <Stack direction="row" spacing={1}>
                  <LoadingButton
                    variant="outlined"
                    loading={loading}
                    disabled={saving}
                    onClick={() => void fetchSettings()}
                  >
                    Update
                  </LoadingButton>

                  <LoadingButton
                    variant="contained"
                    loading={saving}
                    disabled={loading || saving || !dirty}
                    onClick={() => void saveSettings()}
                  >
                    Save
                  </LoadingButton>
                </Stack>
              </Box>
            </Box>
          </Paper>
        </Stack>
      </Container>
    </>
  );
}