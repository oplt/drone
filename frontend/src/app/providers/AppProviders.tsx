import type { ReactNode } from "react";
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
        <ConfirmProvider>{children}</ConfirmProvider>
      </NoticeProvider>
    </QueryProvider>
  );
}
