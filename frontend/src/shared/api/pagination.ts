export type PageResponse<T> = {
  items: T[];
  next_cursor: string | null;
  total?: number | null;
};

/** Accept legacy array fixtures while every production list endpoint uses PageResponse. */
export function unwrapPage<T>(payload: T[] | PageResponse<T>): T[] {
  return Array.isArray(payload) ? payload : payload.items;
}
