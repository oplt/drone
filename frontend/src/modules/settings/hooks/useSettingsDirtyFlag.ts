import { useCallback, useEffect, useState } from "react";

export function useSettingsDirtyFlag() {
  const [dirty, setDirty] = useState(false);

  const markDirty = useCallback(() => setDirty(true), []);
  const markClean = useCallback(() => setDirty(false), []);

  useEffect(() => {
    if (!dirty) return;
    const onBeforeUnload = (event: BeforeUnloadEvent) => {
      event.preventDefault();
      event.returnValue = "";
    };
    window.addEventListener("beforeunload", onBeforeUnload);
    return () => window.removeEventListener("beforeunload", onBeforeUnload);
  }, [dirty]);

  return { dirty, markDirty, markClean };
}
