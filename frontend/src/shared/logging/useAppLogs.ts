import { useEffect, useState } from "react";
import { getAppLogs, subscribeAppLogs, type AppLogEvent } from "./appLog";

export function useAppLogs() {
  const [logs, setLogs] = useState<AppLogEvent[]>(() => getAppLogs());

  useEffect(() => subscribeAppLogs(setLogs), []);

  return logs;
}
