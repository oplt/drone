import { createContext } from "react";
import type { ReactNode } from "react";
import { useJsApiLoader } from "@react-google-maps/api";

const libraries: ("geometry" | "marker")[] = ["marker", "geometry"];

type GoogleMapsContextValue = {
  isLoaded: boolean;
  loadError?: Error;
};

export const GoogleMapsContext = createContext<GoogleMapsContextValue>({
  isLoaded: false,
  loadError: undefined,
});

export function GoogleMapsProvider({ children }: { children: ReactNode }) {
  const googleMapsApiKey =
    import.meta.env.VITE_GOOGLE_MAPS_JAVASCRIPT_API_KEY ||
    import.meta.env.VITE_GOOGLE_MAPS_API_KEY ||
    "";

  const { isLoaded, loadError } = useJsApiLoader({
    id: "google-maps-script",
    googleMapsApiKey,
    libraries
  });

  if (loadError) {
    console.error(loadError);
  }

  return (
    <GoogleMapsContext.Provider value={{ isLoaded, loadError }}>
      {children}
    </GoogleMapsContext.Provider>
  );
}
