import type { TelemetrySnapshot, TelemetrySocketPayload } from "./telemetryStreamTypes";

export function isTelemetryRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value && typeof value === "object" && !Array.isArray(value));
}

export async function parseTelemetryMessage(data: unknown): Promise<TelemetrySocketPayload> {
  try {
    const parsed =
      typeof data === "string"
        ? JSON.parse(data)
        : data instanceof Blob
          ? JSON.parse(await data.text())
          : data instanceof ArrayBuffer
            ? JSON.parse(new TextDecoder("utf-8").decode(data))
            : null;
    if (typeof parsed === "string" || isTelemetryRecord(parsed)) return parsed;
    return null;
  } catch {
    if (typeof data === "string") return data;
    return null;
  }
}

export function telemetryFromMessage(msg: TelemetrySocketPayload): TelemetrySnapshot | null {
  if (!isTelemetryRecord(msg)) return null;
  if (msg.type === "telemetry") {
    if (msg.protocol === "v1" && isTelemetryRecord(msg.envelope)) {
      const payload = (msg.envelope as Record<string, unknown>).payload;
      if (isTelemetryRecord(payload)) {
        const position = isTelemetryRecord(payload.position) ? payload.position : {};
        const attitude = isTelemetryRecord(payload.attitude) ? payload.attitude : {};
        const battery = isTelemetryRecord(payload.battery) ? payload.battery : {};
        const gps = isTelemetryRecord(payload.gps) ? payload.gps : {};
        const link = isTelemetryRecord(payload.link) ? payload.link : {};
        const wind = isTelemetryRecord(payload.wind) ? payload.wind : {};
        const motion = isTelemetryRecord(payload.motion) ? payload.motion : {};
        return {
          position: {
            lat: position.lat ?? 0,
            lon: position.lon ?? 0,
            alt: position.alt_m ?? 0,
            relative_alt: position.relative_alt_m ?? 0,
          },
          attitude: {
            roll: attitude.roll_rad ?? 0,
            pitch: attitude.pitch_rad ?? 0,
            yaw: attitude.yaw_rad ?? 0,
          },
          battery: {
            remaining: battery.remaining_pct ?? 0,
            voltage: battery.voltage_v ?? 0,
          },
          gps,
          link,
          wind,
          status: {
            groundspeed: motion.groundspeed_mps ?? 0,
            heading: motion.heading_deg ?? 0,
          },
          mode: payload.flight_mode,
          armed: payload.armed,
        } as TelemetrySnapshot;
      }
    }
    return isTelemetryRecord(msg.data) ? (msg.data as TelemetrySnapshot) : null;
  }
  if (msg.type) {
    return null;
  }
  return msg as TelemetrySnapshot;
}
