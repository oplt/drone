import React from "react";
import { Navigate } from "react-router-dom";
import PageLoader from "./components/shared/PageLoader";
import { getToken, verifySession } from "./auth";

export function ProtectedRoute({ children }: { children: React.ReactNode }) {
  const token = getToken();
  const [status, setStatus] = React.useState<"checking" | "authed" | "guest">(
    token ? "checking" : "guest",
  );

  React.useEffect(() => {
    let cancelled = false;
    if (!token) {
      setStatus("guest");
      return;
    }

    (async () => {
      const ok = await verifySession();
      if (cancelled) return;
      setStatus(ok ? "authed" : "guest");
    })();

    return () => {
      cancelled = true;
    };
  }, [token]);

  if (status === "checking") return <PageLoader fullScreen />;
  if (status !== "authed") return <Navigate to="/signin" replace />;
  return <>{children}</>;
}
