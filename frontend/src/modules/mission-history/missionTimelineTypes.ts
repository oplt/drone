export type TimelineEntry =
  | { kind: "transition"; ts: number; data: Record<string, unknown> }
  | { kind: "command"; ts: number; data: Record<string, unknown> }
  | { kind: "event"; ts: number; data: Record<string, unknown> };
