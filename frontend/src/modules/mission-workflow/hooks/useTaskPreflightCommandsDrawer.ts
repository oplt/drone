import { useCallback, useState } from "react";

export function useTaskPreflightCommandsDrawer(initialOpen = false) {
  const [open, setOpen] = useState(initialOpen);

  const onOpenChange = useCallback((next: boolean) => {
    setOpen(next);
  }, []);

  const openDrawer = useCallback(() => {
    setOpen(true);
  }, []);

  const closeDrawer = useCallback(() => {
    setOpen(false);
  }, []);

  const toggleDrawer = useCallback(() => {
    setOpen((current) => !current);
  }, []);

  return {
    open,
    setOpen,
    onOpenChange,
    openDrawer,
    closeDrawer,
    toggleDrawer,
  };
}
