export type AppLogLevel = "debug" | "info" | "warn" | "error" | "critical";

export type AppLogSource =
  | "backend"
  | "frontend"
  | "drone"
  | "mavlink"
  | "telemetry"
  | "mission"
  | "video"
  | "analysis"
  | "model"
  | "upload"
  | "websocket"
  | "api";

export type AppLogEvent = {
  id: string;
  timestamp: string;
  level: AppLogLevel;
  source: AppLogSource;
  message: string;
  details?: Record<string, unknown>;
  request_id?: string;
  requestId?: string;
  mission_id?: string;
  missionId?: string;
  flight_id?: string;
  flightId?: string;
};

type LogSubscriber = (events: AppLogEvent[]) => void;

const MAX_EVENTS = 150;
const subscribers = new Set<LogSubscriber>();
let events: AppLogEvent[] = [];
const recentKeys = new Map<string, number>();

function nowIso() {
  return new Date().toISOString();
}

function createId() {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) {
    return crypto.randomUUID();
  }
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2)}`;
}

function normalizeLevel(level: AppLogLevel | "warning"): AppLogLevel {
  return level === "warning" ? "warn" : level;
}

function normalizeEvent(input: Omit<AppLogEvent, "id" | "timestamp"> & Partial<Pick<AppLogEvent, "id" | "timestamp">>): AppLogEvent {
  const level = normalizeLevel(input.level as AppLogLevel | "warning");
  return {
    ...input,
    level,
    id: input.id || createId(),
    timestamp: input.timestamp || nowIso(),
    requestId: input.requestId ?? input.request_id,
    missionId: input.missionId ?? input.mission_id,
    flightId: input.flightId ?? input.flight_id,
  };
}

function notify() {
  const snapshot = [...events];
  subscribers.forEach((subscriber) => subscriber(snapshot));
}

function shouldDropDuplicate(event: AppLogEvent) {
  const key = [
    event.level,
    event.source,
    event.message,
    event.requestId ?? event.request_id ?? "",
    event.flightId ?? event.flight_id ?? "",
  ].join("|");
  const now = Date.now();
  for (const [itemKey, seenAt] of recentKeys) {
    if (now - seenAt > 10_000) recentKeys.delete(itemKey);
  }
  const previous = recentKeys.get(key);
  recentKeys.set(key, now);
  return previous !== undefined && now - previous < 10_000;
}

function mirrorToConsole(event: AppLogEvent) {
  const payload = {
    source: event.source,
    requestId: event.requestId ?? event.request_id,
    missionId: event.missionId ?? event.mission_id,
    flightId: event.flightId ?? event.flight_id,
    details: event.details,
  };
  if (event.level === "critical" || event.level === "error") {
    console.error(`[${event.source}] ${event.message}`, payload);
  } else if (event.level === "warn") {
    console.warn(`[${event.source}] ${event.message}`, payload);
  } else if (event.level === "info") {
    console.info(`[${event.source}] ${event.message}`, payload);
  } else {
    console.debug(`[${event.source}] ${event.message}`, payload);
  }
}

export function emitAppLog(
  input: Omit<AppLogEvent, "id" | "timestamp"> & Partial<Pick<AppLogEvent, "id" | "timestamp">>,
  options: { mirrorToConsole?: boolean } = {},
) {
  const event = normalizeEvent(input);
  if (shouldDropDuplicate(event)) return event;
  events = [event, ...events].slice(0, MAX_EVENTS);
  if (options.mirrorToConsole !== false) {
    mirrorToConsole(event);
  }
  notify();
  return event;
}

export function subscribeAppLogs(subscriber: LogSubscriber) {
  subscribers.add(subscriber);
  subscriber([...events]);
  return () => {
    subscribers.delete(subscriber);
  };
}

export function getAppLogs() {
  return [...events];
}

export function clearAppLogsForTests() {
  events = [];
  recentKeys.clear();
  notify();
}

export const frontendLogger = {
  debug: (source: AppLogSource, message: string, details?: Record<string, unknown>) =>
    emitAppLog({ level: "debug", source, message, details }),
  info: (source: AppLogSource, message: string, details?: Record<string, unknown>) =>
    emitAppLog({ level: "info", source, message, details }),
  warn: (source: AppLogSource, message: string, details?: Record<string, unknown>) =>
    emitAppLog({ level: "warn", source, message, details }),
  error: (source: AppLogSource, message: string, details?: Record<string, unknown>) =>
    emitAppLog({ level: "error", source, message, details }),
  critical: (source: AppLogSource, message: string, details?: Record<string, unknown>) =>
    emitAppLog({ level: "critical", source, message, details }),
};
