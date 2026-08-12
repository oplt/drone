import { useEffect } from "react";
import type { Dispatch, SetStateAction } from "react";
import type { LabelingSaveState } from "./labelingPersistenceTypes";

export function useUnsavedLabelingGuard(
  saveState: LabelingSaveState,
  setSaveError: Dispatch<SetStateAction<string | null>>,
) {
  useEffect(() => {
    const beforeUnload = (event: BeforeUnloadEvent) => {
      if (saveState === "saving" || saveState === "failed") {
        event.preventDefault();
        event.returnValue = "";
      }
    };
    window.addEventListener("beforeunload", beforeUnload);
    return () => window.removeEventListener("beforeunload", beforeUnload);
  }, [saveState]);

  useEffect(() => {
    if (saveState === "saved") return;
    const blockInAppNavigation = (event: MouseEvent) => {
      if (
        event.defaultPrevented ||
        event.button !== 0 ||
        event.metaKey ||
        event.ctrlKey ||
        event.shiftKey ||
        event.altKey
      ) return;
      const target = event.target;
      const anchor = target instanceof Element ? target.closest("a[href]") : null;
      if (!(anchor instanceof HTMLAnchorElement) || anchor.hasAttribute("download")) return;
      const destination = new URL(anchor.href, window.location.href);
      if (destination.origin !== window.location.origin) return;
      event.preventDefault();
      setSaveError((current) =>
        current ?? "Save or resolve this local draft before leaving the labeling workspace.",
      );
    };
    document.addEventListener("click", blockInAppNavigation, true);
    return () => document.removeEventListener("click", blockInAppNavigation, true);
  }, [saveState, setSaveError]);
}
