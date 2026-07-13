import { createContext, useContext } from "react";

export type ConfirmOptions = {
  title: string;
  description: string;
  confirmLabel?: string;
  cancelLabel?: string;
  confirmColor?: "primary" | "error" | "warning" | "success";
};

export type ConfirmContextValue = {
  confirm: (options: ConfirmOptions) => Promise<boolean>;
};

// Accept-by-default keeps reusable hooks testable outside the app shell; the
// application always mounts ConfirmProvider, so destructive actions are modal.
export const ConfirmContext = createContext<ConfirmContextValue>({
  confirm: async () => true,
});

export function useConfirm(): ConfirmContextValue {
  const value = useContext(ConfirmContext);
  return value;
}
