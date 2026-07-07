import { useEffect } from "react";

export type GooglePointMarker = {
  point: {
    lat: number;
    lon: number;
  };
  title: string;
  color: string;
};

type AdvancedMarkerCtor = new (opts: unknown) => unknown;

function clearGoogleMarkers(markers: React.MutableRefObject<unknown[]>) {
  markers.current.forEach((marker) => {
    try {
      if (marker && typeof marker === "object") {
        if ("map" in marker) {
          (marker as { map: null }).map = null;
        } else if (
          "setMap" in marker &&
          typeof (marker as { setMap: (value: null) => void }).setMap === "function"
        ) {
          (marker as { setMap: (value: null) => void }).setMap(null);
        }
      }
    } catch {
      // Google marker cleanup can throw after map teardown; ignore stale marker cleanup.
    }
  });
  markers.current = [];
}

function createMarkerContent(color: string) {
  const content = document.createElement("div");
  content.style.width = "12px";
  content.style.height = "12px";
  content.style.borderRadius = "50%";
  content.style.background = color;
  content.style.border = "2px solid #ffffff";
  content.style.boxShadow = "0 2px 6px rgba(0,0,0,0.2)";
  return content;
}

export function useGooglePointMarkers({
  enabled,
  isLoaded,
  mapReady,
  mapRef,
  markersRef,
  markers,
}: {
  enabled: boolean;
  isLoaded: boolean;
  mapReady: boolean;
  mapRef: React.MutableRefObject<google.maps.Map | null>;
  markersRef: React.MutableRefObject<unknown[]>;
  markers: GooglePointMarker[];
}) {
  useEffect(() => {
    if (!isLoaded || !mapReady) return;
    if (!mapRef.current) return;
    const markerLib = (
      google.maps as unknown as {
        marker?: { AdvancedMarkerElement?: AdvancedMarkerCtor };
      }
    )?.marker;
    const AdvancedMarkerElement = markerLib?.AdvancedMarkerElement;
    if (!AdvancedMarkerElement) {
      return;
    }

    clearGoogleMarkers(markersRef);

    if (!enabled || markers.length === 0) return;

    markers.forEach(({ point, title, color }) => {
      const marker = new AdvancedMarkerElement({
        map: mapRef.current,
        position: { lat: point.lat, lng: point.lon },
        content: createMarkerContent(color),
        title,
      });

      markersRef.current.push(marker);
    });

    return () => clearGoogleMarkers(markersRef);
  }, [enabled, isLoaded, mapReady, mapRef, markers, markersRef]);
}
