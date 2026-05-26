import { Navigate } from "react-router-dom";
import type { ReactNode } from "react";
import { PageLoader } from "../../shared/ui";
import { useSession } from "../../modules/session";

type ProtectedRouteProps = {
  children: ReactNode;
};

export function ProtectedRoute({ children }: ProtectedRouteProps) {
  const { status } = useSession();

  if (status === "checking") {
    return <PageLoader fullScreen />;
  }

  if (status !== "authed") {
    return <Navigate to="/signin" replace />;
  }

  return <>{children}</>;
}
