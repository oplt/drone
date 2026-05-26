export type Herd = {
  id: number;
  name: string;
  pasture_geofence_id?: number | null;
};

export type HerdLatestPos = {
  animal_id: number;
  collar_id: string;
  animal_name?: string | null;
  species: string;
  lat: number;
  lon: number;
  alt?: number | null;
  created_at: string;
};

export type HerdAlert = {
  type: string;
  severity: "low" | "medium" | "high";
  animal_id: number;
  collar_id: string;
  lat: number;
  lon: number;
  message: string;
  distance_to_nearest_m?: number;
};

export type LivestockTaskType = "census" | "herd_sweep" | "search_locate";
