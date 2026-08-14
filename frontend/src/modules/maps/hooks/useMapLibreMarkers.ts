import { useEffect } from "react";
import maplibregl from "maplibre-gl";
import {
  makeDroneMarkerElement,
  makeMarkerElement,
} from "../adapters/maplibre/maplibreMarkers";
import type { LatLng } from "../adapters/maplibre/maplibreMapTypes";
import type { MapLibreMapRefs } from "./useMapLibreMapRefs";

type UseMapLibreMarkersArgs = {
  refs: MapLibreMapRefs;
  droneCenter: LatLng | null;
  userCenter: LatLng | null;
};

export function useMapLibreMarkers({
  refs,
  droneCenter,
  userCenter,
}: UseMapLibreMarkersArgs) {
  useEffect(() => {
    const map = refs.mapRef.current;
    if (!map) return;

    if (droneCenter) {
      if (!refs.droneMarkerRef.current) {
        refs.droneMarkerRef.current = new maplibregl.Marker({
          element: makeDroneMarkerElement(),
        })
          .setLngLat([droneCenter.lng, droneCenter.lat])
          .addTo(map);
      } else {
        refs.droneMarkerRef.current.setLngLat([droneCenter.lng, droneCenter.lat]);
      }
    } else if (refs.droneMarkerRef.current) {
      refs.droneMarkerRef.current.remove();
      refs.droneMarkerRef.current = null;
    }
  }, [refs, droneCenter]);

  useEffect(() => {
    const map = refs.mapRef.current;
    if (!map) return;

    if (userCenter) {
      if (!refs.userMarkerRef.current) {
        refs.userMarkerRef.current = new maplibregl.Marker({
          element: makeMarkerElement("U", "#2e7d32"),
        })
          .setLngLat([userCenter.lng, userCenter.lat])
          .addTo(map);
      } else {
        refs.userMarkerRef.current.setLngLat([userCenter.lng, userCenter.lat]);
      }
    } else if (refs.userMarkerRef.current) {
      refs.userMarkerRef.current.remove();
      refs.userMarkerRef.current = null;
    }
  }, [refs, userCenter]);
}
