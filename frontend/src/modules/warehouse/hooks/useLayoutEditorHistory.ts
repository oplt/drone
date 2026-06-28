import { useCallback, useState } from "react";

export function useLayoutEditorHistory<T>(initial: T) {
  const [past, setPast] = useState<T[]>([]);
  const [present, setPresent] = useState(initial);
  const [future, setFuture] = useState<T[]>([]);

  const replace = useCallback((next: T, record = true) => {
    setPresent((current) => {
      if (record) setPast((items) => [...items.slice(-49), current]);
      return next;
    });
    setFuture([]);
  }, []);

  const undo = useCallback(() => {
    setPast((items) => {
      const previous = items.at(-1);
      if (previous === undefined) return items;
      setPresent((current) => {
        setFuture((next) => [current, ...next].slice(0, 50));
        return previous;
      });
      return items.slice(0, -1);
    });
  }, []);

  const redo = useCallback(() => {
    setFuture((items) => {
      const next = items[0];
      if (next === undefined) return items;
      setPresent((current) => {
        setPast((previous) => [...previous, current].slice(-50));
        return next;
      });
      return items.slice(1);
    });
  }, []);

  return {
    present,
    replace,
    undo,
    redo,
    canUndo: past.length > 0,
    canRedo: future.length > 0,
  };
}
