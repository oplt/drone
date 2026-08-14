export const ANIMAL_FARM_MAP_CONTAINER_STYLE = { width: "100%", height: "400px" };
export const ANIMAL_FARM_DEFAULT_CENTER = { lat: 50.8503, lng: 4.3517 };

export function getAnimalFarmApiBase(): string {
  const raw = import.meta.env.VITE_API_BASE_URL ?? "";
  return (raw || "http://localhost:8000").replace(/\/$/, "");
}

export function getAnimalFarmMapConfig() {
  return {
    apiKey: import.meta.env.VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY as string,
    mapId: (import.meta.env.VITE_GOOGLE_MAPS_MAP_ID as string) || "",
  };
}
