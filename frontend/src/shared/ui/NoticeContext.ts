import { createContext, useContext } from "react";

export type NoticeSeverity = "success" | "info" | "warning" | "error";
export type NoticeOptions = {
  severity?: NoticeSeverity;
  autoHideDuration?: number | null;
  auditHref?: string;
};
export type NoticeContextValue = {
  notify: (message: string, severityOrOptions?: NoticeSeverity | NoticeOptions) => void;
};

export const NoticeContext = createContext<NoticeContextValue | null>(null);

export function useNotice(): NoticeContextValue {
  const value = useContext(NoticeContext);
  if (!value) throw new Error("useNotice must be used inside NoticeProvider.");
  return value;
}
