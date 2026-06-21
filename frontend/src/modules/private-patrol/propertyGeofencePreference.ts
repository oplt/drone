const PROPERTY_PATROL_FIELD_ID_KEY = "property_patrol_active_field_id";

export function readPropertyPatrolFieldId(): number | null {
  if (typeof window === "undefined") return null;
  const raw = window.localStorage.getItem(PROPERTY_PATROL_FIELD_ID_KEY);
  if (!raw) return null;
  const id = Number(raw);
  return Number.isFinite(id) && id > 0 ? id : null;
}

export function writePropertyPatrolFieldId(fieldId: number | null): void {
  if (typeof window === "undefined") return;
  if (fieldId == null) {
    window.localStorage.removeItem(PROPERTY_PATROL_FIELD_ID_KEY);
    return;
  }
  window.localStorage.setItem(PROPERTY_PATROL_FIELD_ID_KEY, String(fieldId));
}
