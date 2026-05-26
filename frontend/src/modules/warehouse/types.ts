export type WarehouseMapOut = {
  id: number;
  name: string;
  area_m2: number | null;
  created_at: string;
  polygon_local_m: [number, number][];
};

export type CreateWarehouseMapPayload = {
  name: string;
  width_m: number;
  length_m: number;
};
