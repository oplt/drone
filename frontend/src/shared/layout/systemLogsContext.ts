import {
  createContext,
  useContext,
  type Dispatch,
  type SetStateAction,
} from "react";

export type SystemLogsContextValue = {
  open: boolean;
  setOpen: Dispatch<SetStateAction<boolean>>;
  criticalCount: number;
};

export const SystemLogsContext = createContext<SystemLogsContextValue | null>(null);

export function useSystemLogs(): SystemLogsContextValue {
  const value = useContext(SystemLogsContext);
  if (!value) {
    throw new Error("useSystemLogs must be used inside SystemLogsProvider.");
  }
  return value;
}
