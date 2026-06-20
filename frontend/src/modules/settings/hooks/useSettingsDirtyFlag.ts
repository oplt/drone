import { useCallback, useState } from "react";

export function useSettingsDirtyFlag() {
  const [dirty, setDirty] = useState(false);

  const markDirty = useCallback(() => setDirty(true), []);
  const markClean = useCallback(() => setDirty(false), []);

  return { dirty, markDirty, markClean };
}
