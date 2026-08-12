import type { ReactNode } from "react";
import { GoogleMapsProvider } from "../../modules/maps/providers/googleMaps";

export type MapProvidersProps = {
  children: ReactNode;
};

export function MapProviders({ children }: MapProvidersProps) {
  return <GoogleMapsProvider>{children}</GoogleMapsProvider>;
}

export default MapProviders;
