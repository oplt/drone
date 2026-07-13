import { useCallback, useMemo, useState, type ReactNode } from "react";
import ConfirmDialog from "./ConfirmDialog";
import { ConfirmContext, type ConfirmOptions } from "./ConfirmContext";

type PendingConfirm = ConfirmOptions & {
  resolve: (accepted: boolean) => void;
};

export function ConfirmProvider({ children }: { children: ReactNode }) {
  const [pending, setPending] = useState<PendingConfirm | null>(null);

  const confirm = useCallback((options: ConfirmOptions) => {
    return new Promise<boolean>((resolve) => {
      setPending((current) => {
        current?.resolve(false);
        return { ...options, resolve };
      });
    });
  }, []);

  const close = useCallback((accepted: boolean) => {
    setPending((current) => {
      current?.resolve(accepted);
      return null;
    });
  }, []);

  const value = useMemo(() => ({ confirm }), [confirm]);

  return (
    <ConfirmContext.Provider value={value}>
      {children}
      <ConfirmDialog
        open={pending !== null}
        title={pending?.title ?? "Confirm action"}
        description={pending?.description ?? "Please confirm this action."}
        confirmLabel={pending?.confirmLabel}
        cancelLabel={pending?.cancelLabel}
        confirmColor={pending?.confirmColor}
        onConfirm={() => close(true)}
        onCancel={() => close(false)}
      />
    </ConfirmContext.Provider>
  );
}
