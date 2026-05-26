import type { ReactNode } from "react";
import { GoogleMapsProvider } from "../../modules/maps/providers/googleMaps";
import { QueryProvider } from "./QueryProvider";

type AppProvidersProps = {
  children: ReactNode;
};

export function AppProviders({ children }: AppProvidersProps) {
  return (
    <QueryProvider>
      <GoogleMapsProvider>{children}</GoogleMapsProvider>
    </QueryProvider>
  );
}
