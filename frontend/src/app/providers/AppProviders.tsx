import type { ReactNode } from "react";
import { GoogleMapsProvider } from "../../modules/maps/providers/googleMaps";
import { NoticeProvider } from "../../shared/ui/NoticeProvider";
import { ConfirmProvider } from "../../shared/ui/ConfirmProvider";
import { QueryProvider } from "./QueryProvider";

type AppProvidersProps = {
  children: ReactNode;
};

export function AppProviders({ children }: AppProvidersProps) {
  return (
    <QueryProvider>
      <NoticeProvider>
        <ConfirmProvider>
          <GoogleMapsProvider>{children}</GoogleMapsProvider>
        </ConfirmProvider>
      </NoticeProvider>
    </QueryProvider>
  );
}
