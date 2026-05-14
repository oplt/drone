import React from "react";
import { Navigate } from "react-router-dom";
import PageLoader from "./components/shared/PageLoader";
import { verifySession } from "./auth";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const [status, setStatus] = React.useState<"checking" | "authed" | "guest">("checking");

  React.useEffect(() => {
    let cancelled = false;

    (async () => {
      const ok = await verifySession();
      if (cancelled) return;
      setStatus(ok ? "authed" : "guest");
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  if (status === "checking") return <PageLoader fullScreen />;
  if (status !== "authed") return <Navigate to="/signin" replace />;
  return <>{children}</>;
}
