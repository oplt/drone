import type {
  LlmProfile,
  LlmProviderId,
  LlmProviderSettings,
  LlmTaskName,
} from "./api/settingsApi";

export type TelemetrySettings = {
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

export type AISettings = {
  llm_provider: string;
  llm_api_base: string;
  llm_model: string;
  llm_api_key?: string;
  active_provider: LlmProviderId;
  system_prompt: string;
  providers: Record<LlmProviderId, LlmProviderSettings>;
  task_defaults: Record<LlmTaskName, { provider: LlmProviderId | ""; model: string }>;
  profiles: LlmProfile[];
  default_profile_id: string;
  task_overrides: Partial<Record<LlmTaskName, string>>;
};

export type CredentialsSettings = {
  google_maps_api_key: string;
  drone_conn: string;
  admin_emails: string;
  admin_domains: string;
};

export type HardwareSettings = {
  battery_capacity_wh: number;
  energy_reserve_frac: number;
  cruise_speed_mps: number;
  cruise_power_w: number;
  heartbeat_timeout: number;
  enforce_preflight_range: boolean;
};

export type PreflightSettings = {
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

export type RaspberrySettings = {
  raspberry_ip: string;
  raspberry_user: string;
  raspberry_host: string;
  raspberry_password?: string;
  ssh_key_path: string;
  raspberry_streaming_script_path: string;
};

export type CameraSettings = {
  drone_video_source: string;
  drone_video_source_gazebo: string;
  drone_video_use_gazebo: boolean;
  drone_video_width: number;
  drone_video_height: number;
  drone_video_fps: number;
  drone_video_timeout: number;
  drone_video_save_path: string;
  drone_video_fallback: string;
  drone_video_enabled: boolean;
  drone_video_save_stream: boolean;
};

export type PhotogrammetrySettings = {
  PHOTOGRAMMETRY_DRONE_SYNC_DIR: string;
  PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR: string;
  PHOTOGRAMMETRY_INPUTS_DIR: string;
  PHOTOGRAMMETRY_STORAGE_DIR: string;
  PHOTOGRAMMETRY_STORAGE_BASE_URL: string;
  PHOTOGRAMMETRY_3DTILES_CMD: string;
  PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET: boolean;
  WEBODM_BASE_URL: string;
  WEBODM_API_TOKEN?: string;
  WEBODM_PROJECT_ID: number;
  WEBODM_MOCK_MODE: boolean;
  MAPPING_JOB_QUEUE_BACKEND: string;
  CELERY_PHOTOGRAMMETRY_QUEUE: string;
  PHOTOGRAMMETRY_ASSET_SIGNING_SECRET?: string;
};

export type AlertSettings = {
  enabled: boolean;
  check_interval_sec: number;
  dedupe_window_sec: number;
  operation_geofence_id?: number | null;
  monitor_herd_ids: string;
  herd_isolation_threshold_m: number;
  low_battery_percent: number;
  weak_link_percent: number;
  high_wind_mps: number;
  route_in_app: boolean;
  route_email: boolean;
  route_sms: boolean;
  email_recipients: string;
  sms_recipients: string;
  smtp_host: string;
  smtp_port: number;
  smtp_user: string;
  smtp_password?: string;
  smtp_from: string;
  smtp_use_tls: boolean;
  twilio_account_sid: string;
  twilio_auth_token?: string;
  twilio_from_number: string;
};

export type SettingsDoc = {
  telemetry: TelemetrySettings;
  ai: AISettings;
  credentials: CredentialsSettings;
  hardware: HardwareSettings;
  preflight: PreflightSettings;
  raspberry: RaspberrySettings;
  camera: CameraSettings;
  photogrammetry: PhotogrammetrySettings;
  alerts: AlertSettings;
  updated_at?: string;
};

export type SettingsSection = Exclude<keyof SettingsDoc, "updated_at">;

export type UserResponse = {
  id: string;
  email: string;
  full_name: string | null;
  created_at?: string;
};

export type UserUpdate = {
  full_name?: string;
};
