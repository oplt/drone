import { Alert, Link, Snackbar } from "@mui/material";
import { useCallback, useMemo, useState, type ReactNode } from "react";
import { NoticeContext, type NoticeOptions, type NoticeSeverity } from "./NoticeContext";

type Notice = {
  message: string;
  severity: NoticeSeverity;
  autoHideDuration: number | null;
  auditHref?: string;
};

export function NoticeProvider({ children }: { children: ReactNode }) {
  const [notice, setNotice] = useState<Notice | null>(null);
  const notify = useCallback((message: string, severityOrOptions: NoticeSeverity | NoticeOptions = "info") => {
    const options = typeof severityOrOptions === "string"
      ? { severity: severityOrOptions }
      : severityOrOptions;
    setNotice({
      message,
      severity: options.severity ?? "info",
      autoHideDuration: options.autoHideDuration ?? 5000,
      auditHref: options.auditHref,
    });
  }, []);
  const value = useMemo(() => ({ notify }), [notify]);

  return (
    <NoticeContext.Provider value={value}>
      {children}
      <Snackbar
        open={notice !== null}
        autoHideDuration={notice?.autoHideDuration ?? null}
        onClose={() => setNotice(null)}
        anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
      >
        <Alert
          onClose={() => setNotice(null)}
          severity={notice?.severity ?? "info"}
          variant="filled"
          action={notice?.auditHref ? (
            <Link href={notice.auditHref} color="inherit" underline="always">
              Audit
            </Link>
          ) : undefined}
        >
          {notice?.message}
        </Alert>
      </Snackbar>
    </NoticeContext.Provider>
  );
}
