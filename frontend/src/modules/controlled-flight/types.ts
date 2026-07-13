export type ManualFlightCommand =
  | "forward"
  | "backward"
  | "left"
  | "right"
  | "yaw_left"
  | "yaw_right"
  | "up"
  | "down"
  | "hold"
  | "takeoff"
  | "land";

export type ManualCommandPhase = "start" | "hold" | "stop";

export type ControlledPreflightCheck = {
  id: string;
  label: string;
  ok: boolean;
  detail: string;
};

export type ControlledPreflightResult = {
  ranAt: string;
  passed: boolean;
  checks: ControlledPreflightCheck[];
};

export type ManualControlButtonConfig = {
  id: string;
  label: string;
  hint: string;
  command: ManualFlightCommand;
};

export const MANUAL_KEY_BINDINGS: Record<string, ManualFlightCommand> = {
  w: "forward",
  arrowup: "forward",
  s: "backward",
  arrowdown: "backward",
  a: "left",
  arrowleft: "left",
  d: "right",
  arrowright: "right",
  q: "yaw_left",
  e: "yaw_right",
  r: "up",
  f: "down",
  " ": "hold",
  t: "takeoff",
  l: "land",
};

export const MANUAL_CONTROL_BUTTONS: ManualControlButtonConfig[] = [
  { id: "btn-takeoff", label: "Takeoff", hint: "T · confirm", command: "takeoff" },
  { id: "btn-up", label: "Ascend", hint: "R", command: "up" },
  { id: "btn-forward", label: "Forward", hint: "W / ↑", command: "forward" },
  { id: "btn-yaw-left", label: "Yaw Left", hint: "Q", command: "yaw_left" },
  { id: "btn-left", label: "Left", hint: "A / ←", command: "left" },
  { id: "btn-hold", label: "Hold", hint: "Space", command: "hold" },
  { id: "btn-right", label: "Right", hint: "D / →", command: "right" },
  { id: "btn-yaw-right", label: "Yaw Right", hint: "E", command: "yaw_right" },
  { id: "btn-backward", label: "Backward", hint: "S / ↓", command: "backward" },
  { id: "btn-down", label: "Descend", hint: "F", command: "down" },
  { id: "btn-land", label: "Land", hint: "L · confirm", command: "land" },
];

export const MANUAL_CONTROL_REPEAT_MS = 180;
