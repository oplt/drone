import { useEffect } from "react";
import maplibregl from "maplibre-gl";
import { ringLatLngBounds } from "../../fields";
import type {
  LatLng,
  LonLat,
  Waypoint,
} from "../adapters/maplibre/maplibreMapTypes";
import type { MapLibreMapRefs } from "./useMapLibreMapRefs";

type UseMapLibreCameraArgs = {
  refs: MapLibreMapRefs;
  center: LatLng;
  zoom: number;
  focusRing: LonLat[] | null;
  focusRequestToken?: number;
  followEnabled: boolean;
  droneCenter: LatLng | null;
  selectedWaypointIndex: number | null;
  waypoints: Waypoint[];
};

export function useMapLibreCamera({
  refs,
  center,
  zoom,
  focusRing,
  focusRequestToken,
  followEnabled,
  droneCenter,
  selectedWaypointIndex,
  waypoints,
}: UseMapLibreCameraArgs) {
  useEffect(() => {
    refs.mapRef.current?.jumpTo({ center: [center.lng, center.lat], zoom });
  }, [refs, center, zoom]);

  useEffect(() => {
    const map = refs.mapRef.current;
    if (!map || focusRequestToken == null) return;
    const bounds = focusRing ? ringLatLngBounds(focusRing) : null;
    if (!bounds) return;
    const fit = new maplibregl.LngLatBounds(
      [bounds.west, bounds.south],
      [bounds.east, bounds.north],
    );
    map.fitBounds(fit, { padding: 40, duration: 500 });
  }, [refs, focusRing, focusRequestToken]);

  useEffect(() => {
    if (!followEnabled || !droneCenter || !refs.mapRef.current) return;
    refs.mapRef.current.easeTo({
      center: [droneCenter.lng, droneCenter.lat],
      duration: 400,
    });
  }, [refs, droneCenter, followEnabled]);

  useEffect(() => {
    if (selectedWaypointIndex == null || !refs.mapRef.current) return;
    const wp = waypoints[selectedWaypointIndex];
    if (!wp) return;
    refs.mapRef.current.easeTo({
      center: [wp.lon, wp.lat],
      duration: 400,
    });
  }, [refs, selectedWaypointIndex, waypoints]);
}
