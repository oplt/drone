from __future__ import annotations

import os
from typing import Any, Dict

from backend.config import RuntimeSettings as EnvSettings
from backend.db.repository.settings_repo import SettingsRepository

_env = EnvSettings()  # env defaults / bootstrap


def _env_string(value: Any) -> str:
    if isinstance(value, bool):
        return "1" if value else "0"
    return "" if value is None else str(value)


def _apply_runtime_to_process_env(runtime: EnvSettings) -> None:
    for key, value in runtime.model_dump().items():
        os.environ[key] = _env_string(value)


def _flatten_for_env(doc: Dict[str, Any]) -> Dict[str, Any]:
    """
    Convert SettingsDoc (nested) -> EnvSettings (flat) overlay.
    Only maps the fields that exist in your SettingsPage.tsx schema.
    """
    t = doc.get("telemetry", {}) or {}
    a = doc.get("ai", {}) or {}
    c = doc.get("credentials", {}) or {}
    h = doc.get("hardware", {}) or {}
    p = doc.get("preflight", {}) or {}
    r = doc.get("raspberry", {}) or {}
    cam = doc.get("camera", {}) or {}
    photo = doc.get("photogrammetry", {}) or {}
    al = doc.get("alerts", {}) or {}

    flat: Dict[str, Any] = {
        # Telemetry
        "mqtt_broker": t.get("mqtt_broker"),
        "mqtt_port": t.get("mqtt_port"),
        "mqtt_user": t.get("mqtt_user"),
        "mqtt_pass": t.get("mqtt_pass"),
        "mqtt_use_tls": t.get("mqtt_use_tls"),
        "mqtt_ca_certs": t.get("mqtt_ca_certs"),
        "opcua_endpoint": t.get("opcua_endpoint"),
        "opcua_security_policy": t.get("opcua_security_policy"),
        "opcua_cert_path": t.get("opcua_cert_path"),
        "opcua_key_path": t.get("opcua_key_path"),
        "telem_log_interval_sec": t.get("telem_log_interval_sec"),
        "telemetry_topic": t.get("telemetry_topic"),

        # AI
        "llm_provider": a.get("llm_provider"),
        "llm_api_base": a.get("llm_api_base"),
        "llm_model": a.get("llm_model"),
        "llm_api_key": a.get("llm_api_key"),

        # Credentials
        "google_maps_api_key": c.get("google_maps_api_key"),
        "drone_conn": c.get("drone_conn"),
        "admin_emails": c.get("admin_emails"),
        "admin_domains": c.get("admin_domains"),

        # Hardware
        "battery_capacity_wh": h.get("battery_capacity_wh"),
        "energy_reserve_frac": h.get("energy_reserve_frac"),
        "cruise_speed_mps": h.get("cruise_speed_mps"),
        "cruise_power_w": h.get("cruise_power_w"),
        "heartbeat_timeout": h.get("heartbeat_timeout"),
        "enforce_preflight_range": h.get("enforce_preflight_range"),

        # Alerts
        "alerts_enabled": al.get("enabled"),
        "alerts_check_interval_sec": al.get("check_interval_sec"),
        "alerts_dedupe_window_sec": al.get("dedupe_window_sec"),
        "alerts_operation_geofence_id": al.get("operation_geofence_id"),
        "alerts_monitor_herd_ids": al.get("monitor_herd_ids"),
        "alerts_herd_isolation_threshold_m": al.get("herd_isolation_threshold_m"),
        "alerts_low_battery_percent": al.get("low_battery_percent"),
        "alerts_weak_link_percent": al.get("weak_link_percent"),
        "alerts_high_wind_mps": al.get("high_wind_mps"),
        "alerts_route_in_app": al.get("route_in_app"),
        "alerts_route_email": al.get("route_email"),
        "alerts_route_sms": al.get("route_sms"),
        "alerts_email_recipients": al.get("email_recipients"),
        "alerts_sms_recipients": al.get("sms_recipients"),
        "alerts_smtp_host": al.get("smtp_host"),
        "alerts_smtp_port": al.get("smtp_port"),
        "alerts_smtp_user": al.get("smtp_user"),
        "alerts_smtp_password": al.get("smtp_password"),
        "alerts_smtp_from": al.get("smtp_from"),
        "alerts_smtp_use_tls": al.get("smtp_use_tls"),
        "alerts_twilio_account_sid": al.get("twilio_account_sid"),
        "alerts_twilio_auth_token": al.get("twilio_auth_token"),
        "alerts_twilio_from_number": al.get("twilio_from_number"),

        # Preflight
        "HDOP_MAX": p.get("HDOP_MAX"),
        "SAT_MIN": p.get("SAT_MIN"),
        "HOME_MAX_DIST": p.get("HOME_MAX_DIST"),
        "GPS_FIX_TYPE_MIN": p.get("GPS_FIX_TYPE_MIN"),
        "EKF_THRESHOLD": p.get("EKF_THRESHOLD"),
        "COMPASS_HEALTH_REQUIRED": p.get("COMPASS_HEALTH_REQUIRED"),
        "BATTERY_MIN_V": p.get("BATTERY_MIN_V"),
        "BATTERY_MIN_PERCENT": p.get("BATTERY_MIN_PERCENT"),
        "HEARTBEAT_MAX_AGE": p.get("HEARTBEAT_MAX_AGE"),
        "MSG_RATE_MIN_HZ": p.get("MSG_RATE_MIN_HZ"),
        "RTL_MIN_ALT": p.get("RTL_MIN_ALT"),
        "MIN_CLEARANCE": p.get("MIN_CLEARANCE"),
        "AGL_MIN": p.get("AGL_MIN"),
        "AGL_MAX": p.get("AGL_MAX"),
        "MAX_RANGE_M": p.get("MAX_RANGE_M"),
        "MAX_WAYPOINTS": p.get("MAX_WAYPOINTS"),
        "NFZ_BUFFER_M": p.get("NFZ_BUFFER_M"),
        "A_LAT_MAX": p.get("A_LAT_MAX"),
        "BANK_MAX_DEG": p.get("BANK_MAX_DEG"),
        "TURN_PENALTY_S": p.get("TURN_PENALTY_S"),
        "WP_RADIUS_M": p.get("WP_RADIUS_M"),

        # Raspberry
        "raspberry_ip": r.get("raspberry_ip"),
        "raspberry_user": r.get("raspberry_user"),
        "raspberry_host": r.get("raspberry_host"),
        "raspberry_password": r.get("raspberry_password"),
        "ssh_key_path": r.get("ssh_key_path"),
        "raspberry_streaming_script_path": r.get("raspberry_streaming_script_path"),

        # Camera
        "drone_video_source": cam.get("drone_video_source"),
        "drone_video_source_gazebo": cam.get("drone_video_source_gazebo"),
        "drone_video_use_gazebo": cam.get("drone_video_use_gazebo"),
        "drone_video_width": cam.get("drone_video_width"),
        "drone_video_height": cam.get("drone_video_height"),
        "drone_video_fps": cam.get("drone_video_fps"),
        "drone_video_timeout": cam.get("drone_video_timeout"),
        "drone_video_save_path": cam.get("drone_video_save_path"),
        "drone_video_fallback": cam.get("drone_video_fallback"),
        "drone_video_enabled": cam.get("drone_video_enabled"),
        "drone_video_save_stream": cam.get("drone_video_save_stream"),

        # Photogrammetry
        "PHOTOGRAMMETRY_DRONE_SYNC_DIR": photo.get("PHOTOGRAMMETRY_DRONE_SYNC_DIR"),
        "PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR": photo.get(
            "PHOTOGRAMMETRY_DRONE_CAPTURE_STAGING_DIR"
        ),
        "PHOTOGRAMMETRY_INPUTS_DIR": photo.get("PHOTOGRAMMETRY_INPUTS_DIR"),
        "PHOTOGRAMMETRY_STORAGE_DIR": photo.get("PHOTOGRAMMETRY_STORAGE_DIR"),
        "PHOTOGRAMMETRY_STORAGE_BASE_URL": photo.get("PHOTOGRAMMETRY_STORAGE_BASE_URL"),
        "PHOTOGRAMMETRY_3DTILES_CMD": photo.get("PHOTOGRAMMETRY_3DTILES_CMD"),
        "PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET": photo.get(
            "PHOTOGRAMMETRY_ALLOW_MINIMAL_TILESET"
        ),
        "WEBODM_BASE_URL": photo.get("WEBODM_BASE_URL"),
        "WEBODM_API_TOKEN": photo.get("WEBODM_API_TOKEN"),
        "WEBODM_PROJECT_ID": photo.get("WEBODM_PROJECT_ID"),
        "WEBODM_MOCK_MODE": photo.get("WEBODM_MOCK_MODE"),
        "MAPPING_JOB_QUEUE_BACKEND": photo.get("MAPPING_JOB_QUEUE_BACKEND"),
        "CELERY_PHOTOGRAMMETRY_QUEUE": photo.get("CELERY_PHOTOGRAMMETRY_QUEUE"),
        "PHOTOGRAMMETRY_ASSET_SIGNING_SECRET": photo.get(
            "PHOTOGRAMMETRY_ASSET_SIGNING_SECRET"
        ),
    }

    # drop None so env defaults remain if DB lacks a value
    return {k: v for k, v in flat.items() if v is not None}


async def get_runtime_settings(repo: SettingsRepository) -> EnvSettings:
    """
    Loads effective settings from DB (including decrypted secrets),
    flattens to EnvSettings, merges with env defaults, and updates backend.config.settings in-place.
    """
    effective_doc = await repo.get_effective_settings_doc()
    overlay = _flatten_for_env(effective_doc)

    merged = _env.model_dump()
    merged.update(overlay)

    runtime = EnvSettings.model_validate(merged)

    # Update shared singleton so existing imports see new values
    from backend import config as config_module
    for key, value in runtime.model_dump().items():
        setattr(config_module.settings, key, value)
    _apply_runtime_to_process_env(runtime)

    return runtime
