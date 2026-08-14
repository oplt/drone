export type TelemetryWebSocketOptions = {
  enabled?: boolean;
  onTelemetry?: (data: TelemetrySnapshot) => void;
  onMessage?: (message: TelemetrySocketPayload) => void;
};

export type TelemetryObject = Record<string, unknown>;

export type TelemetrySnapshot = TelemetryObject & {
  battery?: TelemetryObject;
  gps?: TelemetryObject;
  link?: TelemetryObject;
  position?: TelemetryObject;
  status?: TelemetryObject;
  wind?: TelemetryObject;
};

export type TelemetrySocketPayload = TelemetrySnapshot | string | null;

export type TelemetrySubscriber = {
  onState: (state: SharedTelemetryState) => void;
  onTelemetry?: (data: TelemetrySnapshot) => void;
  onMessage?: (message: TelemetrySocketPayload) => void;
};

export type SharedTelemetryState = {
  telemetry: TelemetrySnapshot | null;
  isConnected: boolean;
  error: string | null;
  reconnectAttempt: number;
  /** Epoch ms of last telemetry packet (not pings/logs). */
  lastPacketAt: number | null;
};
