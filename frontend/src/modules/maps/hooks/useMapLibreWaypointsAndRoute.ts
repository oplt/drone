import { useEffect, useMemo } from "react";
import maplibregl from "maplibre-gl";
import { makeMarkerElement } from "../adapters/maplibre/maplibreMarkers";
import { syncMapLibreRoute } from "../adapters/maplibre/maplibreRoute";
import type { Waypoint } from "../adapters/maplibre/maplibreMapTypes";
import type { MapLibreMapRefs } from "./useMapLibreMapRefs";

type UseMapLibreWaypointsAndRouteArgs = {
  refs: MapLibreMapRefs;
  waypoints: Waypoint[];
  selectedWaypointIndex: number | null;
  onSelectWaypoint?: (index: number) => void;
};

export function useMapLibreWaypointsAndRoute({
  refs,
  waypoints,
  selectedWaypointIndex,
  onSelectWaypoint,
}: UseMapLibreWaypointsAndRouteArgs) {
  const routeCoordinates = useMemo(
    () => waypoints.map((point) => [point.lon, point.lat] as [number, number]),
    [waypoints],
  );

  useEffect(() => {
    const map = refs.mapRef.current;
    if (!map) return;

    refs.waypointMarkersRef.current.forEach((marker) => marker.remove());
    refs.waypointMarkersRef.current = [];

    waypoints.forEach((point, index) => {
      const selected = selectedWaypointIndex === index;
      const marker = new maplibregl.Marker({
        element: makeMarkerElement(
          String(index + 1),
          selected ? "#ff6d00" : "#1976d2",
        ),
      })
        .setLngLat([point.lon, point.lat])
        .addTo(map);
      marker.getElement().style.cursor = "pointer";
      marker.getElement().addEventListener("click", (event) => {
        event.stopPropagation();
        onSelectWaypoint?.(index);
      });
      refs.waypointMarkersRef.current.push(marker);
    });

    const updateRoute = () => {
      syncMapLibreRoute(map, routeCoordinates);
    };

    if (map.loaded()) {
      updateRoute();
    } else {
      map.once("load", updateRoute);
    }
  }, [refs, routeCoordinates, waypoints, selectedWaypointIndex, onSelectWaypoint]);
}
