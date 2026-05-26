import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";
import { PageLoader } from "../../shared/ui";
import { useSession } from "../../modules/session";

type GuestRouteProps = {
  children: ReactNode;
};

/** Redirect authenticated users away from sign-in / marketing entry routes. */
export function GuestRoute({ children }: GuestRouteProps) {
  const { status } = useSession();

  if (status === "checking") {
    return <PageLoader fullScreen />;
  }

  if (status === "authed") {
    return <Navigate to="/dashboard" replace />;
  }

  return <>{children}</>;
}
